"""Phase 05: one GET per candidate homepage -> title, description, feed hints.

Writes probe.parquet and out/to_classify.json (input for local Claude Code).
"""

import asyncio
import json

import pyarrow as pa
import pyarrow.compute  # noqa: F401  (pa.compute)
import pyarrow.parquet as pq
from common import OUT, WORK, args, connect, log
from net import client, get_home, parse_home
from rules import due


def extra(p):
    p.add_argument("--concurrency", type=int, default=128)  # one request per host, so no per-host limit needed


a = args("probe candidate homepages", extra)
lg = log("p05")
con = connect()


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
            except Exception as e:  # malformed HTML must not stop the crawl
                lg.debug("parse %s: %s", site, e)
    return row


def save(old, rows):
    new = pa.Table.from_pylist(rows)
    if old is not None:
        new = pa.concat_tables([old, new.cast(old.schema)])
    pq.write_table(new, WORK / "probe.parquet")


async def main(sites, old):
    sem = asyncio.Semaphore(a.concurrency)
    async with client() as c:
        rows = []
        for i in range(0, len(sites), 1000):
            rows += await asyncio.gather(*(probe(c, sem, s) for s in sites[i : i + 1000]))
            lg.info("probed %d/%d", len(rows), len(sites))
            if len(rows) % 2_000 == 0:  # checkpoint: a stopped run keeps what it probed
                save(old, rows)
    save(old, rows)


old = None  # unreachable homepages (status 0) are probed again when due, about monthly
if (WORK / "probe.parquet").exists():
    old = pq.read_table(WORK / "probe.parquet")
    keep = [st > 0 or not due(s) for s, st in zip(old.column("site").to_pylist(), old.column("status").to_pylist())]
    old = old.filter(pa.array(keep))
shards = sorted((WORK / "probe_shards").glob("*.parquet"))  # from probe_shard.py runs in parallel sandboxes
if shards:
    fresh = pa.concat_tables([pq.read_table(f) for f in shards])
    if old is not None:
        old = old.filter(pa.compute.invert(pa.compute.is_in(old["site"], value_set=fresh.column("site"))))
        fresh = fresh.cast(old.schema)
    old = pa.concat_tables([old, fresh]) if old is not None else fresh  # shard rows count as probed, even unreachable ones
    pq.write_table(old, WORK / "probe.parquet")
    for f in shards:
        f.unlink()
    lg.info("folded %d shard rows into the cache", fresh.num_rows)
done = set(old.column("site").to_pylist()) if old is not None else set()
sites = [r[0] for r in con.execute("SELECT site FROM candidate").fetchall() if r[0] not in done]
lg.info("%d to probe, %d cached", len(sites), len(done))

if sites:
    asyncio.run(main(sites, old))

classified = set()
if (OUT / "classified.json").exists():
    # sites classified before the audited rules (homepage field) are sent again
    classified = {r["site"] for r in json.loads((OUT / "classified.json").read_text()) if "homepage" in r}

rows = con.execute(f"""
    SELECT c.site, c.n_people, c.n_stories, c.n_comment_links, s.titles, s.urls,
           p.status, p.final_url, p.home_title, p.home_desc, p.site_name, p.generator,
           len(p.feed_hints) > 0 AS has_feed_hint
    FROM candidate c
    JOIN candidate_samples s USING (site)
    JOIN '{WORK}/probe.parquet' p USING (site)
    ORDER BY c.n_people DESC
""").fetchall()
cols = [
    "site",
    "n_people",
    "n_stories",
    "n_comment_links",
    "titles",
    "urls",
    "status",
    "final_url",
    "home_title",
    "home_desc",
    "site_name",
    "generator",
    "has_feed_hint",
]
todo = [dict(zip(cols, r)) for r in rows if r[0] not in classified]
(OUT / "to_classify.json").write_text(json.dumps(todo, ensure_ascii=False, indent=0))
lg.info("to_classify.json: %d sites (%d already classified)", len(todo), len(classified))
