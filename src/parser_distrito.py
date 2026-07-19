"""Extracts the "Acidentes e vítimas segundo o concelho" (accidents and
victims by municipality) table from the ANSR per-district annual PDF
reports.

Only works for 2011-2018: the 2004-2010 reports use a different, older
template (a "Vítimas segundo o concelho" table with side-by-side 24h/30
dias columns and no "UTENTES" section) that this parser does not
handle — those years come back empty, not wrong.

Every 2011+ district report contains ~10 tables sharing the exact same
column header ("Acidentes Vítimas Feridos Feridos Total Índice de" /
"c/ vítimas mortais graves leves vítimas gravidade") for different
breakdowns (by month, weekday, light conditions, ...). In 2013+, the
concelho (municipality) breakdown is consistently the LAST such table
before the "UTENTES" section begins, so that ordering — not the heading
text, which can be split awkwardly across a page break — is used to
find it (`_find_concelho_table_by_utentes`).

2011-2012 don't repeat that column header once per table, so "the last
occurrence before UTENTES" degenerates to "the only occurrence in the
whole document" and spans several unrelated tables. For those two
years, `_find_concelho_table_by_heading` anchors on the actual
"... segundo o concelho" heading in the document body instead (distinct
from its dotted table-of-contents entry earlier in the same document),
ending at the next section, which is consistently "Listagem dos
acidentes..." in every year checked. `find_concelho_rows` tries the
UTENTES strategy first and only falls back to the heading strategy if
the first candidate's rows fail the sanity check below — the UTENTES
strategy can find *a* block in 2011-2012 without erroring (the shared
header text happens to also appear once, elsewhere), it's just the
wrong block, so falling back requires actually parsing and checking the
rows, not just checking whether a block was found at all.

Output: one row per (distrito, ano, concelho) with accident/victim
counts, giving genuine municipality-level geographic granularity (unlike
the road+km "Pontos Negros" data, concelho names can be matched to
standard Portuguese municipality boundaries for a real choropleth map).

Usage:
    python src/parser_distrito.py
Writes:
    data/processed/sinistralidade_por_concelho.csv
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_PATH = ROOT / "data" / "processed" / "sinistralidade_por_concelho.csv"

HEADER_ANCHOR = "vítimas mortais graves leves vítimas gravidade"
SECTION_END = "UTENTES"
CONCELHO_HEADING = "segundo o concelho"
NEXT_SECTION_HEADING = "Listagem dos acidentes"

NUMBERS_ONLY_RE = re.compile(
    r"^(?P<acidentes>\d[\d.]*)\s+(?P<pct_acidentes>[\d,]+)\s+"
    r"(?P<mortais>\d[\d.]*)\s+(?P<pct_mortais>[\d,]+)\s+"
    r"(?P<graves>\d[\d.]*)\s+(?P<pct_graves>[\d,]+)\s+"
    r"(?P<leves>\d[\d.]*)\s+(?P<pct_leves>[\d,]+)\s+"
    r"(?P<total_vitimas>\d[\d.]*)\s+(?P<pct_total>[\d,]+)\s+"
    r"(?P<indice>[\d,]+)$"
)

ROW_RE = re.compile(
    r"^(?P<concelho>.+?)\s+"
    r"(?P<acidentes>\d[\d.]*)\s+(?P<pct_acidentes>[\d,]+)\s+"
    r"(?P<mortais>\d[\d.]*)\s+(?P<pct_mortais>[\d,]+)\s+"
    r"(?P<graves>\d[\d.]*)\s+(?P<pct_graves>[\d,]+)\s+"
    r"(?P<leves>\d[\d.]*)\s+(?P<pct_leves>[\d,]+)\s+"
    r"(?P<total_vitimas>\d[\d.]*)\s+(?P<pct_total>[\d,]+)\s+"
    r"(?P<indice>[\d,]+)$"
)

# Fixed list, longest names first, so "Castelo Branco" matches before a
# shorter false-positive would. Deriving district from the filename
# instead of the PDF's own "Distrito - X" header avoids a real bug: that
# header sometimes wraps two-word names across a line break inside the
# PDF (e.g. "Distrito - CASTELO\nBRANCO"), which silently truncated the
# name when read from the page text.
DISTRICTS = sorted(
    [
        "Aveiro", "Beja", "Braga", "Bragança", "Castelo Branco", "Coimbra",
        "Évora", "Faro", "Guarda", "Leiria", "Lisboa", "Portalegre", "Porto",
        "Santarém", "Setúbal", "Viana do Castelo", "Vila Real", "Viseu",
    ],
    key=len,
    reverse=True,
)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def find_district_and_year(path: Path) -> tuple[str, str] | tuple[None, None]:
    filename = path.name
    district = next((d for d in DISTRICTS if filename.startswith(d)), None)
    if not district:
        return None, None
    # the year folder (data/raw/<year>/...) is authoritative — some
    # filenames omit the year entirely (e.g. a bare "Aveiro.pdf" in the
    # 2017 folder), so don't rely on YEAR_RE matching the filename
    folder_year = path.parent.name
    if not re.fullmatch(r"(19|20)\d{2}", folder_year):
        return None, None
    return district, folder_year


def _find_concelho_table_by_utentes(full_text: str) -> str | None:
    """Primary strategy (2013+ layout): the concelho table is the LAST
    occurrence of the shared column header before the "UTENTES" section."""
    utentes_idx = full_text.rfind(SECTION_END)
    if utentes_idx == -1:
        return None
    search_region = full_text[:utentes_idx]
    last_header_idx = search_region.rfind(HEADER_ANCHOR)
    if last_header_idx == -1:
        return None
    start = last_header_idx + len(HEADER_ANCHOR)
    return full_text[start:utentes_idx]


def _find_concelho_table_by_heading(full_text: str) -> str | None:
    """Fallback strategy (2011-2012 layout, no "UTENTES" section, and the
    shared column header isn't repeated once per table so the primary
    strategy can't tell tables apart). These years do still have the
    actual "... segundo o concelho" heading in the document body — just
    also, earlier, as a dotted table-of-contents entry. Take the LAST
    occurrence that isn't immediately followed by TOC-style dot leaders,
    and end at the next section (observed to consistently be "Listagem
    dos acidentes..." in every year checked, whether or not a "UTENTES"
    section exists in between elsewhere in the document)."""
    idx = len(full_text)
    body_idx = None
    while True:
        idx = full_text.lower().rfind(CONCELHO_HEADING, 0, idx)
        if idx == -1:
            break
        following = full_text[idx + len(CONCELHO_HEADING): idx + len(CONCELHO_HEADING) + 15]
        if "...." not in following:
            body_idx = idx
            break
    if body_idx is None:
        return None
    start = body_idx + len(CONCELHO_HEADING)
    end = full_text.find(NEXT_SECTION_HEADING, start)
    if end == -1:
        end = len(full_text)
    return full_text[start:end]


def find_concelho_rows(full_text: str) -> list[dict] | None:
    """Tries the primary (UTENTES-anchored) strategy first, then the
    heading-anchored fallback. Both candidate blocks are run all the way
    through parse_concelho_rows (including its sanity check) before
    deciding — the primary strategy can find A block without error even
    in 2011-2012 (the header text happens to match once, elsewhere in
    the document) and that block fails the sanity check rather than
    coming back None, so the fallback must be tried whenever the first
    candidate's *parsed rows* look wrong, not only when no block at all
    was found.
    """
    for finder in (_find_concelho_table_by_utentes, _find_concelho_table_by_heading):
        block = finder(full_text)
        if block is None:
            continue
        rows = parse_concelho_rows(block)
        if rows:
            return rows
    return None


# If the exact HEADER_ANCHOR string happens to appear only once in a
# given document (seen in 2011-2012, where some other table's header is
# apparently formatted just differently enough not to match), "the last
# occurrence before UTENTES" degenerates to "the only occurrence" and the
# captured block spans every table in between (month, weekday, hour...),
# not just concelho. Reject any row whose "concelho" is actually one of
# these other tables' row labels, so that case comes back empty instead
# of silently mislabeling month/weekday/hour data as municipalities.
NON_CONCELHO_LABELS = re.compile(
    r"^(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez|"
    r"\d+ª\s*feira|s[áa]bado|domingo|"
    r"dia|noite|aurora.*|\d{2}-\d{2})$",
    re.IGNORECASE,
)


def merge_wrapped_names(lines: list[str]) -> list[str]:
    """Some years (2004-2009 at least) wrap a two-word/hyphenated
    concelho name across two physical lines, with the row's numbers
    landing on the line IN BETWEEN — e.g. "Albergaria-a-" / <11 numbers>
    / "Velha" — because the name cell is taller than one text line but
    the numeric cells are vertically centered. A plain per-line regex
    silently drops these rows entirely (neither the name fragments nor
    the numbers-only line match ROW_RE). Detect a numbers-only line
    sandwiched between two digit-free text lines and reassemble them
    into one normal "name numbers" line before the main parse.
    """
    merged: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        prev = merged[-1].strip() if merged else ""
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if (
            NUMBERS_ONLY_RE.match(line)
            and prev
            and not re.search(r"\d", prev)
            and nxt
            and not re.search(r"\d", nxt)
        ):
            merged[-1] = f"{prev}{'' if prev.endswith('-') else ' '}{nxt} {line}"
            i += 2
        else:
            merged.append(line)
            i += 1
    return merged


def parse_concelho_rows(block: str) -> list[dict] | None:
    rows = []
    suspicious = 0
    for line in merge_wrapped_names(block.splitlines()):
        line = line.strip()
        if not line or line.upper().startswith("TOTAL"):
            continue
        m = ROW_RE.match(line)
        if not m:
            continue
        g = m.groupdict()
        concelho = g["concelho"].strip()
        if NON_CONCELHO_LABELS.match(concelho):
            suspicious += 1
        rows.append(
            {
                "concelho": concelho,
                "acidentes_com_vitimas": g["acidentes"].replace(".", ""),
                "vitimas_mortais": g["mortais"].replace(".", ""),
                "feridos_graves": g["graves"].replace(".", ""),
                "feridos_leves": g["leves"].replace(".", ""),
                "total_vitimas": g["total_vitimas"].replace(".", ""),
                "indice_gravidade": g["indice"].replace(",", "."),
            }
        )
    if suspicious > 1:
        return None
    return rows


def process_pdf(path: Path) -> list[dict]:
    distrito, ano = find_district_and_year(path)
    if not distrito or not ano:
        return []

    with pdfplumber.open(path) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)

    rows = find_concelho_rows(full_text)
    if not rows:
        return []
    for r in rows:
        r["distrito"] = distrito
        r["ano"] = ano
        r["source_file"] = path.name
    return rows


def find_district_pdfs() -> list[Path]:
    """District reports are the PDFs in each year folder that are not the
    national annual report (those contain 'Relat' or 'Nacional' in the
    name), are not zips, and are not the "24h"/"24 horas" methodology
    variant — where both exist for a district+year, only "30 dias" (or
    the unlabeled single file, for years before the split existed) is
    kept, so the same distrito/ano/concelho is never counted twice under
    two different fatality-count conventions."""
    out = []
    for path in sorted(RAW_DIR.glob("*/*.pdf")):
        name = path.name
        if re.search(r"(?i)relat[oó]rio|relatorionacional|rel_anual|rel20\d{2}_anual", name):
            continue
        if re.search(r"(?i)24\s*h(oras)?\b", name):
            continue
        out.append(path)
    return out


def dedupe_by_district_year(rows: list[dict]) -> list[dict]:
    """Some years have more than one non-"24h" file for the same
    district (e.g. both "Aveiro 2015.pdf" and "Aveiro 2015 30d.pdf"),
    which would otherwise double-count every concelho for that
    district/year. Keep only one source_file per (distrito, ano): the
    one with "30" in its name if there is one, else the
    alphabetically-first, for a deterministic result."""
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
        try:
            rows = process_pdf(path)
        except Exception as exc:
            print(f"[{i}/{len(pdfs)}] ERRO em {path.parent.name}/{path.name}: {exc}")
            n_error += 1
            continue

        if rows:
            all_rows.extend(rows)
            n_ok += 1
        else:
            print(f"[{i}/{len(pdfs)}] aviso: sem tabela de concelho em {path.parent.name}/{path.name}")
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
    fieldnames = ["distrito", "ano", "concelho", "acidentes_com_vitimas", "vitimas_mortais",
                  "feridos_graves", "feridos_leves", "total_vitimas", "indice_gravidade", "source_file"]
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"{len(all_rows)} linhas (distrito x ano x concelho) -> {OUT_PATH}")


if __name__ == "__main__":
    main()
