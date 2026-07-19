"""Builds a manifest of every document listed on the ANSR 'Relatórios de
Sinistralidade' page (year, title, url, filename, extension).

Usage:
    python src/scraper.py
Writes:
    data/processed/manifest.csv
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

import requests
from bs4 import BeautifulSoup

REPORTS_URL = "http://www.ansr.pt/Estatisticas/RelatoriosDeSinistralidade"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "manifest.csv"
TIMEOUT = 30
USER_AGENT = (
    "ansr-sinistralidade-scraper/0.1 "
    "(uso pessoal/pesquisa; contacto: hmgc2016@proton.me)"
)


def fetch_html(url: str) -> str:
    resp = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def parse_manifest(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []

    items = soup.select("div.item")
    for item in items:
        h3 = item.find("h3")
        if not h3:
            continue
        year_text = h3.get_text(strip=True)
        if not re.fullmatch(r"\d{4}", year_text):
            continue

        data_div = item.find_next_sibling("div", class_="item-data")
        if not data_div:
            continue

        for a in data_div.select("a[href]"):
            url = a["href"].strip()
            title = a.get_text(strip=True)
            filename = unquote(Path(urlparse(url).path).name)
            extension = Path(filename).suffix.lower().lstrip(".")
            rows.append(
                {
                    "year": year_text,
                    "title": title,
                    "url": url,
                    "filename": filename,
                    "extension": extension,
                    "is_annex_xlsx": extension in ("xlsx", "xls"),
                }
            )
    return rows


def main() -> None:
    html = fetch_html(REPORTS_URL)
    rows = parse_manifest(html)
    if not rows:
        print("Aviso: nenhum documento encontrado — a estrutura da página pode ter mudado.", file=sys.stderr)
        sys.exit(1)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} documentos catalogados -> {OUT_PATH}")


if __name__ == "__main__":
    main()
