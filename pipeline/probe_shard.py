"""Probe a list of sites without the drive: one shard of p05's work, run in its own sandbox.

Usage: python probe_shard.py sites.txt out.parquet [--concurrency 128]
p05 folds work/probe_shards/*.parquet into its cache, so shards only need to be copied there.
"""

import argparse
import asyncio
import logging
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from net import client, get_home, parse_home

ap = argparse.ArgumentParser()
ap.add_argument("sites")
ap.add_argument("out")
ap.add_argument("--concurrency", type=int, default=128)
a = ap.parse_args()
logging.basicConfig(level=logging.INFO, format="%(asctime)s shard %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per request drowns the progress lines


async def probe(c, sem, site):
    async with sem:
        res = await get_home(c, site)
    row = {
        "site": site,
        "status": 0,
        "final_url": "",
        "home_title": "",
        "home_desc": "",
        "site_name": "",
        "generator": "",
        "feed_hints": [],
    }
    if res:
        status, final_url, ctype, body = res
        row.update(status=status, final_url=final_url)
        if status < 400 and "html" in ctype:
            try:
                row.update({k: v for k, v in parse_home(final_url, body).items() if k != "sections"})  # p06 reads sections itself
            except Exception:  # malformed HTML must not stop the crawl
                pass
    return row


def save(rows):
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), a.out)


async def main(sites, rows):
    sem = asyncio.Semaphore(a.concurrency)
    async with client() as c:
        for i in range(0, len(sites), 2000):
            rows += await asyncio.gather(*(probe(c, sem, s) for s in sites[i : i + 2000]))
            save(rows)  # checkpoint: a stopped shard keeps what it probed
            logging.info("probed %d/%d", i + len(sites[i : i + 2000]), len(sites))
    return rows


schema = pa.schema(
    [
        ("site", pa.string()),
        ("status", pa.int64()),
        ("final_url", pa.string()),
        ("home_title", pa.string()),
        ("home_desc", pa.string()),
        ("site_name", pa.string()),
        ("generator", pa.string()),
        ("feed_hints", pa.list_(pa.string())),
    ]
)
rows = pq.read_table(a.out).to_pylist() if Path(a.out).exists() else []
have = {r["site"] for r in rows}
sites = [s.strip() for s in open(a.sites) if s.strip() and s.strip() not in have]
save(asyncio.run(main(sites, rows)))
