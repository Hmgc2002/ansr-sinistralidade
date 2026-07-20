"""Extracts the "Listagem dos acidentes com mortos e/ou feridos graves"
table (individual accident records: municipality, datetime, deaths,
serious injuries, road, km marker, accident type) from the same
per-district annual PDF reports used by parser_distrito.py.

Unlike that module, this one works from word-level coordinates rather
than extracted text lines. Two things make plain text extraction
unreliable here:

1. Column order and date format aren't stable across the corpus. 2015+
   reports use "Via Km" order with "DD-MM-YYYY HH:MM" dates; 2004-2010
   reports use "Km Via" order with "YYYY:MM:DD HH:MM:SS" dates (and
   "M*"/"FG*" column labels). Both are handled by deriving each page's
   column boundaries from its own header row instead of assuming one
   fixed layout.

2. When the free-text "Natureza" (accident type) or "Via" (road name)
   value is too long for one line, the PDF renderer keeps the row's
   other cells vertically centered on the row while the wrapped cell's
   extra lines stack above and below it — so a long Natureza can appear
   as three physical text lines with the Concelho/Datahora/M/FG/Via/Km
   values sandwiched in the *middle* line, not the first one. Text
   extraction reads those three lines in top-to-bottom order and a
   naive per-line parser reads them as unrelated garbage; this module
   instead clusters words into physical lines by y-position, identifies
   which lines are real row starts (a word matching the date pattern)
   vs. wrapped continuation fragments, and assigns each continuation
   fragment to its nearest row start by vertical distance — which
   correctly captures both leading and trailing wraps.

A continuation fragment that lands on the following PDF page (a wrap
straddling a page break) is not linked back to its row; this is a rare
edge case, accepted as a known limitation rather than solved.

2010 is skipped entirely, for the same reason parser_distrito.py skips
it for the concelho table: it isn't just a third column layout, it's
internally inconsistent. Some pages in the same district's 2010 file
use the 2004-2009 colon-separated date format with an unexplained
*third* number between FG and Via that no header column accounts for,
while other pages in that same file use the 2011+ dash-separated
format with the normal two numbers — there's no single row shape to
parse it against.

Usage:
    python src/parser_listagem.py
Writes:
    data/processed/listagem_acidentes.csv
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import pdfplumber

from parser_distrito import find_district_and_year, find_district_pdfs

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "processed" / "listagem_acidentes.csv"

DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$|^\d{4}:\d{2}:\d{2}$|^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}(:\d{2})?$")
LINE_TOP_TOLERANCE = 2.5

# Km is either a bare "-" placeholder or a decimal number (every real
# km marker observed in this corpus carries metre precision, e.g.
# "238,200"). Requiring the decimal part — not just any digits — is
# what keeps a plain house number trailing a street name (some years
# have no "-" placeholder at all for a street with no km marker) from
# being misread as a Km value; road names/codes ("EN1", "A25", "Rua
# ...") always contain a letter, so they never match either way.
KM_VALUE_RE = re.compile(r"^-$|^\d+[.,]\d+$")

# Portuguese ANSR reports draw "Natureza do acidente" from a small
# controlled vocabulary (Despiste, Colisão, Atropelamento, Choque,
# Capotamento — sometimes abbreviated). Detecting the field by its
# first matching keyword, rather than by x-position, sidesteps a real
# problem: header labels ("Via", "Natureza") are visually centered
# over columns much wider than their data, so a header's own x0 can
# sit 40-50pt to the right of where that column's data actually
# starts — a fixed offset that isn't consistent across columns, so no
# single per-page calibration derived from headers works for all of
# them at once.
NATUREZA_START_RE = re.compile(
    r"^(Despiste|Desp\.|Colis|Col\.|Atrop|Choque|Chq\.|Capotamento|Cap\.)",
    re.IGNORECASE,
)


def normalize_data(date_tok: str) -> str:
    if ":" in date_tok:
        y, m, d = date_tok.split(":")
        return f"{y}-{m}-{d}"
    parts = date_tok.split("-")
    if len(parts[0]) == 4:
        return date_tok  # already YYYY-MM-DD
    d, m, y = parts
    return f"{y}-{m}-{d}"


def clean_km(val: str) -> str:
    val = val.strip()
    if val in ("", "-"):
        return ""
    return val.replace(",", ".")


def detect_via_before_km(words: list[dict]) -> bool:
    """True for the 2011+ "Via Km" column order, False for the
    2004-2010 "Km Via" order — read from this page's own header row
    (the header's left-to-right *order* is reliable even though its
    exact x-position isn't, see NATUREZA_START_RE)."""
    via_x = next((w["x0"] for w in words if w["text"].rstrip("*").lower() == "via"), None)
    km_x = next((w["x0"] for w in words if w["text"].rstrip("*").lower() == "km"), None)
    if via_x is None or km_x is None:
        return True
    return via_x < km_x


def detect_mfg_x0(words: list[dict]) -> tuple[float | None, float | None]:
    """Header x0 for M and FG, unlike Via/Natureza (see
    NATUREZA_START_RE), tracks their data closely — but not always
    closely enough: at least one report (Vila Real 2005) renders M/FG
    for some rows on a physical line ~4-5pt away from the rest of that
    row, just outside LINE_TOP_TOLERANCE, so they land in a
    continuation line instead of the main one. Searching every
    candidate word (main line + its continuations) by proximity to
    this calibrated x0, rather than assuming M/FG are always the first
    two tokens after date/time on the main line itself, survives that
    without needing a document-specific tolerance tweak."""
    m_x = next((w["x0"] for w in words if w["text"].rstrip("*") == "M"), None)
    fg_x = next((w["x0"] for w in words if w["text"].rstrip("*") == "FG"), None)
    return m_x, fg_x


MFG_VALUE_RE = re.compile(r"^\d{1,2}\*?$")
MFG_X_TOLERANCE = 20.0


def pick_mfg(candidates: list[dict], x0: float | None) -> tuple[dict | None, list[dict]]:
    """Picks the closest-by-x0 small-integer word to a calibrated M or
    FG column position, and returns the remaining candidates with it
    removed."""
    if x0 is None:
        return None, candidates
    numeric = [w for w in candidates if MFG_VALUE_RE.match(w["text"])]
    inrange = [w for w in numeric if abs(w["x0"] - x0) <= MFG_X_TOLERANCE]
    if not inrange:
        return None, candidates
    best = min(inrange, key=lambda w: abs(w["x0"] - x0))
    return best, [w for w in candidates if w is not best]


def group_lines(words: list[dict]) -> list[dict]:
    lines: list[dict] = []
    for w in sorted(words, key=lambda w: w["top"]):
        for line in lines:
            if abs(line["top"] - w["top"]) <= LINE_TOP_TOLERANCE:
                line["words"].append(w)
                break
        else:
            lines.append({"top": w["top"], "words": [w]})
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
    lines.sort(key=lambda l: l["top"])
    return lines


def is_noise_line(line: dict) -> bool:
    texts = [w["text"] for w in line["words"]]
    if any(t.rstrip("*") in ("Concelho", "Datahora", "Data", "hora") for t in texts):
        return True
    if any("Listagem" in t for t in texts):
        return True
    if any(t.startswith("Relat") for t in texts):
        return True
    if len(texts) == 1 and re.fullmatch(r"\d{1,4}", texts[0]):
        return True
    if texts and all(set(t) <= {"_"} for t in texts):
        return True
    if texts and texts[0].startswith("*"):
        return True
    return False


# Observed wrap gaps (Via/Natureza/M-FG continuations, several years)
# run 1.5-5.1pt; a real row is a full row-height away (~11-20pt). A
# stray unlabeled total/subtotal line at the bottom of a table (no
# "Total" text, just bare numbers that happen to fall in the M/FG or
# Km x-range) would otherwise always find *some* "nearest" main line
# and get silently absorbed into it — capping the distance lets such
# an orphaned line be discarded instead of corrupting whichever row
# happens to be closest.
CONT_MAX_DISTANCE = 8.0


def assign_continuations(lines: list[dict]) -> dict[int, list[dict]]:
    main_lines = [l for l in lines if l["is_main"]]
    cont_lines = [l for l in lines if not l["is_main"]]
    assignments: dict[int, list[dict]] = {id(m): [] for m in main_lines}
    for cl in cont_lines:
        if not main_lines:
            continue
        nearest = min(main_lines, key=lambda m: abs(m["top"] - cl["top"]))
        if abs(nearest["top"] - cl["top"]) <= CONT_MAX_DISTANCE:
            assignments[id(nearest)].append(cl)
    return assignments


def build_record(
    main_line: dict, cont_lines: list[dict], via_before_km: bool, mfg_x0: tuple[float | None, float | None],
    page_state: dict,
) -> dict | None:
    """Km and the Via/Natureza split are resolved from the main data
    line's own words alone first (content-based: KM_VALUE_RE for Km,
    NATUREZA_START_RE for where Natureza begins). Continuation-line
    words are then folded in by x-position against a Natureza-column
    threshold calibrated from that split — never by simply sorting all
    words (own + continuation) by vertical position and cutting once,
    which breaks whenever a continuation line's *y*-position places it
    between the main line's Via/Km tokens and its own Natureza text
    (an artifact of how the PDF vertically centers short cells against
    a taller wrapped one). When a row's own line has no Natureza match
    at all — fully wrapped away onto continuation lines above/below —
    the threshold from the most recent row that did have one is reused
    via `page_state`, since the column position doesn't change row to
    row on the same page.

    M and FG are searched by calibrated x-position across the main
    line's own words *and* its continuations (see `pick_mfg`), not
    assumed to be the first two tokens after date/time on the main
    line — at least one report puts them on a slightly-offset physical
    line that misses the line-clustering tolerance for some rows but
    not others."""
    words = main_line["words"]
    date_idx = next((i for i, w in enumerate(words) if DATE_RE.match(w["text"])), None)
    if date_idx is None:
        return None
    concelho = " ".join(w["text"] for w in words[:date_idx]).strip()
    date_tok = words[date_idx]["text"]
    rest_start = date_idx + 1
    time_tok = ""
    if rest_start < len(words) and TIME_RE.match(words[rest_start]["text"]):
        time_tok = words[rest_start]["text"]
        rest_start += 1

    own_after_time = list(words[rest_start:])
    cont_words_all = [w for cl in cont_lines for w in cl["words"]]
    m_x, fg_x = mfg_x0

    m_word, _ = pick_mfg(own_after_time + cont_words_all, m_x)
    pool = [w for w in own_after_time + cont_words_all if w is not m_word]
    fg_word, _ = pick_mfg(pool, fg_x)

    m_val = m_word["text"].rstrip("*") if m_word else ""
    fg_val = fg_word["text"].rstrip("*") if fg_word else ""

    own_tail = [w for w in own_after_time if w is not m_word and w is not fg_word]
    cont_words_all = [w for w in cont_words_all if w is not m_word and w is not fg_word]

    nat_idx = next((i for i, w in enumerate(own_tail) if NATUREZA_START_RE.match(w["text"])), None)
    pre = own_tail[: nat_idx if nat_idx is not None else len(own_tail)]
    nat_words_own = own_tail[nat_idx:] if nat_idx is not None else []

    km = ""
    via_words_own = pre
    idxs = [i for i, w in enumerate(pre) if KM_VALUE_RE.match(w["text"])]
    if idxs:
        k = idxs[-1] if via_before_km else idxs[0]
        km = pre[k]["text"]
        via_words_own = pre[:k] if via_before_km else pre[k + 1:]

    if nat_idx is not None:
        page_state["natureza_x0"] = own_tail[nat_idx]["x0"]
    threshold = page_state.get("natureza_x0")

    cont_via_words, cont_nat_words = [], []
    for w in cont_words_all:
        if threshold is not None and w["x0"] >= threshold - 15:
            cont_nat_words.append(w)
        else:
            cont_via_words.append(w)

    all_via = sorted(via_words_own + cont_via_words, key=lambda w: (w["top"], w["x0"]))
    all_nat = sorted(nat_words_own + cont_nat_words, key=lambda w: (w["top"], w["x0"]))

    if not concelho or not date_tok:
        return None

    return {
        "concelho": concelho,
        "data": normalize_data(date_tok),
        "hora": time_tok,
        "mortos": m_val,
        "feridos_graves": fg_val,
        "via": " ".join(w["text"] for w in all_via),
        "km": clean_km(km),
        "natureza": " ".join(w["text"] for w in all_nat),
    }


def extract_listagem_records(pdf_path: Path, distrito: str, ano: str) -> list[dict]:
    records: list[dict] = []
    page_state: dict = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            texts = {w["text"] for w in words}
            # most years render one "Datahora" word; 2005 splits it into
            # "Data" + "hora" as two separate words instead
            if "Datahora" not in texts and not ("Data" in texts and "hora" in texts):
                continue
            via_before_km = detect_via_before_km(words)
            mfg_x0 = detect_mfg_x0(words)
            lines = [l for l in group_lines(words) if not is_noise_line(l)]
            for l in lines:
                l["is_main"] = any(DATE_RE.match(w["text"]) for w in l["words"])
            assignments = assign_continuations(lines)
            for l in lines:
                if not l["is_main"]:
                    continue
                rec = build_record(l, assignments[id(l)], via_before_km, mfg_x0, page_state)
                if rec is None:
                    continue
                rec["distrito"] = distrito
                rec["ano"] = ano
                rec["source_file"] = pdf_path.name
                records.append(rec)
    return records


def dedupe_by_district_year(rows: list[dict]) -> list[dict]:
    """Mirrors parser_distrito.dedupe_by_district_year: some years have
    more than one non-"24h" file for the same district, which would
    otherwise double-count every accident record."""
    files_by_key: dict[tuple[str, str], set[str]] = {}
    for r in rows:
        files_by_key.setdefault((r["distrito"], r["ano"]), set()).add(r["source_file"])

    keep_file: dict[tuple[str, str], str] = {}
    for key, files in files_by_key.items():
        if len(files) == 1:
            keep_file[key] = next(iter(files))
        else:
            with_30 = sorted(f for f in files if "30" in f)
            keep_file[key] = with_30[0] if with_30 else sorted(files)[0]

    return [r for r in rows if r["source_file"] == keep_file[(r["distrito"], r["ano"])]]


def main() -> None:
    pdfs = find_district_pdfs()
    if not pdfs:
        print("Nenhum PDF de distrito encontrado em data/raw/<ano>/", file=sys.stderr)
        sys.exit(1)

    all_rows: list[dict] = []
    n_ok = n_empty = n_error = 0

    for i, path in enumerate(pdfs, 1):
        distrito, ano = find_district_and_year(path)
        if not distrito or not ano:
            n_empty += 1
            continue
        if ano == "2010":
            # internally inconsistent row format even within a single
            # file — see module docstring
            n_empty += 1
            continue
        try:
            rows = extract_listagem_records(path, distrito, ano)
        except Exception as exc:
            print(f"[{i}/{len(pdfs)}] ERRO em {path.parent.name}/{path.name}: {exc}")
            n_error += 1
            continue

        if rows:
            all_rows.extend(rows)
            n_ok += 1
        else:
            print(f"[{i}/{len(pdfs)}] aviso: sem listagem em {path.parent.name}/{path.name}")
            n_empty += 1

        if i % 50 == 0:
            print(f"[{i}/{len(pdfs)}] processados...")

    print(f"\n{n_ok} ficheiros com dados, {n_empty} sem tabela encontrada, {n_error} com erro")

    if not all_rows:
        print("Nenhuma linha extraída.", file=sys.stderr)
        return

    before = len(all_rows)
    all_rows = dedupe_by_district_year(all_rows)
    if len(all_rows) != before:
        print(f"Deduplicação: {before - len(all_rows)} linhas removidas (mais de um ficheiro por distrito/ano)")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["distrito", "ano", "concelho", "data", "hora", "mortos",
                  "feridos_graves", "via", "km", "natureza", "source_file"]
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"{len(all_rows)} linhas (registos individuais de acidentes) -> {OUT_PATH}")


if __name__ == "__main__":
    main()
