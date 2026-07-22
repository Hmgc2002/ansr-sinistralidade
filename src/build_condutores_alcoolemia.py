"""Extracts a tidy annual series of driver alcohol-testing stats
(1998-2004) from the national report PDF dump — one of the "recurring
tables" the README flagged as a natural next step after the main annual
series, picked because it's one of the few that actually recurs with a
countable structure across several editions (most others shift too much
year to year to be worth reconciling).

The 1999-2003 reports show a "Condutores testados" table broken down by
**vehicle type** (Ligeiros, Pesados, Motociclos, ...) x BAC band, with the
BAC bands themselves getting one more subdivision each edition (a "TAS não
definida" column appears from the 2002 edition on). The 2004 report drops
this breakdown entirely in favour of "5. Condutores segundo o teste de
alcoolemia", organized by **injury severity** (Vítimas mortais/Feridos
graves/Feridos leves) x test outcome instead — a genuinely different
cross-tab, not a formatting tweak, and it isn't captured by
`pdf_tables_index.csv` at all (pdfplumber's grid detector doesn't pick up
this specific table as a "table"; it's parsed here straight from
`extract_text()`).

Despite the schema change, both editions' **grand-total row** collapses
to the same four aggregate figures: how many drivers involved in
accidents were tested, how many of those tested over the legal limit
(>=0.5 g/l), how many weren't tested at all, and the total number of
drivers involved. That aggregate is what this script extracts — not the
fuller vehicle-type or severity breakdowns, which don't share a common
shape to extract into one column set.

Each edition shows the current and previous year side by side (same
overlap-for-cross-checking pattern as build_serie_anual_nacional.py), and
the more recent edition's figures are kept for a year covered by two
editions. Checked against each other, four of the five overlaps (1999,
2000, 2002, 2003) agree exactly across editions on all four aggregates.
The fifth doesn't: 2001 as shown in the 2002 edition reclassifies 330
drivers from (implicitly) "tested, BAC below the limit" into an explicit
"TAS não definida" (test taken, result inconclusive) bucket that the
2001 edition's own table didn't break out — total_condutores_intervenientes
and total_infratores are unaffected, but total_testados shifts by exactly
that 330. Kept as the more recent edition's figure, same rule as every
other overlap, but called out here since it's a real revision, not
extraction noise.

No table after 2004 was found with this structure: 2005-2018 report this
narratively (a %, in prose or a chart) rather than as a data table, so the
series stops there rather than being padded with guesses.

Usage:
    python src/build_condutores_alcoolemia.py
Writes:
    data/processed/condutores_alcoolemia.csv
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
INDEX_PATH = ROOT / "data" / "processed" / "pdf_tables_index.csv"
OUT_PATH = ROOT / "data" / "processed" / "condutores_alcoolemia.csv"

NATIONAL_REPORT_BY_YEAR = {
    "1999": "Relatório Anual 1999 (PDF).pdf",
    "2000": "Relatório Anual 2000 (PDF).pdf",
    "2001": "Relatório Anual 2001(PDF).pdf",
    "2002": "Relatório Anual 2002 (PDF).pdf",
    "2003": "Relatório Anual 2003 (PDF).pdf",
    "2004": "Relatório Anual 2004 (PDF).pdf",
}


def find_vehicle_schema_csv(report_year: str) -> Path | None:
    with INDEX_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["year"] == report_year and "condutores testados" in row["first_row_preview"].lower():
                return ROOT / row["csv_path"]
    return None


def extract_vehicle_schema(csv_path: Path) -> dict[str, dict]:
    """1999-2003 editions: rows are (label, year, ...BAC bands..., total_infratores, total_intervenientes),
    with the number of BAC-band columns and a leading 'TAS não definida'
    column varying by edition — inferred here from the row width rather
    than assumed fixed.
    """
    rows = list(csv.reader(csv_path.open(encoding="utf-8")))

    def parse(nums: list[int]) -> dict:
        if len(nums) == 6:  # 1999 edition: non_inf, inf1, inf2, inf3, inf_total, total_interv
            non_inf, inf_total, total_interv = nums[0], nums[4], nums[5]
            tas_nao_def = 0
        elif len(nums) == 7:  # 2000-2001: non_inf_a, non_inf_b, inf1, inf2, inf3, inf_total, total_interv
            non_inf, inf_total, total_interv = nums[0] + nums[1], nums[5], nums[6]
            tas_nao_def = 0
        else:  # 2002-2003 (8 nums): tas_nao_def, non_inf_a, non_inf_b, inf1, inf2, inf3, inf_total, total_interv
            tas_nao_def, non_inf, inf_total, total_interv = nums[0], nums[1] + nums[2], nums[6], nums[7]
        return {
            "total_condutores_intervenientes": total_interv,
            "total_testados": tas_nao_def + non_inf + inf_total,
            "total_infratores": inf_total,
        }

    out: dict[str, dict] = {}
    for i, row in enumerate(rows):
        if row[0].strip().lower() != "total":
            continue
        # this row is the block's *current*-year line; the block's
        # *previous*-year line is the row right before it, with the same
        # column count but a blank label (row[0] repeats the vehicle-type
        # label only on its last line, e.g. "Velocípedes"/"Total" — every
        # earlier line in a multi-line block, including the prior-year
        # figures, carries no label at all)
        curr_year = row[1].strip()
        out[curr_year] = parse([int(v) for v in row[2:]])
        prev_row = rows[i - 1]
        if prev_row[0].strip() == "" and prev_row[1].strip().isdigit():
            prev_year = prev_row[1].strip()
            out[prev_year] = parse([int(v) for v in prev_row[2:]])
    return out


def extract_severity_schema(pdf_path: Path) -> dict[str, dict]:
    """2004 edition: a page with rows Submetido / TAS não def. / TAS<0,5 /
    0,5-0,79 g/l / 0,8-1,19 g/l / TAS >= 1,2 g/l / Não submetido / Não
    definido / Total, each with 10 numbers (5 severity groups x 2 years) —
    not detected by pdfplumber's own table-grid logic, so this parses
    extract_text() lines directly. Only the last pair of numbers on each
    row is used (the "Total condutores intervenientes" group).
    """
    with pdfplumber.open(pdf_path) as pdf:
        page = next(
            (p for p in pdf.pages if _has_alcohol_table(p)),
            None,
        )
    if page is None:
        return {}

    all_lines = page.extract_text().splitlines()
    # this page has three side-by-side tables (sections "5.", "6.", "7."
    # in the source), each with its own "Total" row — restrict to the
    # first section's lines only, or "Total" from section 6/7 would
    # silently overwrite section 5's
    start = next(i for i, ln in enumerate(all_lines) if "teste de alcoolemia" in ln.lower())
    end = next((i for i, ln in enumerate(all_lines) if i > start and re.match(r"6\.\s", ln)), len(all_lines))
    lines = all_lines[start:end]

    year_line = next((ln for ln in lines if re.match(r"(?:19|20)\d{2} (?:19|20)\d{2}", ln.strip())), None)
    if not year_line:
        return {}
    prev_year, curr_year = year_line.split()[:2]

    wanted = {
        "submetido": "total_testados",
        "0,5-0,79 g/l": "_inf1",
        "0,8-1,19 g/l": "_inf2",
        "tas >= 1,2 g/l": "_inf3",
        "total": "total_condutores_intervenientes",
    }
    found: dict[str, tuple[int, int]] = {}
    for ln in lines:
        low = ln.strip().lower()
        key = next((k for k in wanted if low.startswith(k)), None)
        if key is None:
            continue
        nums = re.findall(r"-?\d+", ln)
        if len(nums) < 2:
            continue
        found[wanted[key]] = (int(nums[-2]), int(nums[-1]))

    required = {"total_testados", "_inf1", "_inf2", "_inf3", "total_condutores_intervenientes"}
    if not required.issubset(found):
        return {}

    out = {}
    for i, year in enumerate((prev_year, curr_year)):
        out[year] = {
            "total_condutores_intervenientes": found["total_condutores_intervenientes"][i],
            "total_testados": found["total_testados"][i],
            "total_infratores": found["_inf1"][i] + found["_inf2"][i] + found["_inf3"][i],
        }
    return out


def _has_alcohol_table(page) -> bool:
    text = (page.extract_text() or "").lower()
    return "submetido" in text and "não submetido" in text and "tas" in text


def main() -> None:
    by_year: dict[str, dict] = {}
    for report_year, filename in NATIONAL_REPORT_BY_YEAR.items():
        path = RAW_DIR / report_year / filename
        if not path.exists():
            print(f"[{report_year}] aviso: ficheiro não encontrado: {path}")
            continue

        if report_year == "2004":
            extracted = extract_severity_schema(path)
        else:
            csv_path = find_vehicle_schema_csv(report_year)
            extracted = extract_vehicle_schema(csv_path) if csv_path else {}

        if not extracted:
            print(f"[{report_year}] aviso: tabela de alcoolemia não encontrada")
            continue
        print(f"[{report_year}] {sorted(extracted.keys())}")
        # most recent edition wins for a year covered by two editions —
        # report any disagreement instead of silently overwriting, since
        # a real mismatch here (as opposed to the known 2001 revision;
        # see module docstring) would mean a parsing bug, not a revision
        for year, new in extracted.items():
            old = by_year.get(year)
            if old and old != new:
                diff = {k: (old[k], new[k]) for k in new if old[k] != new[k]}
                print(f"  aviso: {year} revisto por esta edição — {diff}")
        by_year.update(extracted)

    if not by_year:
        print("Nenhuma linha extraída.")
        return

    rows = []
    for year in sorted(by_year):
        d = by_year[year]
        testados, interv = d["total_testados"], d["total_condutores_intervenientes"]
        rows.append(
            {
                "ano": year,
                "total_condutores_intervenientes": interv,
                "total_testados": testados,
                "total_nao_testados": interv - testados,
                "total_infratores": d["total_infratores"],
                "pct_testados": round(testados / interv * 100, 1) if interv else None,
                "pct_infratores_entre_testados": round(d["total_infratores"] / testados * 100, 2) if testados else None,
            }
        )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} anos ({rows[0]['ano']}-{rows[-1]['ano']}) -> {OUT_PATH}")


if __name__ == "__main__":
    main()
