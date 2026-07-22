"""Combines the two national time-series datasets — the annual
1975-2019 history and the monthly 2020-2025 series — into the single
compact JSON that dashboard/serie_nacional.html embeds. Both source
CSVs are already small (45 and 69 rows), so this mostly just reshapes
them for direct use by the chart code, plus one derived view (average
per calendar month across 2020-2024, a full-year lens the monthly data
doesn't show on its own — 2025 is excluded from it since the year
isn't complete yet and would skew the later months' averages down).

Usage:
    python src/build_serie_nacional_dashboard_data.py
Writes:
    data/processed/serie_nacional_dashboard_data.json
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANUAL_PATH = ROOT / "data" / "processed" / "serie_anual_nacional.csv"
MENSAL_PATH = ROOT / "data" / "processed" / "sinistralidade_mensal.csv"
CONTINENTE_24H_PATH = ROOT / "data" / "processed" / "sinistralidade_mensal_continente_24h.csv"
ALCOOLEMIA_PATH = ROOT / "data" / "processed" / "condutores_alcoolemia.csv"
OUT_PATH = ROOT / "data" / "processed" / "serie_nacional_dashboard_data.json"

MONTH_LABELS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    anual = read_csv(ANUAL_PATH)
    mensal = read_csv(MENSAL_PATH)
    continente_24h = read_csv(CONTINENTE_24H_PATH)
    alcoolemia = read_csv(ALCOOLEMIA_PATH)

    serie_anual = [
        {
            "ano": r["ano"],
            "vitimas_mortais": int(r["vitimas_mortais"]) if r["vitimas_mortais"] else None,
            "indice_gravidade": float(r["indice_gravidade"]) if r["indice_gravidade"] else None,
            "acidentes_com_vitimas": int(r["acidentes_com_vitimas"]) if r["acidentes_com_vitimas"] else None,
        }
        for r in anual
    ]

    serie_mensal = [
        {
            "report_year": r["report_year"],
            "month_num": int(r["month_num"]),
            "acidentes_com_vitimas": int(r["acidentes_com_vitimas"]),
            "vitimas_mortais": int(r["vitimas_mortais"]),
            "feridos_graves": int(r["feridos_graves"]),
        }
        for r in mensal
    ]

    # average per calendar month, 2020-2024 only (2025 incomplete)
    by_month: dict[int, list[int]] = defaultdict(list)
    for r in serie_mensal:
        if r["report_year"] != "2025":
            by_month[r["month_num"]].append(r["acidentes_com_vitimas"])
    sazonalidade = [
        {"mes": MONTH_LABELS[m - 1], "media_acidentes": round(sum(v) / len(v))}
        for m, v in sorted(by_month.items())
    ]

    serie_continente_24h = [
        {
            "report_year": r["report_year"],
            "month_num": int(r["month_num"]),
            "acidentes_com_vitimas": int(r["acidentes_com_vitimas"]),
            "vitimas_mortais": int(r["vitimas_mortais"]),
        }
        for r in continente_24h
    ]

    serie_alcoolemia = [
        {
            "ano": r["ano"],
            "total_condutores_intervenientes": int(r["total_condutores_intervenientes"]),
            "total_testados": int(r["total_testados"]),
            "total_infratores": int(r["total_infratores"]),
            "pct_testados": float(r["pct_testados"]),
            "pct_infratores_entre_testados": float(r["pct_infratores_entre_testados"]),
        }
        for r in alcoolemia
    ]

    out = {
        "serie_anual": serie_anual,
        "serie_mensal": serie_mensal,
        "sazonalidade": sazonalidade,
        "serie_continente_24h": serie_continente_24h,
        "serie_alcoolemia": serie_alcoolemia,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)

    print(f"{len(serie_anual)} anos + {len(serie_mensal)} meses -> {OUT_PATH}")


if __name__ == "__main__":
    main()
