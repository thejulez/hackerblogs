"""Polite, bounded HTTP fetching for crawl phases. HTML is parsed, never executed."""

import asyncio
import re
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import h2.exceptions
import httpx
from common import USER_AGENT
from selectolax.lexbor import LexborHTMLParser as HTMLParser

MAX_BYTES = 1_000_000
DEADLINE = 25  # seconds per request, whole response
FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/feed+json", "application/json")
TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        http2=False,  # HTTP/2 lost ~40% of connections at 64 concurrent in the Sandbox (h2 ProtocolError)
        timeout=TIMEOUT,
        follow_redirects=True,
        max_redirects=5,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/atom+xml,application/feed+json,*/*;q=0.5",
        },
        limits=httpx.Limits(max_connections=128, max_keepalive_connections=32),
    )


# robots.txt per origin, fetched once per run; APIs we read on purpose (HN) are not crawled pages
ROBOTS: dict[str, RobotFileParser | None] = {}
ROBOTS_LOCKS: dict[str, asyncio.Lock] = {}
NO_ROBOTS = ("hacker-news.firebaseio.com", "hn.algolia.com")
AGENT = "HackerBlogsBot"


async def allowed(c: httpx.AsyncClient, url: str) -> bool:
    """Whether the site's robots.txt lets HackerBlogsBot fetch this URL (RFC 9309)."""
    parts = urlsplit(url)
    if parts.hostname in NO_ROBOTS or parts.path == "/robots.txt":
        return True
    origin = f"{parts.scheme}://{parts.netloc}"
    async with ROBOTS_LOCKS.setdefault(origin, asyncio.Lock()):
        if origin not in ROBOTS:
            try:
                res = await asyncio.wait_for(_get(c, origin + "/robots.txt", 200_000), DEADLINE)
            except TimeoutError:
                res = None
            # RFC 9309: rules apply when served; a 4xx means no rules; a 5xx means "assume everything disallowed"
            rp = None
            if res and res[0] == 200 and "html" not in res[2].lower():
                rp = RobotFileParser()
                rp.parse(res[3].decode("utf-8", "replace").splitlines())
            elif res and res[0] >= 500:
                rp = RobotFileParser()
                rp.disallow_all = True
            ROBOTS[origin] = rp
    rp = ROBOTS[origin]
    return rp is None or rp.can_fetch(AGENT, url)


async def get(c: httpx.AsyncClient, url: str, max_bytes: int = MAX_BYTES):
    """Return (status, final_url, content_type, body bytes) or None on network error, after DEADLINE seconds,
    or when robots.txt disallows the URL for our crawler."""
    try:
        if not await allowed(c, url):
            return None
    except (TimeoutError, Exception):  # an unreachable robots.txt allows, like a missing one
        pass
    try:
        return await asyncio.wait_for(_get(c, url, max_bytes), DEADLINE)
    except TimeoutError:  # the client timeout is per read: a server trickling bytes would hang forever
        return None


async def _get(c: httpx.AsyncClient, url: str, max_bytes: int):
    try:
        async with c.stream("GET", url) as r:
            body = bytearray()
            async for chunk in r.aiter_bytes():
                body += chunk
                if len(body) >= max_bytes:
                    break
            return r.status_code, str(r.url), r.headers.get("content-type", ""), bytes(body)
    except (TimeoutError, httpx.HTTPError, httpx.InvalidURL, h2.exceptions.H2Error, UnicodeError, ValueError):
        return None
    except Exception:  # one odd host (e.g. an invalid IDNA name) must never stop a 200k-site crawl
        return None


def site_url(site: str, scheme: str = "https") -> str:
    return f"{scheme}://{site}/"


async def get_home(c: httpx.AsyncClient, site: str):
    """GET the homepage over https, falling back to http on error or status >= 400."""
    res = await get(c, site_url(site))
    if res is None or res[0] >= 400:
        res = await get(c, site_url(site, "http")) or res
    if res is None and not site.startswith("www.") and "/" not in site:  # some domains only resolve with www.
        res = await get(c, site_url("www." + site))
    return res


# comment feeds and WordPress/oEmbed JSON look like feeds but are not the blog's posts (feed audit)
NOT_FEED = re.compile(r"comments?/feed|feed=comments|comments-rss|/comments/?$|wp-json|oembed", re.I)
# section links that usually lead to the blog part of a personal site (/blog/, /ongoing/, /pyblog/ ...)
SECTION = re.compile(r"^/(blog|weblog|writing|writings|posts|articles|essays|journal|notes|ongoing|pyblog)/?$", re.I)
FEED_HREF = re.compile(r"(/feed/?|/rss/?|/atom/?|[./](rss|atom|feed)\.xml|/index\.xml|\.rss|\?feed=rss2?)$", re.I)


def parse_home(final_url: str, body: bytes) -> dict:
    tree = HTMLParser(body.decode("utf-8", "replace"))
    meta = lambda sel: (n.attributes.get("content") or "").strip()[:300] if (n := tree.css_first(sel)) else ""
    title = tree.css_first("title")
    feeds = []
    for link in tree.css("link[rel~=alternate], link[rel~=feed]"):
        t = (link.attributes.get("type") or "").lower()
        href = link.attributes.get("href")
        json_ok = t != "application/json" or not NOT_FEED.search(href or "")
        if href and json_ok and (any(t.startswith(ft) for ft in FEED_TYPES) or "feed" in (link.attributes.get("rel") or "")):
            feeds.append(urljoin(final_url, href))
    # some blogs only link their feed in the page body ("RSS" in the footer)
    home_host = ".".join(urlsplit(final_url).netloc.lower().split(".")[-2:])
    for a in tree.css("a[href]"):
        href = urljoin(final_url, a.attributes.get("href") or "")
        text = a.text(strip=True).lower()
        same_site = urlsplit(href).netloc.lower().endswith(home_host)
        if same_site and (FEED_HREF.search(href) or text in ("rss", "feed", "atom", "rss feed", "subscribe via rss")):
            feeds.append(href)
    feeds = list(dict.fromkeys(f for f in feeds if f.startswith("http") and not NOT_FEED.search(f)))
    sections = []
    if (refresh := tree.css_first('meta[http-equiv="refresh" i]')) and "url=" in (
        c := refresh.attributes.get("content") or ""
    ).lower():
        sections.append(urljoin(final_url, c.split("=", 1)[1].strip(" '\"")))
    for a in tree.css("a[href]"):
        href = urljoin(final_url, a.attributes.get("href") or "")
        if urlsplit(href).netloc.lower().endswith(home_host) and SECTION.match(urlsplit(href).path):
            sections.append(href.split("#")[0])
    sections = list(dict.fromkeys(sections))
    feeds.sort(key=lambda f: "sitemap" in f.lower())  # SEO sitemap feeds list pages, not posts: try them last
    return {
        "home_title": title.text(strip=True)[:200] if title else "",
        "home_desc": meta('meta[name="description"]') or meta('meta[property="og:description"]'),
        "site_name": meta('meta[property="og:site_name"]'),
        "generator": meta('meta[name="generator"]'),
        "feed_hints": feeds[:5],
        "sections": sections[:2],
    }
