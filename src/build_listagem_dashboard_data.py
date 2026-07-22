"""Pre-aggregates listagem_acidentes.csv (32488 individual accident
records) into the compact summary JSON that dashboard/listagem.html
embeds. Not embedding the raw rows keeps the dashboard's payload small:
the interesting signal here is in the aggregate patterns (trend by
year, hour of day, day of week, accident type, district), not in
browsing all 32k records one by one — the same reasoning already
applied to the concelho choropleth (which embeds per-concelho-year
aggregates, not raw PDF text).

Usage:
    python src/build_listagem_dashboard_data.py
Writes:
    data/processed/listagem_dashboard_data.json
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IN_PATH = ROOT / "data" / "processed" / "listagem_acidentes.csv"
OUT_PATH = ROOT / "data" / "processed" / "listagem_dashboard_data.json"

WEEKDAY_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

# Ordered most-specific-first: a natureza mentioning "atropel" is always
# that, regardless of any other word it also contains; a plain "despiste"
# is checked after the colisão sub-types so "despiste com capotamento"
# still lands under despiste (the primary mechanism), not capotamento
# (usually just a consequence mentioned in the same phrase).
NATUREZA_CATEGORIES = [
    ("Atropelamento", re.compile(r"atropel", re.IGNORECASE)),
    ("Colisão frontal", re.compile(r"colis.*frontal|frontal.*colis", re.IGNORECASE)),
    ("Colisão traseira", re.compile(r"colis.*tras|tras.*colis", re.IGNORECASE)),
    ("Colisão lateral", re.compile(r"colis.*later|later.*colis", re.IGNORECASE)),
    ("Outra colisão", re.compile(r"colis|col\.", re.IGNORECASE)),
    ("Despiste", re.compile(r"despiste|desp\.", re.IGNORECASE)),
    ("Capotamento", re.compile(r"capotamento|capot\.", re.IGNORECASE)),
]


def categorize_natureza(text: str) -> str:
    if not text:
        return "Não especificado"
    for label, pattern in NATUREZA_CATEGORIES:
        if pattern.search(text):
            return label
    return "Outro"


def main() -> None:
    with IN_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    total = len(rows)
    total_mortos = sum(int(r["mortos"]) for r in rows)
    total_fg = sum(int(r["feridos_graves"]) for r in rows)
    anos = sorted({r["ano"] for r in rows})
    distritos = sorted({r["distrito"] for r in rows})

    by_year = defaultdict(lambda: {"acidentes": 0, "mortos": 0, "feridos_graves": 0})
    by_hour = Counter()
    by_weekday = Counter()
    by_natureza = Counter()
    by_district = defaultdict(lambda: {"acidentes": 0, "mortos": 0, "feridos_graves": 0})
    parse_errors = 0

    for r in rows:
        ano = r["ano"]
        mortos = int(r["mortos"])
        fg = int(r["feridos_graves"])

        y = by_year[ano]
        y["acidentes"] += 1
        y["mortos"] += mortos
        y["feridos_graves"] += fg

        d = by_district[r["distrito"]]
        d["acidentes"] += 1
        d["mortos"] += mortos
        d["feridos_graves"] += fg

        by_natureza[categorize_natureza(r["natureza"])] += 1

        if r["hora"]:
            try:
                hour = int(r["hora"].split(":")[0])
                by_hour[hour] += 1
            except ValueError:
                parse_errors += 1

        try:
            y_, m_, d_ = (int(x) for x in r["data"].split("-"))
            weekday = date(y_, m_, d_).weekday()
            by_weekday[weekday] += 1
        except ValueError:
            parse_errors += 1

    # top 20 most severe individual accidents (mortos+feridos_graves desc)
    top_severe = sorted(
        rows, key=lambda r: (int(r["mortos"]), int(r["feridos_graves"])), reverse=True
    )[:20]
    top_severe_out = [
        {
            "distrito": r["distrito"], "concelho": r["concelho"], "ano": r["ano"],
            "data": r["data"], "mortos": int(r["mortos"]), "feridos_graves": int(r["feridos_graves"]),
            "via": r["via"], "natureza": r["natureza"],
        }
        for r in top_severe
    ]

    out = {
        "total": total,
        "total_mortos": total_mortos,
        "total_feridos_graves": total_fg,
        "anos": anos,
        "n_distritos": len(distritos),
        "por_ano": [
            {"ano": a, **by_year[a]} for a in anos
        ],
        "por_hora": [{"hora": h, "acidentes": by_hour.get(h, 0)} for h in range(24)],
        "por_dia_semana": [
            {"dia": WEEKDAY_PT[i], "acidentes": by_weekday.get(i, 0)} for i in range(7)
        ],
        "por_natureza": sorted(
            ({"tipo": k, "acidentes": v} for k, v in by_natureza.items()),
            key=lambda x: x["acidentes"], reverse=True,
        ),
        "por_distrito": sorted(
            ({"distrito": k, **v} for k, v in by_district.items()),
            key=lambda x: x["mortos"] + x["feridos_graves"], reverse=True,
        ),
        "top_severos": top_severe_out,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)

    print(f"{total} registos agregados ({parse_errors} erros de parsing de data/hora) -> {OUT_PATH}")


if __name__ == "__main__":
    main()
