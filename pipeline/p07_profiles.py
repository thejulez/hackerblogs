"""Phase 07: HN profiles of the top linkers per personal blog.

A linker whose `about` links to the blog is flagged as the likely author.
Users are cached in hn_user.parquet across runs; writes linker.parquet:
linker(site, by, n_links, karma, is_author).
"""

import asyncio
import html
import re

import pyarrow as pa
import pyarrow.parquet as pq
from common import HN_API, WORK, args, connect, listed, log
from net import client

USER_SCHEMA = pa.schema([("id", pa.string()), ("karma", pa.int64()), ("created", pa.int64()), ("about", pa.string())])
LINKER_SCHEMA = pa.schema(
    [("site", pa.string()), ("by", pa.string()), ("n_links", pa.int64()), ("karma", pa.int64()), ("is_author", pa.bool_())]
)


def mentions_site(about: str, site: str) -> bool:
    """True if the profile text names the site as a host (subdomains allowed, dropbox.com != box.com)."""
    return re.search(r"(?<![a-z0-9-])" + re.escape(site) + r"(?![a-z0-9-])", about) is not None


def extra(p):
    p.add_argument("--per-blog", type=int, default=10)
    p.add_argument("--concurrency", type=int, default=32)


a = args("fetch HN profiles of top linkers", extra)
lg = log("p07")
con = connect()

con.execute("CREATE OR REPLACE TEMP TABLE personal(site VARCHAR)")  # all listed sites, company blogs too
con.executemany("INSERT INTO personal VALUES (?)", [(site,) for site in listed()])

con.execute(f"""
CREATE OR REPLACE TEMP TABLE top_linker AS
SELECT site, "by", n_links FROM (
    SELECT m.site, m."by", count(*) AS n_links,
           row_number() OVER (PARTITION BY m.site ORDER BY count(*) DESC, min(m.ts)) AS rk
    FROM mention m JOIN personal USING (site)
    GROUP BY m.site, m."by"
) WHERE rk <= {a.per_blog}
""")

user_path = WORK / "hn_user.parquet"
cached = pq.read_table(user_path).cast(USER_SCHEMA) if user_path.exists() else None
have = set(cached.column("id").to_pylist()) if cached is not None else set()
wanted = [r[0] for r in con.execute('SELECT DISTINCT "by" FROM top_linker').fetchall()]
todo = [u for u in wanted if u not in have]
lg.info("%d linkers, %d to fetch, %d cached", len(wanted), len(todo), len(have))


async def fetch(c, sem, uid):
    async with sem:
        for attempt in range(3):
            try:
                r = await c.get(f"{HN_API}/user/{uid}.json")
                if r.status_code == 200:
                    d = r.json() or {}
                    return {"id": uid, "karma": d.get("karma"), "created": d.get("created"), "about": d.get("about") or ""}
            except Exception as e:  # network or JSON error: retry, then record an empty profile
                lg.debug("user %s: %s", uid, e)
            await asyncio.sleep(1 + attempt)
    return {"id": uid, "karma": None, "created": None, "about": ""}


async def main(users):
    sem = asyncio.Semaphore(a.concurrency)
    async with client() as c:
        return await asyncio.gather(*(fetch(c, sem, u) for u in users))


if todo:
    new = pa.Table.from_pylist(asyncio.run(main(todo)), schema=USER_SCHEMA)
    pq.write_table(pa.concat_tables([cached, new]) if cached is not None else new, user_path)

users = {r["id"]: r for r in pq.read_table(user_path).to_pylist()}
rows = []
for site, by, n_links in con.execute('SELECT site, "by", n_links FROM top_linker ORDER BY site, n_links DESC').fetchall():
    u = users.get(by, {})
    about = html.unescape(u.get("about") or "").lower()
    rows.append({"site": site, "by": by, "n_links": n_links, "karma": u.get("karma"), "is_author": mentions_site(about, site)})
pq.write_table(pa.Table.from_pylist(rows, schema=LINKER_SCHEMA), WORK / "linker.parquet")
lg.info("linker rows %d, blogs with a likely author %d", len(rows), len({r["site"] for r in rows if r["is_author"]}))
