"""Downloads and tidies INE's resident-population-by-concelho dataset
(2021 Census) — used to normalize accident counts by population (e.g.
"acidentes por 100 mil habitantes"), since raw counts make Lisboa/Porto
look disproportionately dangerous mostly because they're bigger, not
necessarily riskier per resident.

Source: https://dados.gov.pt/en/datasets/populacao-residente-no-por-concelho-censos-2021/
A single snapshot (31/12/2021), not an annual series — INE doesn't
publish concelho-level population as a clean open time series for
2004-2018, the years sinistralidade_por_concelho.csv covers (only
district-level series go back that far as open data; concelho-level
annual estimates for older years exist only as INE PDF yearbooks). Every
year in that CSV therefore gets normalized against the *same* 2021
figure — a real temporal mismatch, not a subtle one, flagged wherever
this is used (see the dashboard caveat and README), not silently assumed
away.

Mainland only (278 concelhos) — the Azores/Madeira rows are dropped,
matching every other dataset in this project's geographic scope.

Usage:
    python src/build_populacao_concelhos.py
Writes:
    data/processed/populacao_concelhos_2021.csv
"""
from __future__ import annotations

import csv
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "processed" / "populacao_concelhos_2021.csv"

SOURCE_URL = (
    "https://dados.gov.pt/s/resources/populacao-residente-no-por-concelho-censos-2021/"
    "20251001-141259/populacao-por-concelho-censos-2021.csv"
)
TIMEOUT = 60
USER_AGENT = (
    "ansr-sinistralidade-scraper/0.1 "
    "(uso pessoal/pesquisa; contacto: hmgc2016@proton.me)"
)
MAINLAND_NUTS_II = {"Norte", "Centro", "Área Metropolitana de Lisboa", "Alentejo", "Algarve"}


def main() -> None:
    resp = requests.get(SOURCE_URL, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    resp.encoding = "windows-1252"
    rows = list(csv.DictReader(resp.text.splitlines()))

    out = [
        {
            "concelho": r["Designação Concelho"].strip(),
            "distrito": r["Designação Distrito"].strip(),
            "populacao_residente_2021": int(r["População residente (Nº)"]),
        }
        for r in rows
        if r["Designação NUTSII"].strip() in MAINLAND_NUTS_II
    ]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["concelho", "distrito", "populacao_residente_2021"])
        writer.writeheader()
        writer.writerows(out)
    print(f"{len(out)} concelhos (Continente) -> {OUT_PATH}")


if __name__ == "__main__":
    main()
