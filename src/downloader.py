"""Downloads every file listed in data/processed/manifest.csv into
data/raw/<year>/<filename>, skipping files already present so the script
is safe to re-run (resumable).

Usage:
    python src/downloader.py [--delay 0.5]
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "data" / "processed" / "manifest.csv"
RAW_DIR = ROOT / "data" / "raw"
TIMEOUT = 60
USER_AGENT = (
    "ansr-sinistralidade-scraper/0.1 "
    "(uso pessoal/pesquisa; contacto: hmgc2016@proton.me)"
)

_ILLEGAL_WINDOWS_CHARS = re.compile(r'[<>:"|?*]')


def safe_filename(name: str) -> str:
    return _ILLEGAL_WINDOWS_CHARS.sub("_", name).strip()


def download_one(session: requests.Session, url: str, dest: Path) -> str:
    if dest.exists() and dest.stat().st_size > 0:
        return "skip (já existe)"
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = session.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(resp.content)
    tmp.replace(dest)
    return "ok"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=0.5, help="segundos entre pedidos")
    args = parser.parse_args()

    if not MANIFEST_PATH.exists():
        print(f"Manifesto não encontrado: {MANIFEST_PATH}. Corre primeiro src/scraper.py.", file=sys.stderr)
        sys.exit(1)

    with MANIFEST_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    session = requests.Session()
    ok = skipped = failed = 0

    for i, row in enumerate(rows, 1):
        year = row["year"]
        filename = safe_filename(row["filename"])
        dest = RAW_DIR / year / filename
        try:
            status = download_one(session, row["url"], dest)
        except requests.RequestException as exc:
            status = f"falhou ({exc})"

        print(f"[{i}/{len(rows)}] {year}/{filename}: {status}")
        if status == "ok":
            ok += 1
            time.sleep(args.delay)
        elif status.startswith("skip"):
            skipped += 1
        else:
            failed += 1

    print(f"\nConcluído: {ok} descarregados, {skipped} já existiam, {failed} falharam.")


if __name__ == "__main__":
    main()
