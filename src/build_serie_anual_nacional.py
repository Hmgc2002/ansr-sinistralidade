"""Extracts the national annual historical series (accidents/victims,
1975-2019) that (almost) every ANSR national annual report includes as
a single table near its start — not a per-report snapshot, but a
rolling multi-year lookback (10-25 years) that grows by one row with
each edition. A handful of editions already cover 1975-2019 between
them with overlapping years for cross-checking:

- 1999 report: 1975-1999
- 2009 report: 1990-2009
- 2014 report: 2005-2014 (covers 2010-2012, whose own reports use an
  entirely different, incompatible table format — see
  parser_distrito.py's docstring for the same issue at district level)
- 2019 report: 2010-2019

So rather than reconcile 21 editions' differing per-year table layouts
individually, this scans every edition's own tables (from
pdf_tables_index.csv / pdf_raw/) for this one recurring table and
merges what each contributes, preferring the most recent edition's
figures whenever two editions cover the same year.

The table's column layout is a fixed 16-column pattern that holds
across every edition checked (1999-2019), even though the header
wording drifts a lot ("Acidentes com mortos e/ou f. graves" in early
2000s, "AcVM ou AcFG" abbreviated by 2019): ano, then 7 pairs of
(value, % change vs. previous year), then the severity index with no
trailing %:
    ano, acidentes_com_vitimas, %,
    acidentes_com_mortos_ou_feridos_graves, %,
    acidentes_com_mortos, %, vitimas_mortais, %,
    feridos_graves, %, feridos_leves, %, total_feridos, %,
    indice_gravidade

pdfplumber renders the same table two different ways depending on the
edition — sometimes one row per year (year as a bare 4-digit cell),
sometimes the whole table as 2-3 rows where every cell is a single
"\n"-joined string of all years' values for that column (no visible
row-separator lines in the source PDF for pdfplumber to key off).
Both are handled: the second form is detected by a first cell that
starts with a year but contains embedded newlines, and repaired by
splitting every column on "\n" and zipping them back into rows.

Usage:
    python src/build_serie_anual_nacional.py
Writes:
    data/processed/serie_anual_nacional.csv
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "data" / "processed" / "pdf_tables_index.csv"
OUT_PATH = ROOT / "data" / "processed" / "serie_anual_nacional.csv"

YEAR_RE = re.compile(r"^(19|20)\d{2}$")

FIELDS = [
    "acidentes_com_vitimas", "acidentes_com_mortos_ou_feridos_graves",
    "acidentes_com_mortos", "vitimas_mortais", "feridos_graves",
    "feridos_leves", "total_feridos", "indice_gravidade",
]
# index into a 16-cell row for each field (ano is index 0, skipped here)
FIELD_COLS = [1, 3, 5, 7, 9, 11, 13, 15]


def is_candidate_table(all_text: str) -> bool:
    t = all_text.lower()
    return "grav" in t and ("e/ou" in t or "acvm" in t)


def clean_num(s: str) -> str:
    s = s.strip().replace("\xa0", " ").replace(" ", "")
    if s in ("", "-", "--", "__", "n.d.", "n.d", "-,-"):
        return ""
    return s.replace(",", ".")


def parse_row16(cells: list[str]) -> dict | None:
    ano = cells[0].strip()
    if not YEAR_RE.match(ano):
        return None
    if len(cells) < 16:
        return None
    row = {"ano": ano}
    for field, col in zip(FIELDS, FIELD_COLS):
        row[field] = clean_num(cells[col])
    return row


def parse_table(rows: list[list[str]]) -> list[dict]:
    out = []
    for row in rows:
        if not row or not row[0]:
            continue
        first = row[0].strip()
        if YEAR_RE.match(first):
            parsed = parse_row16(row)
            if parsed:
                out.append(parsed)
        elif "\n" in first and YEAR_RE.match(first.split("\n")[0].strip()):
            cols = [c.split("\n") for c in row]
            n = len(cols[0])
            for i in range(n):
                cells = [c[i] if i < len(c) else "" for c in cols]
                parsed = parse_row16(cells)
                if parsed:
                    out.append(parsed)
    return out


def sanity_ok(rows: list[dict]) -> bool:
    """Rejects tables that matched the keyword search but aren't
    actually this series (e.g. a different table that happens to also
    mention "gravidade") — real rows always have a plausible death
    count and more accidents-with-victims than deaths."""
    if not rows:
        return False
    good = 0
    for r in rows:
        try:
            vm = int(r["vitimas_mortais"] or -1)
            av = int(r["acidentes_com_vitimas"] or -1)
        except ValueError:
            continue
        if 50 <= vm <= 5000 and av > vm:
            good += 1
    return good >= len(rows) * 0.7


def main() -> None:
    with INDEX_PATH.open(encoding="utf-8") as f:
        index_rows = list(csv.DictReader(f))

    by_year_report: dict[str, list[tuple[str, dict]]] = {}
    report_years = sorted({r["year"] for r in index_rows})

    for report_year in report_years:
        candidates = [r for r in index_rows if r["year"] == report_year and int(r["page"]) <= 100]
        for c in candidates:
            csv_path = ROOT / c["csv_path"]
            try:
                with csv_path.open(encoding="utf-8") as f:
                    raw_rows = list(csv.reader(f))
            except FileNotFoundError:
                continue
            all_text = "\n".join(cell for row in raw_rows for cell in row)
            if not is_candidate_table(all_text):
                continue
            parsed = parse_table(raw_rows)
            if not sanity_ok(parsed):
                continue
            for r in parsed:
                by_year_report.setdefault(r["ano"], []).append((report_year, r))

    # prefer the most recent report edition for each year
    final: dict[str, dict] = {}
    for ano, candidates in by_year_report.items():
        candidates.sort(key=lambda t: t[0])
        report_year, row = candidates[-1]
        row = dict(row)
        row["source_report_year"] = report_year
        final[ano] = row

    anos = sorted(final.keys())
    if not anos:
        print("Nenhuma linha da série histórica encontrada.")
        return

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ano", *FIELDS, "source_report_year"])
        writer.writeheader()
        for ano in anos:
            writer.writerow(final[ano])

    print(f"{len(anos)} anos ({anos[0]}-{anos[-1]}) -> {OUT_PATH}")
    missing = [y for y in range(int(anos[0]), int(anos[-1]) + 1) if str(y) not in final]
    if missing:
        print(f"Anos em falta dentro do intervalo: {missing}")


if __name__ == "__main__":
    main()
