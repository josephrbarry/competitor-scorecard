"""
SEC EDGAR access layer.

Everything that talks to sec.gov goes through this module so the fair-access
rules are enforced in one place:
  * a User-Agent identifying the requester (SEC_USER_AGENT in .env),
  * no more than 10 requests per second (we use ~5),
  * every response cached under data/raw/ and recorded in data/raw/manifest.csv.

Usage (from the repo root, inside the venv):
    python -m src.edgar tickers            # refresh the ticker -> CIK map
    python -m src.edgar submissions KR     # filing index for one company
    python -m src.edgar companyfacts KR    # all XBRL facts for one company
    python -m src.edgar filing KR 10-K 2026-01-31   # primary 10-K document
"""

from __future__ import annotations

import csv
import gzip
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
MANIFEST = RAW / "manifest.csv"
CONFIG = ROOT / "config" / "companies.yaml"

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
FRAMES_URL = "https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/USD/{frame}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"

MIN_INTERVAL_SECONDS = 0.2  # 5 requests/second, half the SEC ceiling
_last_request_at = 0.0


def user_agent() -> str:
    """Read the SEC User-Agent from .env; refuse to run without one."""
    load_dotenv(ROOT / ".env")
    ua = os.getenv("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        sys.exit(
            "SEC_USER_AGENT is not set. Copy .env.example to .env and enter "
            "'Your Name your.email@example.com' (the SEC requires it)."
        )
    return ua


def load_config() -> dict:
    with open(CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _throttle() -> None:
    global _last_request_at
    wait = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _record(url: str, path: Path, nbytes: int) -> None:
    """Append one line to the manifest so every download is documented."""
    new = not MANIFEST.exists()
    with open(MANIFEST, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["retrieved_utc", "url", "local_path", "bytes"])
        w.writerow(
            [
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                url,
                path.relative_to(ROOT).as_posix(),
                nbytes,
            ]
        )


def fetch(url: str, path: Path, refresh: bool = False) -> bytes:
    """GET `url` into `path` (cached). Returns the raw bytes."""
    if path.exists() and not refresh:
        return path.read_bytes()
    last_err: Exception | None = None
    for attempt in range(4):  # the SEC occasionally drops a connection; back off and retry
        _throttle()
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"},
                timeout=60,
            )
            resp.raise_for_status()
            break
        except (requests.ConnectionError, requests.Timeout) as err:
            last_err = err
            time.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError(f"gave up on {url}") from last_err
    data = resp.content
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    _record(url, path, len(data))
    return data


def fetch_json(url: str, path: Path, refresh: bool = False) -> dict:
    data = fetch(url, path, refresh)
    if data[:2] == b"\x1f\x8b":  # gzip magic, in case requests didn't decode
        data = gzip.decompress(data)
    return json.loads(data)


# ---------------------------------------------------------------- endpoints


def tickers(refresh: bool = False) -> dict[str, dict]:
    """Ticker -> {'cik': int, 'title': str} from the SEC's own map."""
    raw = fetch_json(TICKERS_URL, RAW / "company_tickers.json", refresh)
    return {v["ticker"]: {"cik": v["cik_str"], "title": v["title"]} for v in raw.values()}


def submissions(cik: int, refresh: bool = False) -> dict:
    """Filing index for one company, including the older-filing index files.

    The `recent` block only holds the latest ~1000 filings; older ones sit in
    separate JSON files listed under filings.files. We merge them so a search
    for FY2016 10-Ks works for companies like Walmart that file constantly.
    """
    name = f"CIK{cik:010d}.json"
    sub = fetch_json(SUBMISSIONS_URL.format(name=name), RAW / str(cik) / name, refresh)
    merged = {k: list(v) for k, v in sub["filings"]["recent"].items()}
    for extra in sub["filings"].get("files", []):
        older = fetch_json(
            SUBMISSIONS_URL.format(name=extra["name"]), RAW / str(cik) / extra["name"], refresh
        )
        for k in merged:
            merged[k].extend(older.get(k, []))
    sub["filings"]["all"] = merged
    return sub


def list_filings(cik: int, form: str = "10-K") -> list[dict]:
    """[{'form','filingDate','reportDate','accessionNumber','primaryDocument'}] newest first."""
    f = submissions(cik)["filings"]["all"]
    rows = [
        {
            "form": f["form"][i],
            "filingDate": f["filingDate"][i],
            "reportDate": f["reportDate"][i],
            "accessionNumber": f["accessionNumber"][i],
            "primaryDocument": f["primaryDocument"][i],
        }
        for i in range(len(f["form"]))
        if f["form"][i] == form
    ]
    return sorted(rows, key=lambda r: r["filingDate"], reverse=True)


def companyfacts(cik: int, refresh: bool = False) -> dict:
    """All XBRL facts for one company (no dimensions - see extract_categories.py)."""
    return fetch_json(COMPANYFACTS_URL.format(cik=cik), RAW / str(cik) / "companyfacts.json", refresh)


def frame(tag: str, frame_id: str, refresh: bool = False) -> dict:
    """One tag across all filers for one period, e.g. frame('Revenues', 'CY2024')."""
    return fetch_json(FRAMES_URL.format(tag=tag, frame=frame_id), RAW / "frames" / f"{tag}_{frame_id}.json", refresh)


def filing_document(cik: int, accession: str, doc: str, refresh: bool = False) -> bytes:
    """Any file inside a filing folder: the primary 10-K HTML, or the XBRL instance."""
    acc = accession.replace("-", "")
    return fetch(ARCHIVE_URL.format(cik=cik, acc=acc, doc=doc), RAW / str(cik) / acc / doc, refresh)


def filing_index(cik: int, accession: str, refresh: bool = False) -> dict:
    """The filing's index.json - lists every file in the folder (to find the XBRL instance)."""
    acc = accession.replace("-", "")
    url = ARCHIVE_URL.format(cik=cik, acc=acc, doc="index.json")
    return fetch_json(url, RAW / str(cik) / acc / "index.json", refresh)


# ---------------------------------------------------------------- CLI


def _cik_for(ticker: str) -> int:
    cfg = load_config()["companies"]
    if ticker not in cfg:
        sys.exit(f"{ticker} is not in config/companies.yaml")
    return int(cfg[ticker]["cik"])


def main(argv: list[str]) -> None:
    if not argv:
        print(__doc__)
        return
    cmd, *args = argv
    if cmd == "tickers":
        t = tickers(refresh=True)
        for tk in load_config()["companies"]:
            print(f"{tk:5} CIK {t[tk]['cik']:>8}  {t[tk]['title']}")
    elif cmd == "submissions":
        for r in list_filings(_cik_for(args[0]))[:12]:
            print(r)
    elif cmd == "companyfacts":
        cf = companyfacts(_cik_for(args[0]))
        print(cf["entityName"], "| us-gaap tags:", len(cf["facts"]["us-gaap"]))
    elif cmd == "filing":
        ticker, form, period = args
        row = next(r for r in list_filings(_cik_for(ticker), form) if r["reportDate"] == period)
        data = filing_document(_cik_for(ticker), row["accessionNumber"], row["primaryDocument"])
        print(row["accessionNumber"], row["primaryDocument"], len(data), "bytes")
    else:
        sys.exit(f"unknown command {cmd!r}")


if __name__ == "__main__":
    main(sys.argv[1:])
