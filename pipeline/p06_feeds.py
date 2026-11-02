"""Phase 06: find and validate a feed for every listed site (personal blogs, long-form company blogs).

Per site, first hit wins: homepage feed hints, platform rules, common paths. For a company
blog under a path (classified blog_path, e.g. /blog) the blog index and paths under it go first.
Platform rules go before common paths so medium.com/@user never resolves to
Medium's site-wide /feed. Writes feed.parquet:
feed(site, feed_url, kind, title, last_post_at, n_entries, status: ok | stale | undated | none).
"""

import asyncio
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin, urlsplit

import feedparser
import pyarrow as pa
import pyarrow.compute  # noqa: F401  (pa.compute)
import pyarrow.parquet as pq
from common import WORK, args, connect, listed, log
from dateutil import parser as dateparser
from net import NOT_FEED, client, get, get_home, parse_home

PATHS = [
    "/feed",
    "/rss",
    "/rss.xml",
    "/atom.xml",
    "/feed.xml",
    "/index.xml",
    "/feed/",
    "/blog/feed",
    "/blog/rss.xml",
    "/posts/index.xml",
    "/feed.atom",
    "/index.rss",
    "/index.atom",
]
BLOG_PATHS = [
    "/blog/feed/",
    "/blog/index.xml",
    "/blog/atom.xml",
    "/blog/?feed=rss2",
    "/blog/rss",
    "/blog/feed.xml",
    "/blog/index.rss",
]
# hosts where a homepage redirect lands on someone else's blog, and where a guessed subdomain is another user
PLATFORMS = ("github.com", "github.blog", "substack.com", "about.me", "medium.com", "linktr.ee", "twitter.com", "x.com")
SHARED = (
    ".dreamwidth.org",
    ".wordpress.com",
    ".blogspot.com",
    ".github.io",
    ".substack.com",
    ".medium.com",
    ".tumblr.com",
    ".livejournal.com",
    ".neocities.org",
    ".bearblog.dev",
)
FEED_MAX_BYTES = 5_000_000  # some feeds carry every post in full
STALE = timedelta(days=730)
SCHEMA = pa.schema(
    [
        ("site", pa.string()),
        ("feed_url", pa.string()),
        ("kind", pa.string()),
        ("title", pa.string()),
        ("last_post_at", pa.timestamp("s", tz="UTC")),
        ("n_entries", pa.int32()),
        ("status", pa.string()),
    ]
)


def extra(p):
    p.add_argument("--concurrency", type=int, default=64)
    p.add_argument("--refresh", action="store_true", help="re-check sites that already have a feed too")


a = args("discover feeds", extra)
lg = log("p06")
con = connect()


def candidates(site: str, probe: dict, blog_path: str = "") -> list[tuple[str, str]]:
    """Ordered (kind, url) list to try for one site."""
    final = probe.get("final_url") or ""
    base = final if final and probe.get("status", 0) and probe["status"] < 400 else f"https://{site}/"
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(base))
    host = urlsplit(base).netloc.lower()
    gen = (probe.get("generator") or "").lower()

    hints = [u for u in probe.get("feed_hints") or [] if not NOT_FEED.search(u)]
    own = site.split("/", 1)[0].removeprefix("www.")
    if host.endswith(PLATFORMS) and not host.endswith(own):
        # the homepage now redirects to a platform (a GitHub org, a Substack profile): its feeds are not this blog's
        return [("platform", "https://medium.com/feed/" + site.split("/", 1)[1])] if site.startswith("medium.com/@") else []
    if blog_path:  # company: feeds of the blog section first, never the site-wide changelog or status feed
        hints = [u for u in hints if blog_path in urlsplit(u).path] + [u for u in hints if blog_path not in urlsplit(u).path]
        out = [("hint", u) for u in probe.get("blog_hints") or []]
        out += [("hint", u) for u in hints]
        out += [("path", urljoin(origin, blog_path.rstrip("/") + p)) for p in PATHS[:7]]
    else:
        out = [("hint", u) for u in hints]
    if site.startswith("medium.com/@"):
        out.append(("platform", "https://medium.com/feed/" + site.split("/", 1)[1]))
    if host.endswith(".substack.com") or "substack" in gen or gen.startswith("medium"):
        out.append(("platform", origin + "/feed"))
    if gen.startswith("ghost"):
        out.append(("platform", origin + "/rss/"))
    if "wordpress" in gen:
        out.append(("platform", origin + "/?feed=rss2"))
    if host.endswith(".blogspot.com") or gen.startswith("blogger"):
        out.append(("platform", origin + "/feeds/posts/default"))
    if not site.startswith("medium.com/") and probe.get("status", 1):  # status 0: homepage unreachable
        section = urlsplit(base).path.rstrip("/")
        if section and not blog_path:  # the homepage redirected into a section (replit.com/blog): try its feeds first
            out += [("path", urljoin(origin, section + p)) for p in ("/feed", "/feed.xml", "/rss.xml", "/atom.xml", "/index.xml")]
        out += [("path", urljoin(origin, p)) for p in PATHS]
        # many personal sites keep the blog in a section or on a subdomain (found by the feed audit)
        out += [("path", urljoin(origin, p)) for p in BLOG_PATHS]
        if "/" not in site and not host.startswith(("blog.", "writings.")) and not host.endswith(SHARED):
            bare = host.removeprefix("www.")
            out += [
                ("path", f"https://{sub}.{bare}{p}") for sub in ("blog", "writings") for p in ("/feed", "/rss.xml", "/atom.xml")
            ]
    seen, uniq = set(), []
    for kind, u in out:
        if u not in seen:
            seen.add(u)
            uniq.append((kind, u))
    return uniq


def plausible(d: datetime | None) -> datetime | None:
    """Feeds sometimes carry dates like year 1 or far in the future; treat those as undated."""
    return d if d and datetime(1995, 1, 1, tzinfo=UTC) <= d <= datetime.now(UTC) + timedelta(days=2) else None


def entry_time(e) -> datetime | None:
    t = e.get("published_parsed") or e.get("updated_parsed")
    try:
        if t:
            return plausible(datetime(*t[:6], tzinfo=UTC))
        raw = e.get("published") or e.get("updated")  # e.g. "July 10th, 2025", which feedparser rejects
        if raw:
            d = dateparser.parse(raw, fuzzy=True)
            return plausible(d if d.tzinfo else d.replace(tzinfo=UTC))
    except (ValueError, OverflowError, TypeError):
        pass
    return None


def parse_feed(ctype: str, body: bytes) -> dict | None:
    """Validate a feed body: at least one entry. Returns title, n_entries, last_post_at."""
    head = body[:200].lstrip().lower()
    if "json" in ctype or head.startswith(b"{"):
        try:
            data = json.loads(body)
        except ValueError:
            return None
        if not isinstance(data, dict) or "jsonfeed.org" not in str(data.get("version", "")):
            return None
        items = data.get("items") or []
        dates = []
        for it in items:
            try:
                dates.append(datetime.fromisoformat(it.get("date_published") or it.get("date_modified")))
            except (TypeError, ValueError):
                pass
        dates = [d for d in (plausible(d if d.tzinfo else d.replace(tzinfo=UTC)) for d in dates) if d]
        return (
            {"title": str(data.get("title") or "")[:200], "n_entries": len(items), "last_post_at": max(dates) if dates else None}
            if items
            else None
        )
    if head.startswith((b"<!doctype html", b"<html")):
        return None
    f = feedparser.parse(body)
    if not f.entries or f.version == "":
        return None
    dates = [d for d in map(entry_time, f.entries) if d]
    return {
        "title": (f.feed.get("title") or "")[:200],
        "n_entries": len(f.entries),
        "last_post_at": max(dates) if dates else None,
    }


def blog_path(r: dict) -> str:
    p = (r.get("blog_path") or "").strip() if r["kind"] == "company" else ""
    return "/" + p.strip("/") + "/" if p.strip("/") else ""


class HostLimit:
    """At most `n` requests in flight per host."""

    def __init__(self, n: int = 2):
        self.sems = defaultdict(lambda: asyncio.Semaphore(n))

    def __call__(self, url: str) -> asyncio.Semaphore:
        return self.sems[urlsplit(url).netloc.lower()]


async def discover(c, sem, per_host, site, probe, blog_path=""):
    row = {"site": site, "feed_url": None, "kind": None, "title": None, "last_post_at": None, "n_entries": 0, "status": "none"}
    async with sem:
        if not probe.get("status"):  # homepage failed in p05: retry once, it may have been a transient block
            async with per_host(f"https://{site}/"):
                res = await get_home(c, site)
            if res and res[0] < 400:
                probe = {**probe, "status": res[0], "final_url": res[1]}
                if "html" in res[2]:
                    try:
                        probe.update(parse_home(res[1], res[3]))
                    except Exception as e:  # malformed HTML: fall back to platform rules and paths
                        lg.debug("parse home %s: %s", site, e)
        if blog_path:  # the blog index usually advertises its own feed
            final = probe.get("final_url") or f"https://{site}/"
            origin = "{0.scheme}://{0.netloc}".format(urlsplit(final))
            async with per_host(origin):
                res = await get(c, urljoin(origin, blog_path))
            if res and res[0] < 400 and "html" in res[2]:
                try:
                    probe = {**probe, "blog_hints": parse_home(res[1], res[3]).get("feed_hints") or []}
                except Exception as e:
                    lg.debug("parse blog %s: %s", site, e)
        for kind, url in candidates(site, probe, blog_path):
            async with per_host(url):
                res = await get(c, url, FEED_MAX_BYTES)
                if res is None and kind != "path":  # hints and platform URLs are worth one retry
                    res = await get(c, url, FEED_MAX_BYTES)
            # an advertised "feed" that is an HTML page often links the real feed: follow one hop
            if res and kind != "path" and res[0] < 400 and "html" in res[2].lower():
                try:
                    hop = [u for u in parse_home(res[1], res[3]).get("feed_hints") or [] if u != url and not NOT_FEED.search(u)][
                        :2
                    ]
                except Exception:
                    hop = []
                for u in hop:
                    async with per_host(u):
                        r2 = await get(c, u, FEED_MAX_BYTES)
                    if r2 and r2[0] < 400 and "html" not in r2[2].lower():
                        res = r2
                        break
            # parse any body: some servers send a valid feed with a 5xx status; HTML error pages fail parse_feed
            if not res or res[0] in (401, 403, 404, 410):
                continue
            status, final_url, ctype, body = res
            try:
                info = await asyncio.to_thread(parse_feed, ctype.lower(), body)
            except Exception as e:  # a broken feed must not stop the crawl
                lg.debug("parse %s: %s", url, e)
                info = None
            if info:
                last = info["last_post_at"]
                status = "undated" if last is None else "stale" if last < datetime.now(UTC) - STALE else "ok"
                row.update(
                    feed_url=final_url,
                    kind=kind,
                    title=info["title"],
                    n_entries=info["n_entries"],
                    last_post_at=last,
                    status=status,
                )
                break
    if row["feed_url"] is None and probe.get("status", 0) and probe["status"] < 400:
        await sections(c, per_host, probe, row)
    return row


async def sections(c, per_host, probe, row):
    """Last resort: the blog lives in a section the homepage links (/blog/, /ongoing/) or meta-refreshes to;
    read that page's advertised feeds (feed audit: martinfowler.com, tbray.org, mikeash.com)."""
    async with per_host(probe["final_url"]):
        res = await get(c, probe["final_url"])
    if not res or res[0] >= 400 or "html" not in res[2]:
        return
    try:
        pages = parse_home(res[1], res[3]).get("sections") or []
    except Exception:
        return
    for page in pages:
        async with per_host(page):
            res = await get(c, page)
        if not res or res[0] >= 400 or "html" not in res[2]:
            continue
        try:
            hints = parse_home(res[1], res[3]).get("feed_hints") or []
        except Exception:
            continue
        for u in hints[:3]:
            async with per_host(u):
                r2 = await get(c, u, FEED_MAX_BYTES)
            if not r2 or r2[0] >= 400:
                continue
            info = await asyncio.to_thread(parse_feed, r2[2].lower(), r2[3])
            if info:
                last = info["last_post_at"]
                status = "undated" if last is None else "stale" if last < datetime.now(UTC) - STALE else "ok"
                row.update(
                    feed_url=r2[1],
                    kind="section",
                    title=info["title"],
                    n_entries=info["n_entries"],
                    last_post_at=last,
                    status=status,
                )
                return


async def main(todo):
    sem, per_host = asyncio.Semaphore(a.concurrency), HostLimit(2)
    async with client() as c:
        rows = []
        for i in range(0, len(todo), 500):
            chunk = todo[i : i + 500]
            rows += await asyncio.gather(*(discover(c, sem, per_host, s, p, bp) for s, p, bp in chunk))
            lg.info("checked %d/%d, %d with feed", len(rows), len(todo), sum(r["feed_url"] is not None for r in rows))
    return rows


sites = listed()
probes = {}
if (WORK / "probe.parquet").exists():
    probes = {r["site"]: r for r in pq.read_table(WORK / "probe.parquet").to_pylist()}

feed_path = WORK / "feed.parquet"
old = pq.read_table(feed_path).cast(SCHEMA) if feed_path.exists() and not a.refresh else None
if old is not None:  # only active feeds are cached; stale, undated and missing ones are checked again every run
    old = old.filter(pa.compute.equal(old["status"], "ok"))
done = set(old.column("site").to_pylist()) if old is not None else set()
todo = [(s, probes.get(s, {}), blog_path(r)) for s, r in sites.items() if s not in done]
lg.info("%d listed sites, %d to check, %d cached", len(sites), len(todo), len(done))

if todo:
    new = pa.Table.from_pylist(asyncio.run(main(todo)), schema=SCHEMA)
    pq.write_table(pa.concat_tables([old, new]) if old is not None else new, feed_path)

stats = con.execute(f"SELECT status, count(*) FROM '{feed_path}' GROUP BY 1 ORDER BY 2 DESC").fetchall()
lg.info("feeds: %s", dict(stats))
