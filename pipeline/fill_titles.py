"""Fill thread titles the dump lacks (polls, killed stories, items newer than the dump) from the HN API:
python pipeline/fill_titles.py data/out
Updates blog/<slug>.json and mentions/<slug>.json in place; titles are cached in thread_titles.json."""

import asyncio
import json
import sys
from pathlib import Path

import httpx

out = Path(sys.argv[1] if len(sys.argv) > 1 else "data/out")
site = out / "site"
cache_file = out / "thread_titles.json"
cache = {int(k): v for k, v in json.loads(cache_file.read_text()).items()} if cache_file.exists() else {}


def files():
    for f in sorted((site / "blog").glob("*.json")):
        yield f
        more = site / "mentions" / f.name
        if more.exists():
            yield more


def rows(data):
    return data["mentions"] if isinstance(data, dict) else data


async def title(c, sem, i):
    async with sem:
        for _ in range(3):
            try:
                r = await c.get(f"https://hacker-news.firebaseio.com/v0/item/{i}.json", timeout=15)
                it = r.json() or {}
                return i, it.get("title") or ""
            except (httpx.HTTPError, ValueError):
                await asyncio.sleep(1)
    return i, None


async def fetch(ids):
    sem = asyncio.Semaphore(16)
    async with httpx.AsyncClient(headers={"User-Agent": "HackerBlogsBot/0.1 (+https://hackerblogs.org/about#crawler)"}) as c:
        return dict(await asyncio.gather(*(title(c, sem, i) for i in ids)))


missing = set()
for f in files():
    for m in rows(json.loads(f.read_text())):
        if m.get("kind") == "comment" and not m.get("title") and m.get("story_id") and m["story_id"] not in cache:
            missing.add(m["story_id"])
print(f"{len(missing)} thread titles to fetch")
cache.update({k: v for k, v in asyncio.run(fetch(sorted(missing))).items() if v is not None})
cache_file.write_text(json.dumps(cache))

filled = 0
for f in files():
    data = json.loads(f.read_text())
    changed = False
    for m in rows(data):
        if m.get("kind") == "comment" and not m.get("title") and cache.get(m.get("story_id")):
            m["title"] = cache[m["story_id"]]
            filled += 1
            changed = True
    if changed:
        f.write_text(json.dumps(data, ensure_ascii=False))
print(f"filled {filled} thread titles")
