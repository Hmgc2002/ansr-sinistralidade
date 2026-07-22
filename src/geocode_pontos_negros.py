"""Adds approximate coordinates to pontos_negros.csv by cross-referencing
each record's estrada + km against the official kilometre-marker layer
("Marcos Quilométricos") from Infraestruturas de Portugal's own public GIS
service (SIGIP) — the "additional geocoding source" the README previously
flagged as needed and unexplored.

Source: https://sigip.infraestruturasdeportugal.pt/pub/rest/services/MOBILE_DRR/EQUIVIA/MapServer/0
(an ArcGIS REST feature layer, ~16k point markers nationwide, EPSG:3763 —
PT-TM06/ETRS89). Not affiliated with ANSR; a separate open dataset from a
different public entity (IP), used only to translate estrada+km into a
point.

Method: markers are ~1km apart along each road. For a record's km range,
this takes the midpoint and linearly interpolates between the two nearest
markers bracketing it on the same road (matched on IP's own numbering,
e.g. "EN106", spaces stripped) — a straight line between two points on a
curved road, not a road-following snap. The gap between those two markers
is kept as `geocoding_precisao_km`: the record's coordinates are only
written when that gap is <= PRECISION_THRESHOLD_KM; readers can decide for
themselves whether to trust a wider precision report, but nothing here is
silently invented past that threshold.

Two structural gaps, by design, not fixed by picking a lower threshold:
- Privately-concessioned motorways (A2, A3, A5 in this dataset) aren't in
  IP's own marker layer at all — it only surveys the roads IP itself
  manages directly. Some national roads (EN125, EN378, IC20) are missing
  too, for reasons not stated by the source.
- A handful of IP-managed roads (A1, EN10, EN206, EN106) have markers tens
  of km apart in the relevant stretch, which would need snapping to the
  actual road centerline (not just the two nearest markers) to place a
  trustworthy point — out of scope here, left ungeocoded rather than
  guessed at.

Usage:
    python src/geocode_pontos_negros.py
Writes:
    data/processed/pontos_negros.csv (adds lat, lon, geocoding_precisao_km)
"""
from __future__ import annotations

import csv
import re
import time
from collections import defaultdict
from pathlib import Path

import requests
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "processed" / "pontos_negros.csv"

MARKERS_URL = (
    "https://sigip.infraestruturasdeportugal.pt/pub/rest/services/"
    "MOBILE_DRR/EQUIVIA/MapServer/0/query"
)
PAGE_SIZE = 1000
PRECISION_THRESHOLD_KM = 5.0

_TRANSFORMER = Transformer.from_crs("EPSG:3763", "EPSG:4326", always_xy=True)


def fetch_markers() -> dict[str, list[tuple[float, float, float]]]:
    """Returns {n_via: [(km, x, y), ...]} sorted by km, for every marker
    with a known road number and km value."""
    by_road: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    offset = 0
    while True:
        params = {
            "where": "1=1",
            "outFields": "n_via,quilometragem",
            "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE,
            "f": "json",
        }
        resp = requests.get(MARKERS_URL, params=params, timeout=60)
        resp.raise_for_status()
        features = resp.json().get("features", [])
        for feat in features:
            attrs = feat["attributes"]
            geom = feat.get("geometry")
            km = attrs.get("quilometragem")
            road = attrs.get("n_via")
            if geom is None or km is None or not road:
                continue
            by_road[road].append((float(km), geom["x"], geom["y"]))
        if len(features) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.2)

    for road in by_road:
        by_road[road].sort(key=lambda t: t[0])
    return by_road


def parse_km_midpoint(text: str) -> float | None:
    """Handles every format seen in the field: comma or dot decimals, a
    stray '190+400' PK notation, an omitted 'Km' on the second value, and
    trailing 'Cres.'/'Dec.' direction markers."""

    def to_float(token: str) -> float:
        if "+" in token:
            whole, frac = token.split("+", 1)
            return float(whole) + float(re.sub(r"\D", "", frac)) / 1000
        return float(token.replace(",", "."))

    nums = re.findall(r"\d+(?:[.,+]\d+)*", text.strip())
    if len(nums) < 2:
        return None
    try:
        start, end = to_float(nums[0]), to_float(nums[1])
    except ValueError:
        return None
    return (start + end) / 2


def geocode(markers: list[tuple[float, float, float]], km: float) -> tuple[float, float, float] | None:
    """Returns (lat, lon, precisao_km) or None if this road has no markers."""
    if not markers:
        return None
    lo = hi = None
    for m in markers:
        if m[0] <= km:
            lo = m
        if m[0] >= km and hi is None:
            hi = m
    lo = lo or hi
    hi = hi or lo
    if lo[0] == hi[0]:
        x, y, precisao = lo[1], lo[2], 0.0
    else:
        frac = (km - lo[0]) / (hi[0] - lo[0])
        x = lo[1] + frac * (hi[1] - lo[1])
        y = lo[2] + frac * (hi[2] - lo[2])
        precisao = hi[0] - lo[0]
    lon, lat = _TRANSFORMER.transform(x, y)
    return lat, lon, precisao


def main() -> None:
    print("A obter marcos quilométricos do SIGIP (IP)...")
    by_road = fetch_markers()
    print(f"{sum(len(v) for v in by_road.values())} marcos em {len(by_road)} vias")

    with OUT_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    n_geocoded = 0
    for row in rows:
        row["lat"] = ""
        row["lon"] = ""
        row["geocoding_precisao_km"] = ""

        road = row["estrada"].replace(" ", "").strip()
        markers = by_road.get(road)
        km = parse_km_midpoint(row["km"]) if row["km"] else None
        if not markers or km is None:
            continue
        result = geocode(markers, km)
        if result is None:
            continue
        lat, lon, precisao = result
        if precisao > PRECISION_THRESHOLD_KM:
            continue
        row["lat"] = f"{lat:.5f}"
        row["lon"] = f"{lon:.5f}"
        row["geocoding_precisao_km"] = f"{precisao:.2f}"
        n_geocoded += 1

    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"{n_geocoded}/{len(rows)} registos geocodificados (precisão <= {PRECISION_THRESHOLD_KM} km) -> {OUT_PATH}")


if __name__ == "__main__":
    main()
