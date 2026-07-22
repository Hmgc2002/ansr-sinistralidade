"""Extracts the "Sinistralidade no Continente por mês" monthly table from
the 2020-2022 ANSR "24h" annual PDF reports.

parser_xlsx.py already produces data/processed/sinistralidade_mensal_continente_24h.csv
for 2023-2024 from the .xlsx annexes — but the ANSR only started publishing
those annexes in 2023; for 2020-2022 the same "24h" annual report only
exists as a PDF, with the monthly Continente table inline as prose-adjacent
text rather than a structured spreadsheet. This script fills in that gap by
locating the table via pdfplumber word positions (its built-in table-grid
detection silently drops half the rows on this layout) and appending the
result to the existing CSV.

Each report also shows the *previous* year's monthly figures side by side
for comparison (e.g. the 2022 report has both 2021 and 2022 columns), which
gives every year except 2020 two independent extractions to cross-check
against — both overlaps (2020-in-2021-report vs 2020-in-2020-report, and
2021-in-2022-report vs 2021-in-2021-report) match exactly, with the most
recent report's own-year column kept in case of any future discrepancy
(same "latest edition wins" rule as build_serie_anual_nacional.py).

Column positions differ across the three reports (different report years
used different margins/layout), so bands are computed dynamically per PDF
from its own header row instead of hardcoded — anchored on the literal
"Mês" column header, which (unlike "AcV"/"VM"/"FG"/"FL") never also
appears as a chart legend elsewhere on the same page.

Usage:
    python src/parser_continente_24h_pdf.py
Writes:
    data/processed/sinistralidade_mensal_continente_24h.csv (2020-2024, replaces the 2023-2024-only version)
"""
from __future__ import annotations

import csv
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_PATH = ROOT / "data" / "processed" / "sinistralidade_mensal_continente_24h.csv"

# (year, filename, report_year, prev_year) — manually resolved from the
# manifest, same convention as parser_pdf.py's NATIONAL_REPORT_BY_YEAR.
REPORTS = [
    ("2020", "Relatório Anual de Sinistralidade a 24h, fiscalização e contraordenações rodoviárias 2020.pdf", 2020, 2019),
    ("2021", "Relatório Anual de Sinistralidade a 24h, fiscalização e contraordenações rodoviárias 2021.pdf", 2021, 2020),
    ("2022", "Relatório Anual de Sinistralidade a 24h, fiscalização e contraordenações rodoviárias 2022.pdf", 2022, 2021),
]

MONTHS_PT = {
    "janeiro": (1, "Janeiro"), "fevereiro": (2, "Fevereiro"), "março": (3, "Março"),
    "abril": (4, "Abril"), "maio": (5, "Maio"), "junho": (6, "Junho"),
    "julho": (7, "Julho"), "agosto": (8, "Agosto"), "setembro": (9, "Setembro"),
    "outubro": (10, "Outubro"), "novembro": (11, "Novembro"), "dezembro": (12, "Dezembro"),
}
GROUPS = ["AcV", "VM", "FG", "FL"]
FIELD_FOR_GROUP = {
    "AcV": "acidentes_com_vitimas", "VM": "vitimas_mortais",
    "FG": "feridos_graves", "FL": "feridos_leves",
}


def _group_into_lines(words: list[dict], tol: float = 3) -> list[list[dict]]:
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(w["top"] - lines[-1][0]["top"]) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    return lines


def find_table_page(pdf: pdfplumber.PDF):
    """The target table always has all 12 month names plus the AcV group
    label on the same page — a much more specific signal than any single
    keyword, since the report also has several unrelated charts and a
    national (not Continente) monthly table earlier in the same document.
    """
    for page in pdf.pages:
        text = (page.extract_text() or "").lower()
        if "acv" in text and sum(1 for m in MONTHS_PT if m in text) >= 10:
            return page
    return None


def extract_continente_table(page, report_year: int) -> list[dict]:
    words = page.extract_words()
    lines = _group_into_lines(words)

    mes_words = [w for w in words if w["text"] == "Mês"]
    if not mes_words:
        return []
    mes_top = mes_words[0]["top"]

    # the AcV/VM/FG/FL group-label line: must have all four together (a
    # chart legend on the same page may repeat one or two of these labels,
    # but never all four), and sit just above the 'Mês' header — this is
    # what tells the real table header apart from a chart drawn earlier on
    # the same page.
    group_line = next(
        (
            line for line in lines
            if set(GROUPS).issubset({w["text"] for w in line})
            and line[0]["top"] < mes_top
            and mes_top - line[0]["top"] < 60
        ),
        None,
    )
    if group_line is None:
        return []
    group_top = group_line[0]["top"]

    month_lines = [
        line for line in lines
        if min(line, key=lambda w: w["x0"])["text"].strip().lower() in MONTHS_PT
    ]
    if not month_lines:
        return []
    first_data_top = min(line[0]["top"] for line in month_lines)

    # the year-value + 'Δ(%)' row sits between the group line and the first
    # data row; both years appear as bare 4-digit tokens, so match on that
    # rather than assuming they share one exact visual "line" with the delta
    # symbols (they don't, in some reports — off by a few pt).
    prev_year = report_year - 1
    header_zone = [w for w in words if group_top < w["top"] < first_data_top]
    year_or_delta = sorted(
        (w for w in header_zone if w["text"] in (str(report_year), str(prev_year)) or "%" in w["text"]),
        key=lambda w: w["x0"],
    )
    if len(year_or_delta) != len(GROUPS) * 3:
        return []

    col_x = [w["x0"] for w in year_or_delta]
    kinds = ["prev", "curr", "delta"] * len(GROUPS)
    group_for_col = [g for g in GROUPS for _ in range(3)]
    midpoints = [(col_x[i] + col_x[i + 1]) / 2 for i in range(len(col_x) - 1)]

    def bucket_for(x0: float) -> tuple[str, str]:
        i = 0
        while i < len(midpoints) and x0 >= midpoints[i]:
            i += 1
        return kinds[i], group_for_col[i]

    out = []
    for line in lines:
        first_word = min(line, key=lambda w: w["x0"])
        key = first_word["text"].strip().lower()
        if key == "total":
            break
        if key not in MONTHS_PT:
            continue
        month_num, month_label = MONTHS_PT[key]
        buf = {g: {"prev": [], "curr": []} for g in GROUPS}
        for w in sorted(line, key=lambda w: w["x0"]):
            if w is first_word:
                continue
            kind, group = bucket_for(w["x0"])
            if kind == "delta":
                continue
            buf[group][kind].append(w["text"])
        row = {
            "report_year": report_year,
            "scope": "Continente",
            "month": month_label,
            "month_num": month_num,
        }
        for group in GROUPS:
            field = FIELD_FOR_GROUP[group]
            row[field] = int("".join(buf[group]["curr"]).replace(".", ""))
        out.append(row)
    return out


def main() -> None:
    rows_by_year: dict[int, dict] = {}
    for year_label, filename, report_year, _prev_year in REPORTS:
        path = RAW_DIR / year_label / filename
        if not path.exists():
            print(f"[{year_label}] aviso: ficheiro não encontrado: {path}")
            continue
        with pdfplumber.open(path) as pdf:
            page = find_table_page(pdf)
            if page is None:
                print(f"[{year_label}] aviso: página da tabela não encontrada")
                continue
            rows = extract_continente_table(page, report_year)
            if not rows:
                print(f"[{year_label}] aviso: não consegui extrair a tabela")
                continue
            print(f"[{year_label}] {len(rows)} meses extraídos")
            # later reports overwrite earlier ones for the same year (most
            # recent edition wins, same rule as build_serie_anual_nacional.py)
            for row in rows:
                rows_by_year[(row["report_year"], row["month_num"])] = row

    if not rows_by_year:
        print("Nenhuma linha extraída.")
        return

    existing_rows: list[dict] = []
    if OUT_PATH.exists():
        with OUT_PATH.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                row["report_year"] = int(row["report_year"])
                row["month_num"] = int(row["month_num"])
                for field in FIELD_FOR_GROUP.values():
                    row[field] = int(row[field])
                existing_rows.append(row)

    combined = {(r["report_year"], r["month_num"]): r for r in existing_rows}
    combined.update(rows_by_year)

    all_rows = sorted(combined.values(), key=lambda r: (r["report_year"], r["month_num"]))
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\n{len(all_rows)} linhas na série mensal Continente (24h), {min(r['report_year'] for r in all_rows)}-{max(r['report_year'] for r in all_rows)} -> {OUT_PATH}")


if __name__ == "__main__":
    main()
