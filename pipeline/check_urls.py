"""Check that every listed blog link answers: python check_urls.py urls.json out.json
Each URL gets one GET (with the http/www fallbacks of get_home for bare homepages) and a retry on network errors."""

import asyncio
import json
import sys

from net import client, get


async def check(c, sem, per_host, url):
    async with sem, per_host(url):
        res = await get(c, url, 200_000) or await get(c, url, 200_000)
    return {"url": url, "status": res[0] if res else 0, "final_url": res[1] if res else ""}


async def main(urls):
    from collections import defaultdict
    from urllib.parse import urlsplit

    sems = defaultdict(lambda: asyncio.Semaphore(2))
    per_host = lambda u: sems[urlsplit(u).netloc.lower()]
    sem = asyncio.Semaphore(96)
    out = []
    async with client() as c:
        for i in range(0, len(urls), 2000):
            out += await asyncio.gather(*(check(c, sem, per_host, u) for u in urls[i : i + 2000]))
            print(
                f"checked {len(out)}/{len(urls)}, {sum(r['status'] == 0 or r['status'] >= 400 for r in out)} failing", flush=True
            )
    return out


urls = json.load(open(sys.argv[1]))
json.dump(asyncio.run(main(urls)), open(sys.argv[2], "w"))
