"""Extracts structured records from the ANSR 'Pontos Negros' PDFs
(road black-spot inspections and safety recommendations).

pdfplumber's table detection is unreliable on these documents: the
default ('lines') strategy silently drops the Entidade/Estrada/Km cells
for some rows, and the alternate ('text') strategy fragments the free
-text Problemas/Recomendações columns into unstable sub-columns. Rather
than risk misattributing a recommendation to the wrong road/entity, this
parser deliberately extracts only the fields it can place reliably by
word position: Entidade Gestora da Via, Estrada, Km, Relatório Data and
Estado de Intervenção. The Problemas/Recomendações free text is dropped.

Column x-bands below were measured from the 2022 report and assumed
stable across years (same official template). If a future year's layout
shifts, `_bucket` will silently misassign text — spot check output
before trusting a new year.

Usage:
    python src/parser_pontos_negros.py
Writes:
    data/processed/pontos_negros.csv
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "pontos_negros"
OUT_PATH = ROOT / "data" / "processed" / "pontos_negros.csv"

# (band_name, x0_min, x0_max) — a word is assigned to the first band
# whose range contains its x0. Anything outside these ranges (the
# Problemas/Recomendações columns, x ~207-689) is ignored on purpose.
BANDS = [
    ("entidade", 0, 100),
    ("estrada", 100, 150),
    ("km", 150, 205),
    ("data", 680, 720),
    ("estado", 720, 830),
]
HEADER_ROW_MARGIN = 15  # pt past the 'Estrada' column header before real data starts
NEW_RECORD_GAP = 25  # vertical gap (pt) that signals a new record, not a wrapped word
LINE_TOLERANCE = 3  # pt: words within this of each other are "the same line"


def _bucket(x0: float) -> str | None:
    for name, lo, hi in BANDS:
        if lo <= x0 < hi:
            return name
    return None


def _group_into_lines(words: list[dict]) -> list[list[dict]]:
    """Groups words into visual lines by top-coordinate proximity.

    Decisions below act on a whole line at once — not word-by-word — so
    that a new record's Entidade (the leftmost column, read first) can
    never be appended to the previous record's buffer before the
    same line's Estrada is seen and triggers a flush.
    """
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(w["top"] - lines[-1][0]["top"]) <= LINE_TOLERANCE:
            lines[-1].append(w)
        else:
            lines.append([w])
    return lines


def extract_records(pdf_path: Path, year: str) -> list[dict]:
    records: list[dict] = []
    buf = {name: [] for name, _, _ in BANDS}
    has_data = False

    def flush():
        nonlocal buf, has_data
        if has_data:
            records.append(
                {
                    "year": year,
                    "entidade_gestora": " ".join(buf["entidade"]).strip(),
                    "estrada": " ".join(buf["estrada"]).strip(),
                    "km": " ".join(buf["km"]).strip(),
                    "relatorio_data": " ".join(buf["data"]).strip(),
                    "estado_intervencao": " ".join(buf["estado"]).strip(),
                }
            )
        buf = {name: [] for name, _, _ in BANDS}
        has_data = False

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            # the header row position (and thus where real data starts)
            # varies a lot per page: page 1 has a tall institutional
            # title block pushing it down, later pages don't. Anchor on
            # the literal 'Estrada' column header instead of a fixed cutoff.
            header_words = [w for w in words if w["text"] == "Estrada"]
            cutoff = (header_words[0]["top"] + HEADER_ROW_MARGIN) if header_words else 0

            relevant = [w for w in words if w["top"] >= cutoff and _bucket(w["x0"])]
            lines = _group_into_lines(relevant)

            # A record's Estado value ("Não Implementadas", "Parcialmente
            # implementadas") routinely wraps onto its own line before the
            # Entidade cell of that same record appears — so Entidade can
            # legitimately show up on the page's 2nd relevant line rather
            # than its 1st. Only an unusually long "estado" free-text (a
            # justification instead of the usual one/two-word status) pushes
            # it past that — checking the first two lines instead of just
            # the first is what tells a genuine new record (identity band
            # nearby) apart from that free-text still wrapping across the
            # page break (no identity band nearby, just more prose).
            page_starts_new_record = any(
                {_bucket(w["x0"]) for w in line} & {"entidade", "estrada"}
                for line in lines[:2]
            )

            page_top_cursor: float | None = None
            first_line_on_page = True
            for line in lines:
                line_bands = {_bucket(w["x0"]) for w in line}
                if first_line_on_page and has_data:
                    # A record's identity fields (entidade/estrada) never
                    # span a page break in this template, so a new page
                    # that actually starts a new record always belongs to a
                    # different record than whatever is still buffered.
                    if page_starts_new_record:
                        flush()
                elif (
                    "estrada" in line_bands
                    and buf["estrada"]
                    and page_top_cursor is not None
                    and line[0]["top"] - page_top_cursor > NEW_RECORD_GAP
                ):
                    # this line carries a fresh Estrada value, after a real
                    # vertical gap on the same page (not just the next
                    # wrapped line of the same record) — flush BEFORE any
                    # of this line's words (including Entidade) are added
                    flush()
                for w in sorted(line, key=lambda w: w["x0"]):
                    band = _bucket(w["x0"])
                    buf[band].append(w["text"])
                has_data = True
                page_top_cursor = line[0]["top"]
                first_line_on_page = False
    flush()
    return records


def find_pdfs() -> list[tuple[str, Path]]:
    out = []
    for path in sorted(RAW_DIR.glob("PN_*.pdf")):
        m = re.search(r"PN_(\d{4})", path.name)
        if m:
            out.append((m.group(1), path))
    return out


def main() -> None:
    pdfs = find_pdfs()
    if not pdfs:
        print(f"Nenhum PDF encontrado em {RAW_DIR} (esperado: PN_<ano>.pdf)")
        return

    all_records: list[dict] = []
    for year, path in pdfs:
        print(f"[{year}] a processar {path.name} ...")
        records = extract_records(path, year)
        print(f"[{year}] {len(records)} pontos negros extraídos")
        all_records.extend(records)

    if not all_records:
        print("Nenhum registo extraído.")
        return

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_records[0].keys()))
        writer.writeheader()
        writer.writerows(all_records)
    print(f"\n{len(all_records)} registos -> {OUT_PATH}")


if __name__ == "__main__":
    main()
