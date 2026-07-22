"""Downloads INE's national-road-network length by district — used to
normalize accident counts by network exposure ("acidentes por km de
estrada"), a different lens than the population normalization already
in the concelho map: this measures risk relative to how much road there
is, not how many people live there (a district can have few residents
but a lot of transit highway, or vice-versa).

Source: INE indicator 0002129 ("Extensão da rede nacional rodoviária
(km) por Localização geográfica (Distrito) e Tipo de rede rodoviária;
Anual", from IMT), JSON API:
https://www.ine.pt/ine/json_indicador/pindica.jsp?op=2&varcd=0002129
CC BY 4.0. Only the "T" ("Rede nacional", i.e. every road type summed)
breakdown is kept; the source also splits by itinerário principal/
complementar/estrada nacional/regional, not needed here.

Two methodology breaks documented by INE itself, carried into the
dashboard caveat rather than smoothed over: the source changed from
"Estradas de Portugal, S.A." to IMT after 2010, and the road
classification/counting methodology was revised in 2012.

Coverage: 2007-2024, by district (18 mainland + "Continente", the
latter dropped here — every other dataset in this project is
mainland-only already). Doesn't reach back to 2004-2006, the first
three years of sinistralidade_por_concelho.csv — those are left
unnormalized rather than backfilled with a guess.

Usage:
    python src/build_extensao_rede_distrito.py
Writes:
    data/processed/extensao_rede_distrito.csv
"""
from __future__ import annotations

import csv
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "processed" / "extensao_rede_distrito.csv"

YEARS = range(2007, 2025)
SOURCE_URL = (
    "https://www.ine.pt/ine/json_indicador/pindica.jsp?op=2&varcd=0002129"
    "&Dim1=" + ",".join(f"S13A{y}1231" for y in YEARS)
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
        key = f"31 de Dezembro de {year}"
        year_rows = data.get(key, [])
        totals = [r for r in year_rows if r["dim_3"] == "T" and r["geocod"] != "1"]
        if len(totals) != 18:
            print(f"[{year}] aviso: esperava 18 distritos, encontrei {len(totals)}")
        for r in totals:
            rows.append({"ano": year, "distrito": r["geodsg"], "extensao_km": int(r["valor"])})

    rows.sort(key=lambda r: (r["ano"], r["distrito"]))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ano", "distrito", "extensao_km"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} linhas ({YEARS[0]}-{YEARS[-1]}, 18 distritos) -> {OUT_PATH}")


if __name__ == "__main__":
    main()
