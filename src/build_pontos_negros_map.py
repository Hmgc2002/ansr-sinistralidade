"""Projects the geocoded Pontos Negros records onto the same SVG canvas
as the concelho choropleth map, so dashboard/pontos_negros.html can show
an actual map of Portugal instead of a per-row link out to OpenStreetMap.

Reuses concelhos_map.json's already-simplified concelho outlines as a
neutral backdrop (all 278 paths in one color, not a choropleth — this
dashboard has no per-concelho metric to color by) and its projection
parameters (x_min, y_max, scale — persisted by build_concelhos_map.py
specifically so this script doesn't need to re-parse the 36.5 MB source
GeoJSON on its own). geocode_pontos_negros.py stored each point as
WGS84 lat/lon (the standard the OpenStreetMap links need), so this
reprojects back to EPSG:3763 with pyproj before applying the shared
linear projection.

Usage:
    python src/build_pontos_negros_map.py
Writes:
    data/processed/pontos_negros_map.json
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
CONCELHOS_MAP_PATH = ROOT / "data" / "processed" / "concelhos_map.json"
PONTOS_NEGROS_CSV = ROOT / "data" / "processed" / "pontos_negros.csv"
OUT_PATH = ROOT / "data" / "processed" / "pontos_negros_map.json"

_TO_PT_TM06 = Transformer.from_crs("EPSG:4326", "EPSG:3763", always_xy=True)


def main() -> None:
    with CONCELHOS_MAP_PATH.open(encoding="utf-8") as f:
        concelhos_map = json.load(f)
    proj = concelhos_map["projection"]
    x_min, y_max, scale = proj["x_min"], proj["y_max"], proj["scale"]

    def project(x: float, y: float) -> tuple[float, float]:
        return round((x - x_min) * scale, 1), round((y_max - y) * scale, 1)

    backdrop = " ".join(c["path"] for c in concelhos_map["concelhos"].values())

    with PONTOS_NEGROS_CSV.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    points = []
    for row in rows:
        if not row["lat"] or not row["lon"]:
            continue
        x_3763, y_3763 = _TO_PT_TM06.transform(float(row["lon"]), float(row["lat"]))
        px, py = project(x_3763, y_3763)
        points.append(
            {
                "x": px,
                "y": py,
                "year": row["year"],
                "entidade_gestora": row["entidade_gestora"],
                "estrada": row["estrada"],
                "km": row["km"],
                "estado_intervencao": row["estado_intervencao"],
                "geocoding_precisao_km": row["geocoding_precisao_km"],
            }
        )

    out = {
        "viewBox": concelhos_map["viewBox"],
        "backdrop": backdrop,
        "points": points,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"{len(points)} pontos projetados -> {OUT_PATH} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
