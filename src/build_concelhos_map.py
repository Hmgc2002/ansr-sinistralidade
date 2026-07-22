"""Builds a self-contained SVG-ready dataset for a concelho choropleth
map: simplifies the CAOP mainland-municipality polygons (Douglas-Peucker),
rescales them to a flat SVG coordinate space, and joins in
sinistralidade_por_concelho.csv by normalized concelho name.

Also joins in populacao_concelhos_2021.csv (built by
build_populacao_concelhos.py) to derive "acidentes por 100 mil
habitantes" — raw accident counts alone make Lisboa/Porto look
disproportionately dangerous mostly because they're bigger. That
population figure is a single 2021 snapshot applied to every year
2004-2018 alike (INE doesn't publish a concelho-level population time
series reaching back that far as open data) — a real temporal mismatch,
not a subtle one, so the derived metric is clearly labeled in the
dashboard as approximate rather than presented alongside the others
without comment.

The GeoJSON's coordinates are NOT lon/lat — despite being valid GeoJSON,
this particular file stores them already projected into a Portuguese
national grid (values like -20560.75, 113803.91 are meters, not
degrees). No re-projection is needed, just a linear rescale-and-flip
into an SVG viewBox, and Douglas-Peucker epsilon is in meters.

No external geo libraries (shapely/pyproj) are used, and none are
needed here — a plain-Python Douglas-Peucker implementation is enough
to cut point count for embedding in an HTML artifact (which cannot
fetch external tile servers or GIS libraries at runtime — the whole
map has to ship as static SVG paths).

Usage:
    python src/build_concelhos_map.py
Writes:
    data/processed/concelhos_map.json
"""
from __future__ import annotations

import csv
import json
import math
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEOJSON_PATH = ROOT / "data" / "ContinenteConcelhos.geojson"
CONCELHO_CSV = ROOT / "data" / "processed" / "sinistralidade_por_concelho.csv"
POPULACAO_CSV = ROOT / "data" / "processed" / "populacao_concelhos_2021.csv"
OUT_PATH = ROOT / "data" / "processed" / "concelhos_map.json"

SIMPLIFY_EPSILON_M = 400  # meters (native units of the source file); tune for size vs fidelity
SVG_WIDTH = 800

# The PDF-extracted concelho names in sinistralidade_por_concelho.csv
# occasionally drop a "de"/"da" or a disambiguating suffix compared to
# the official CAOP name. Mapped after normalize_name (accent-stripped,
# uppercased) on the CSV side.
NAME_ALIASES = {
    "FREIXO ESPADA A CINTA": "FREIXO DE ESPADA A CINTA",
    "SOBRAL MONTE AGRACO": "SOBRAL DE MONTE AGRACO",
    "LAGOA (ALGARVE)": "LAGOA",
}


def normalize_name(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    norm = re_sub_ws(name).strip().upper()
    return NAME_ALIASES.get(norm, norm)


def re_sub_ws(s: str) -> str:
    return " ".join(s.split())


def perpendicular_distance(pt, start, end):
    x, y = pt
    x1, y1 = start
    x2, y2 = end
    if (x1, y1) == (x2, y2):
        return math.hypot(x - x1, y - y1)
    num = abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1)
    den = math.hypot(y2 - y1, x2 - x1)
    return num / den


def douglas_peucker(points: list, epsilon: float) -> list:
    if len(points) < 3:
        return points
    dmax, index = 0.0, 0
    end = len(points) - 1
    for i in range(1, end):
        d = perpendicular_distance(points[i], points[0], points[end])
        if d > dmax:
            index, dmax = i, d
    if dmax > epsilon:
        left = douglas_peucker(points[: index + 1], epsilon)
        right = douglas_peucker(points[index:], epsilon)
        return left[:-1] + right
    return [points[0], points[end]]


def load_concelho_data() -> dict[str, dict[str, dict]]:
    """Returns {year: {normalized_concelho: row_dict}}."""
    by_year: dict[str, dict[str, dict]] = {}
    with CONCELHO_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_year.setdefault(row["ano"], {})[normalize_name(row["concelho"])] = row
    return by_year


def load_populacao() -> dict[str, int]:
    """Returns {normalized_concelho: populacao_residente_2021}."""
    if not POPULACAO_CSV.exists():
        return {}
    with POPULACAO_CSV.open(encoding="utf-8") as f:
        return {normalize_name(row["concelho"]): int(row["populacao_residente_2021"]) for row in csv.DictReader(f)}


def ring_to_points(ring: list) -> list[tuple[float, float]]:
    return [(pt[0], pt[1]) for pt in ring]


def main() -> None:
    with GEOJSON_PATH.open(encoding="utf-8-sig") as f:
        gj = json.load(f)

    xs, ys = [], []
    for feat in gj["features"]:
        geom = feat["geometry"]
        rings = geom["coordinates"] if geom["type"] == "Polygon" else [r for poly in geom["coordinates"] for r in poly]
        for ring in rings:
            xs.extend(pt[0] for pt in ring)
            ys.extend(pt[1] for pt in ring)
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    scale = SVG_WIDTH / (x_max - x_min)
    height = (y_max - y_min) * scale

    def project(x: float, y: float) -> tuple[float, float]:
        # source y increases northward; SVG y increases downward
        return round((x - x_min) * scale, 1), round((y_max - y) * scale, 1)

    concelhos = {}
    unmatched_geo = []
    for feat in gj["features"]:
        props = feat["properties"]
        raw_name = props["Concelho"]
        norm = normalize_name(raw_name)
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "Polygon" else [r for poly in geom["coordinates"] for r in poly]

        path_parts = []
        for ring in polys:
            pts = ring_to_points(ring)
            simplified = douglas_peucker(pts, SIMPLIFY_EPSILON_M)
            projected = [project(x, y) for x, y in simplified]
            d = "M" + " L".join(f"{x},{y}" for x, y in projected) + " Z"
            path_parts.append(d)

        concelhos[norm] = {
            "name": raw_name.title(),
            "distrito": props["Distrito"].title(),
            "path": " ".join(path_parts),
        }

    populacao = load_populacao()
    for norm, pop in populacao.items():
        if norm in concelhos:
            concelhos[norm]["populacao_2021"] = pop
    unmatched_pop = [norm for norm in concelhos if norm not in populacao]
    if unmatched_pop:
        print(f"Aviso: {len(unmatched_pop)} concelhos sem população 2021 correspondente: {unmatched_pop[:10]}")

    by_year = load_concelho_data()
    matched_years: dict[str, dict[str, dict]] = {}
    for year, rows in by_year.items():
        matched_years[year] = {}
        for norm, row in rows.items():
            if norm not in concelhos:
                unmatched_geo.append((year, row["concelho"]))
                continue
            acidentes_com_vitimas = int(row["acidentes_com_vitimas"])
            pop = populacao.get(norm)
            matched_years[year][norm] = {
                "acidentes_com_vitimas": acidentes_com_vitimas,
                "vitimas_mortais": int(row["vitimas_mortais"]),
                "feridos_graves": int(row["feridos_graves"]),
                "feridos_leves": int(row["feridos_leves"]),
                "total_vitimas": int(row["total_vitimas"]),
                "indice_gravidade": float(row["indice_gravidade"]),
                "acidentes_por_100k_hab": round(acidentes_com_vitimas / pop * 100_000, 1) if pop else None,
            }

    if unmatched_geo:
        print(f"Aviso: {len(unmatched_geo)} linhas do CSV sem concelho correspondente no GeoJSON:")
        for year, name in unmatched_geo[:30]:
            print(f"  {year}: {name}")

    out = {
        "viewBox": f"0 0 {SVG_WIDTH:.1f} {height:.1f}",
        "concelhos": concelhos,
        "data": matched_years,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"{len(concelhos)} concelhos, {len(matched_years)} anos -> {OUT_PATH} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
