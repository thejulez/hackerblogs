"""Phase 01: fetch items newer than the dump from the official HN API.

Resumable: each chunk is written as gap/gap_<first>_<last>.parquet and the next
run starts after the highest id already on disk.
"""

import asyncio
from datetime import UTC, datetime

import duckdb
import h2.exceptions
import httpx
import pyarrow as pa
import pyarrow.parquet as pq
from common import GAP, HN_API, RAW, USER_AGENT, args, log

TYPES = {"story": 1, "comment": 2, "poll": 3, "pollopt": 4, "job": 5}
SCHEMA = pa.schema(
    [
        ("id", pa.uint32()),
        ("deleted", pa.uint8()),
        ("type", pa.int8()),
        ("by", pa.string()),
        ("time", pa.timestamp("us", tz="UTC")),
        ("text", pa.string()),
        ("dead", pa.uint8()),
        ("parent", pa.uint32()),
        ("url", pa.string()),
        ("score", pa.int32()),
        ("title", pa.string()),
        ("descendants", pa.int32()),
    ]
)


def extra(p):
    p.add_argument("--limit", type=int, help="fetch at most N items (testing)")
    p.add_argument("--concurrency", type=int, default=64)
    p.add_argument("--chunk", type=int, default=20_000)


a = args("fill the gap between dump and now", extra)
lg = log("p01")


def start_id() -> int:
    hi = 0
    dump = list((RAW / "data").rglob("*.parquet"))
    if dump:
        hi = duckdb.connect().execute(f"SELECT max(id) FROM read_parquet('{RAW}/data/**/*.parquet')").fetchone()[0] or 0
    for f in GAP.glob("gap_*.parquet"):
        hi = max(hi, int(f.stem.split("_")[2]))
    return hi + 1


def row(it: dict) -> dict:
    return {
        "id": it["id"],
        "deleted": int(it.get("deleted", False)),
        "type": TYPES.get(it.get("type"), 0),
        "by": it.get("by"),
        "time": datetime.fromtimestamp(it.get("time", 0), UTC),
        "text": it.get("text"),
        "dead": int(it.get("dead", False)),
        "parent": it.get("parent"),
        "url": it.get("url"),
        "score": it.get("score"),
        "title": it.get("title"),
        "descendants": it.get("descendants"),
    }


async def fetch(client: httpx.AsyncClient, sem: asyncio.Semaphore, i: int):
    async with sem:
        for attempt in range(5):
            try:
                r = await client.get(f"{HN_API}/item/{i}.json")
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, h2.exceptions.H2Error, ValueError):
                await asyncio.sleep(2**attempt)
        lg.warning("gave up on item %d", i)
        return None


async def main():
    async with httpx.AsyncClient(http2=True, timeout=20, headers={"User-Agent": USER_AGENT}) as client:
        maxitem = (await client.get(f"{HN_API}/maxitem.json")).json()
        first = start_id()
        last = maxitem if not a.limit else min(maxitem, first + a.limit - 1)
        lg.info("gap %d..%d (%d items)", first, last, max(0, last - first + 1))
        sem = asyncio.Semaphore(a.concurrency)
        for lo in range(first, last + 1, a.chunk):
            hi = min(lo + a.chunk - 1, last)
            items = await asyncio.gather(*(fetch(client, sem, i) for i in range(lo, hi + 1)))
            rows = [row(it) for it in items if it]
            pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), GAP / f"gap_{lo}_{hi}.parquet")
            lg.info("wrote %d..%d (%d items)", lo, hi, len(rows))


asyncio.run(main())
