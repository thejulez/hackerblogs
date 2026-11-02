"""Shared paths, config and helpers for the pipeline phases."""

import argparse
import logging
import os
import sys
from pathlib import Path

DATA = Path(os.environ.get("HB_DATA", "/data"))
RAW = DATA / "raw"  # HF dump, data/YYYY/YYYY-MM.parquet
GAP = RAW / "gap"  # items fetched from the HN API after the dump
WORK = DATA / "work"  # derived Parquet tables
OUT = Path(os.environ.get("HB_OUT", DATA / "out"))  # JSON handed to the laptop / site
LOGS = Path(os.environ.get("HB_LOGS", DATA / "logs"))
DB = WORK / "hn.duckdb"

HF_REPO = "open-index/hacker-news"
HN_API = "https://hacker-news.firebaseio.com/v0"
USER_AGENT = "HackerBlogsBot/0.1 (+https://hackerblogs.org/about#crawler)"

# keep in sync with classify/classify.py TOPICS
TOPICS = {
    "programming",
    "systems",
    "web",
    "security",
    "ai",
    "data",
    "math",
    "science",
    "startups",
    "business",
    "economics",
    "design",
    "writing",
    "career",
    "culture",
    "politics",
    "history",
    "philosophy",
    "hardware",
    "games",
    "productivity",
    "health",
    "other",
}


from rules import SPAM, exclude_list, excluded  # noqa: E402,F401  (re-exported)

MIN_CONFIDENCE = 0.7  # the audit found about half of the listed sites below this were wrong


def listed() -> dict[str, dict]:
    """Classified sites the directory covers: personal blogs, and company sites with long-form writing,
    minus the exclude list and homepages the classifier saw as parked, spam or changed hands."""
    import json

    rules = exclude_list()
    rows = json.loads((OUT / "classified.json").read_text())
    return {
        r["site"]: r
        for r in rows
        if (r["kind"] == "personal" or (r["kind"] == "company" and r.get("longform")))
        and r.get("homepage", "ok") == "ok"
        and r.get("confidence", 1) >= MIN_CONFIDENCE
        and not excluded(r["site"], rules)
    }


for d in (RAW, GAP, WORK, OUT, LOGS) if not os.environ.get("HB_READONLY") else (OUT, LOGS):
    d.mkdir(parents=True, exist_ok=True)


def args(description: str, extra=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--sample", help="limit the dump to one month, e.g. 2024-01")
    if extra:
        extra(p)
    return p.parse_args()


def log(name: str) -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOGS / "pipeline.log")],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return logging.getLogger(name)


def items_sql() -> str:
    """read_parquet() over all item files: dump months plus API gap files."""
    pats = []
    if any((RAW / "data").rglob("*.parquet")):
        pats.append(f"'{RAW}/data/**/*.parquet'")
    if any(GAP.glob("*.parquet")):
        pats.append(f"'{GAP}/*.parquet'")
    if not pats:
        raise SystemExit("no item Parquet found, run 00 and 01 first")
    cols = 'id, deleted, type, "by", time, text, dead, parent, url, score, title, descendants'
    return f"(SELECT {cols} FROM read_parquet([{', '.join(pats)}], union_by_name=true))"


def connect():
    import duckdb

    if os.environ.get("HB_READONLY"):  # export from a read-only Drive snapshot: temp tables only
        con = duckdb.connect()
        con.execute(f"ATTACH '{DB}' AS hn (READ_ONLY)")
        con.execute("USE hn")
    else:
        con = duckdb.connect(str(DB))
    # spill to local disk when HB_TMP is set (the Drive is network storage)
    con.execute(f"SET temp_directory='{os.environ.get('HB_TMP', WORK / 'tmp')}'")
    con.execute("SET preserve_insertion_order=false")
    return con
