"""Downloads INE's national motor-vehicle fleet size by year — used to
normalize accident counts by fleet size ("acidentes por 1000 veículos"),
since the raw annual/monthly series makes 2019 look far more dangerous
than 1999 partly just because there are many more vehicles on the road
now, the same exposure problem behind the concelho population
normalization.

Source: INE indicator 0007244 ("Veículos rodoviários motorizados (Nº)
por Tipo de veículo e Tipo de combustível; Anual"), JSON API:
https://www.ine.pt/ine/json_indicador/pindica.jsp?op=2&varcd=0007244
CC BY 4.0. Only the "Total" x "Total" breakdown (dim_3=T, dim_4=T) is
kept — the source also splits by vehicle type (ligeiros/pesados/
motociclos/...) and fuel type, not needed here.

Coverage: 2010-2024, national only — no district/concelho breakdown,
and INE doesn't publish this indicator further back as open data, so
this can't reach the 1975-2009 stretch of the annual series or the
2025 months of the monthly series.

Usage:
    python src/build_frota_veiculos.py
Writes:
    data/processed/frota_veiculos.csv
"""
from __future__ import annotations

import csv
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "processed" / "frota_veiculos.csv"

YEARS = range(2010, 2025)
SOURCE_URL = (
    "https://www.ine.pt/ine/json_indicador/pindica.jsp?op=2&varcd=0007244"
    "&Dim1=" + ",".join(f"S7A{y}" for y in YEARS)
    + "&lang=PT"
)
TIMEOUT = 60
USER_AGENT = (
    "ansr-sinistralidade-scraper/0.1 "
    "(uso pessoal/pesquisa; contacto: hmgc2016@proton.me)"
)


def main() -> None:
    resp = requests.get(SOURCE_URL, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    data = resp.json()[0]["Dados"]

    rows = []
    for year in YEARS:
        year_rows = data.get(str(year), [])
        total_row = next(
            (r for r in year_rows if r["dim_3"] == "T" and r["dim_4"] == "T"),
            None,
        )
        if total_row is None:
            print(f"[{year}] aviso: linha Total/Total não encontrada")
            continue
        rows.append({"ano": year, "total_veiculos": int(total_row["valor"])})

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ano", "total_veiculos"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} anos ({rows[0]['ano']}-{rows[-1]['ano']}) -> {OUT_PATH}")


if __name__ == "__main__":
    main()
