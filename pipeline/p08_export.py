"""Phase 08: JSON for the site.

Listed sites (personal blogs, long-form company blogs); status is the feed's: ok, stale, undated or none.
Writes out/site/:
  blogs.json            ranked summary rows
  meta.json             build info and totals
  blog/<slug>.json      one per blog: stats, feed, yearly distinct people, top linkers, author's HN profile,
                        most-linked posts, related blogs, top mentions, Claude summary and stances if present
  mentions/<slug>.json  up to --all mentions per blog (the "show more" list)
and out/to_summarize.json: comment snippets of blogs without a summary yet (input for classify/summarize.py).
Snippets are plain text (tags stripped, entities decoded); the site escapes them on render.
"""

import html
import json
import re
import shutil
from datetime import UTC, datetime

import pyarrow.parquet as pq
from common import OUT, SPAM, TOPICS, WORK, args, connect, items_sql, listed, log
from rules import parked_url, same_blog_key
from slugs import assign
from to_summarize import build as build_to_summarize


def extra(p):
    p.add_argument("--mentions", type=int, default=30, help="mentions in blog/<slug>.json")
    p.add_argument("--all", type=int, default=150, help="mentions in mentions/<slug>.json (keeps the site small)")
    p.add_argument("--posts", type=int, default=10)
    p.add_argument("--related", type=int, default=8)


a = args("export site JSON", extra)
lg = log("p08")
con = connect()

TAG = re.compile(r"<[^>]+>")


def plain(text: str | None, n: int = 280) -> str:
    s = html.unescape(TAG.sub(" ", (text or "").replace("<p>", "\n")))
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def iso(ts) -> str | None:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        ts = datetime.fromtimestamp(ts, UTC)
    return ts.isoformat()


home = {}
if (WORK / "probe.parquet").exists():
    home = {
        r["site"]: r
        for r in pq.read_table(
            WORK / "probe.parquet", columns=["site", "final_url", "home_title", "home_desc", "site_name"]
        ).to_pylist()
    }
# hijacked domains serve gambling or parking pages, often under the old feed, so a working feed proves nothing
unhealthy = {
    s
    for s, h in home.items()
    if SPAM.search(f"{h['home_title']} {h['home_desc']} {h['site_name']}") or parked_url(h["final_url"])
}
classified = {s: r for s, r in listed().items() if s not in unhealthy}
lg.info("listed %d, dropped %d with spam or parked homepages", len(classified), len(unhealthy & set(listed())))
con.execute("CREATE OR REPLACE TEMP TABLE listed(site VARCHAR)")
con.executemany("INSERT INTO listed VALUES (?)", [(s,) for s in classified])

con.execute(f"""
CREATE OR REPLACE TEMP TABLE blog AS
SELECT s.*, f.feed_url, f.kind AS feed_kind, f.title AS feed_title, f.last_post_at,
       coalesce(f.n_entries, 0) AS n_entries, coalesce(f.status, 'none') AS status
FROM site_stats s
JOIN listed USING (site)
LEFT JOIN '{WORK}/feed.parquet' f USING (site);  -- blogs without a feed are listed too (filter "Without feed")
CREATE OR REPLACE TEMP TABLE bm AS  -- one row per (blog, HN item)
SELECT DISTINCT ON (site, item_id) m.* FROM mention m JOIN (SELECT site FROM blog) USING (site);
""")

lg.info("selecting mentions")
con.execute(f"""
CREATE OR REPLACE TEMP TABLE sel AS  -- comments and stories interleaved, each by thread score, so big blogs keep comments
SELECT * FROM (
    SELECT *, row_number() OVER (PARTITION BY site ORDER BY rk_kind, kind = 'comment' DESC) AS rk
    FROM (SELECT *, row_number() OVER (
              PARTITION BY site, kind ORDER BY story_score DESC NULLS LAST, ts DESC) AS rk_kind
          FROM bm)
) WHERE rk <= {a.all};
CREATE OR REPLACE TEMP TABLE sel_text AS
SELECT i.id, i.text FROM {items_sql()} i
WHERE i.id IN (SELECT item_id FROM sel WHERE kind = 'comment');
""")

mentions = {}
for site, item_id, kind, by, ts, story_id, title, score, url, text in con.execute("""
    SELECT t.site, t.item_id, t.kind, t."by", t.ts, t.story_id, t.story_title, t.story_score, t.url, x.text
    FROM sel t LEFT JOIN sel_text x ON x.id = t.item_id
    ORDER BY t.site, t.rk
""").fetchall():
    mentions.setdefault(site, []).append(
        {
            "id": item_id,
            "kind": kind,
            "by": by,
            "date": iso(ts),
            "story_id": story_id,
            "title": title or "",
            "points": score,
            "url": url,
            "snippet": plain(text, 420) if kind == "comment" else "",
        }
    )

lg.info("most-linked posts")
posts = {}
for site, url, people, n, title, first in con.execute(f"""
    SELECT site, url, people, n, title, first FROM (
        SELECT site, url, count(DISTINCT "by") AS people, count(*) AS n,
               arg_max(story_title, coalesce(story_score, 0)) FILTER (WHERE kind = 'story') AS title,
               min(ts) AS first,
               row_number() OVER (PARTITION BY site ORDER BY count(DISTINCT "by") DESC, count(*) DESC) AS rk
        FROM bm GROUP BY site, url
    ) WHERE rk <= {a.posts} AND people >= 2 ORDER BY site, rk
""").fetchall():
    posts.setdefault(site, []).append({"url": url, "title": title or "", "people": people, "mentions": n, "first": iso(first)})

lg.info("related blogs")
related = {}
for site, other, shared, _score in con.execute(f"""
    WITH p AS (SELECT DISTINCT site, "by" FROM bm),
    deg AS (SELECT "by" FROM p GROUP BY "by" HAVING count(*) BETWEEN 2 AND 300),  -- skip link-everything accounts
    pp AS (SELECT p.* FROM p JOIN deg USING ("by")),
    sz AS (SELECT site, count(*) AS n FROM pp GROUP BY site),
    pair AS (SELECT a.site, b.site AS other, count(*) AS shared
             FROM pp a JOIN pp b ON a."by" = b."by" AND a.site <> b.site GROUP BY ALL HAVING count(*) >= 3)
    SELECT site, other, shared, score FROM (
        SELECT pair.*, shared / (sa.n + sb.n - shared) AS score,
               row_number() OVER (PARTITION BY pair.site ORDER BY shared / (sa.n + sb.n - shared) DESC) AS rk
        FROM pair JOIN sz sa ON sa.site = pair.site JOIN sz sb ON sb.site = pair.other
    ) WHERE rk <= {a.related} ORDER BY site, rk
""").fetchall():
    related.setdefault(site, []).append({"site": other, "shared": shared})

years = {}
for site, year, people, n in con.execute("""
    SELECT site, year(ts) AS y, count(DISTINCT "by"), count(*) FROM bm GROUP BY ALL ORDER BY site, y
""").fetchall():
    years.setdefault(site, []).append({"year": year, "people": people, "mentions": n})

linkers = {}
if (WORK / "linker.parquet").exists():
    for site, by, n, karma, is_author in con.execute(
        f"SELECT site, \"by\", n_links, karma, is_author FROM '{WORK}/linker.parquet' ORDER BY site, n_links DESC"
    ).fetchall():
        linkers.setdefault(site, []).append({"by": by, "n_links": n, "karma": karma, "is_author": is_author})

# the author's own HN profile text, as they published it
users = {}
if (WORK / "hn_user.parquet").exists():
    users = {u["id"]: u for u in pq.read_table(WORK / "hn_user.parquet").to_pylist()}

summaries = {}
if (OUT / "summaries.json").exists():
    summaries = {r["site"]: r for r in json.loads((OUT / "summaries.json").read_text())}

cols = [d[0] for d in con.execute("SELECT * FROM blog LIMIT 0").description]
rows = [dict(zip(cols, r)) for r in con.execute("SELECT * FROM blog ORDER BY n_people DESC, story_points DESC").fetchall()]
# one listing per blog: country-domain copies and renamed domains that land on the same URL keep the most-linked
seen_blog, dupes = set(), 0
for r in list(rows):
    key = same_blog_key(r["site"], home.get(r["site"], {}).get("final_url"))
    if key in seen_blog:
        rows.remove(r)
        dupes += 1
    seen_blog.add(key)
lg.info("merged %d duplicate listings", dupes)

site_dir = OUT / "site"
shutil.rmtree(site_dir, ignore_errors=True)
(site_dir / "blog").mkdir(parents=True)
(site_dir / "mentions").mkdir()


def display_name(b: dict) -> str:
    h = home.get(b["site"], {})
    return (h.get("site_name") or b["feed_title"] or h.get("home_title") or "")[:120]


slugs = assign([{"site": b["site"], "author": classified[b["site"]].get("author"), "name": display_name(b)} for b in rows])
SPARK_FROM = 2007  # links per year from HN's first full year, for the list sparklines


def spark(ys: list[dict]) -> list[int]:
    by = {y["year"]: y["mentions"] for y in ys}
    return [by.get(y, 0) for y in range(SPARK_FROM, datetime.now(UTC).year + 1)]


summary = []
exported = {r["site"] for r in rows}  # related blogs must point at pages that exist
for rank, b in enumerate(rows, 1):
    site = b["site"]
    c = classified[site]
    hn_author = next((l["by"] for l in linkers.get(site, []) if l["is_author"]), None)
    s = summaries.get(site, {})
    stance = s.get("stances") or {}
    counts = {k: sum(v == k for v in stance.values()) for k in ("recommend", "neutral", "critical")}
    h = home.get(site, {})
    row = {
        "rank": rank,
        "site": site,
        "slug": slugs[site],
        "type": c["kind"],
        "author": c.get("author") or "",
        "name": display_name(b),
        "hn_author": hn_author,
        "topics": [t for t in c.get("topics") or [] if t in TOPICS],
        "n_people": b["n_people"],
        "n_mentions": b["n_mentions"],
        "n_stories": b["n_stories"],
        "n_comment_links": b["n_comment_links"],
        "story_points": int(b["story_points"]),
        "people_2y": b["people_2y"],
        "first_seen": iso(b["first_ts"]),
        "last_seen": iso(b["last_ts"]),
        "feed_url": b["feed_url"],
        "feed_title": b["feed_title"] or "",
        "last_post_at": iso(b["last_post_at"]),
        "status": b["status"],
        "why": s.get("why") or "",
        "stance": counts if stance else None,
        "description": plain(h.get("home_desc"), 200),
        "spark": spark(years.get(site, [])),
    }
    summary.append(row)
    ms = mentions.get(site, [])
    for m in ms:
        if str(m["id"]) in stance:
            m["stance"] = stance[str(m["id"])]
    u = users.get(hn_author) if hn_author else None
    detail = {
        **row,
        "feed_kind": b["feed_kind"],
        "n_entries": b["n_entries"],
        "blog_path": c.get("blog_path") or "",
        "description": plain(h.get("home_desc"), 300),
        "praised_for": s.get("praised_for") or "",
        "criticized_for": s.get("criticized_for") or "",
        "author_profile": {"id": u["id"], "karma": u["karma"], "created": iso(u["created"]), "about": plain(u["about"], 500)}
        if u
        else None,
        "years": years.get(site, []),
        "linkers": linkers.get(site, []),
        "posts": posts.get(site, []),
        "related": [{**r, "slug": slugs[r["site"]]} for r in related.get(site, []) if r["site"] in exported],
        "mentions": ms[: a.mentions],
        "n_more": max(0, len(ms) - a.mentions),
    }
    (site_dir / "blog" / f"{row['slug']}.json").write_text(json.dumps(detail, ensure_ascii=False))
    if len(ms) > a.mentions:
        (site_dir / "mentions" / f"{row['slug']}.json").write_text(json.dumps(ms[a.mentions :], ensure_ascii=False))

(site_dir / "blogs.json").write_text(json.dumps(summary, ensure_ascii=False))
to_summarize = build_to_summarize(site_dir, {k for k, v in summaries.items() if "praised_ids" in v})
(OUT / "to_summarize.json").write_text(json.dumps(to_summarize, ensure_ascii=False))
max_ts = con.execute("SELECT max(ts) FROM mention").fetchone()[0]
yearly = [
    {"year": y, "mentions": n, "people": p}
    for y, n, p in con.execute('SELECT year(ts) AS y, count(*), count(DISTINCT "by") FROM bm GROUP BY 1 ORDER BY 1').fetchall()
]
meta = {
    "generated_at": datetime.now(UTC).isoformat(),
    "data_until": iso(max_ts),
    "sample": a.sample,
    "n_blogs": len(summary),
    "n_active": sum(r["status"] == "ok" for r in summary),
    "n_with_feed": sum(r["status"] != "none" for r in summary),
    "years": yearly,
    "n_personal": sum(r["type"] == "personal" for r in summary),
    "n_company": sum(r["type"] == "company" for r in summary),
    "n_listed_classified": len(classified),
    # coverage, for the "work in progress" note: sites linked by enough people vs sites classified so far
    "n_candidates": con.execute("SELECT count(*) FROM candidate").fetchone()[0],
    "candidate_min_people": con.execute("SELECT min(n_people) FROM candidate").fetchone()[0],
    "n_classified": len(json.loads((OUT / "classified.json").read_text())),
}
(site_dir / "meta.json").write_text(json.dumps(meta, indent=1))
lg.info(
    "exported %d blogs (%d active, %d company), %d to summarize",
    len(summary),
    meta["n_active"],
    meta["n_company"],
    len(to_summarize),
)
