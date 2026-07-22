"""Raw-table dump of the ANSR national annual reports for 1999-2019
(the years before the ANSR started publishing structured .xlsx annexes).

Unlike parser_xlsx.py, this does not attempt to normalize every report
into one tidy schema: PDF table layout changes noticeably across two
decades of reports (different agencies, methodologies and page designs),
so forcing a single schema here would be unreliable. Instead every table
pdfplumber can detect is dumped verbatim to CSV, tagged by year/page/
table index, with an index file for discoverability — the same approach
used for the raw xlsx dump in parser_xlsx.py.

Usage:
    python src/parser_pdf.py
Writes:
    data/processed/pdf_raw/<year>/p<page>_t<table>.csv
    data/processed/pdf_tables_index.csv
"""
from __future__ import annotations

import csv
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PDF_RAW_OUT = ROOT / "data" / "processed" / "pdf_raw"
INDEX_OUT = ROOT / "data" / "processed" / "pdf_tables_index.csv"

# One national annual report per year, manually resolved from the
# manifest (each year originally lists district reports plus 1-2
# national variants; where both a "30 dias" and "24 horas" methodology
# exist, the "30 dias" one is picked for consistency with parser_xlsx.py,
# which uses the same convention for 2020-2024).
NATIONAL_REPORT_BY_YEAR = {
    "1999": "Relatório Anual 1999 (PDF).pdf",
    "2000": "Relatório Anual 2000 (PDF).pdf",
    "2001": "Relatório Anual 2001(PDF).pdf",
    "2002": "Relatório Anual 2002 (PDF).pdf",
    "2003": "Relatório Anual 2003 (PDF).pdf",
    "2004": "Relatório Anual 2004 (PDF).pdf",
    "2005": "Relatório Anual 2005 (PDF).pdf",
    "2006": "Relatório Anual 2006 (PDF).pdf",
    "2007": "Relatório Anual 2007.pdf",
    "2008": "Relatório Anual 2008.pdf",
    "2009": "Relatório Anual 2009.pdf",
    "2010": "RelatorioNacional_Vitimas30Dias_2010.pdf",
    "2011": "Relatório Nacional Anual 2011- Vítimas a 30 dias.pdf",
    "2012": "Relatório Nacional Anual 2012- Vítimas a 30 dias.pdf",
    "2013": "Relatório Nacional Anual 2013- Vítimas a 30 dias.pdf",
    "2014": "Relatório Anual de Sinistralidade Rodoviária - 2014.pdf",
    "2015": "Rel2015_anual30dias.pdf",
    "2016": "Relatório Anual Sinistralidade Rodoviária 2016 30d.pdf",
    "2017": "Relatório Anual Sinistralidade Rodoviária 30dias.pdf",
    "2018": "Relatório Anual Sinistralidade Rodoviária 2018 - 30 dias.pdf",
    "2019": "Relatório Anual Sinistralidade Rodoviária 2019.pdf",
}


def dump_pdf_tables(path: Path, year: str, index_rows: list[dict]) -> int:
    out_dir = PDF_RAW_OUT / year
    out_dir.mkdir(parents=True, exist_ok=True)
    n_tables = 0

    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for t_idx, table in enumerate(tables):
                if not table or all(all(c is None for c in row) for row in table):
                    continue
                out_path = out_dir / f"p{page_num:03d}_t{t_idx}.csv"
                with out_path.open("w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerows(table)
                preview = " | ".join(str(c) for c in table[0] if c)[:80]
                n_rows = len(table)
                n_cols = max(len(r) for r in table)
                index_rows.append(
                    {
                        "year": year,
                        "source_file": path.name,
                        "page": page_num,
                        "table_index": t_idx,
                        "rows": n_rows,
                        "cols": n_cols,
                        # a 1-row or 1-column "table" is almost always a
                        # chart axis/legend or a wrapped paragraph that
                        # pdfplumber's grid detector mistook for tabular
                        # data, not a flag to drop it — kept in the dump,
                        # just marked so a search over the index can filter
                        # it out
                        "provavel_ruido": n_rows == 1 or n_cols == 1,
                        "csv_path": str(out_path.relative_to(ROOT)),
                        "first_row_preview": preview,
                    }
                )
                n_tables += 1
    return n_tables


def main() -> None:
    index_rows: list[dict] = []

    for year, filename in NATIONAL_REPORT_BY_YEAR.items():
        path = RAW_DIR / year / filename
        if not path.exists():
            print(f"[{year}] aviso: ficheiro não encontrado: {path}")
            continue
        print(f"[{year}] a processar {filename} ...")
        n = dump_pdf_tables(path, year, index_rows)
        print(f"[{year}] {n} tabelas extraídas")

    if not index_rows:
        print("Nenhuma tabela extraída.")
        return

    INDEX_OUT.parent.mkdir(parents=True, exist_ok=True)
    with INDEX_OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(index_rows[0].keys()))
        writer.writeheader()
        writer.writerows(index_rows)

    print(f"\n{len(index_rows)} tabelas catalogadas -> {INDEX_OUT}")


if __name__ == "__main__":
    main()
