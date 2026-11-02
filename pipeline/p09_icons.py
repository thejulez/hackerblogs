"""Phase 09: a favicon for every exported blog, cached across runs.

Tries the site's own /favicon.ico first, then DuckDuckGo's icon service, and stores a 32 px PNG
(an .ico can hold many sizes and weigh 100 KB). Cached in work/icons/<slug>.png (a run only fetches
new blogs) and copied to out/site/icons/ for the site.
A missing icon is fine: the site falls back to the blog's initial.
"""

import asyncio
import io
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from common import OUT, WORK, args, log
from net import client, get
from PIL import Image
from rules import due

ICON_TYPES = ("image/", "application/octet-stream")


def extra(p):
    p.add_argument("--concurrency", type=int, default=64)


a = args("fetch favicons", extra)
lg = log("p09")
cache = Path(os.environ.get("HB_ICON_CACHE", WORK / "icons"))
cache.mkdir(parents=True, exist_ok=True)
missing = cache / "missing.json"  # sites with no icon anywhere; delete the file to retry them


def to_png(data: bytes, dest: Path, size: int = 32) -> bool:
    """Largest frame of the icon, scaled to size x size; False when it is not a readable image."""
    try:
        img = Image.open(io.BytesIO(data))
        if getattr(img, "ico", None):  # pick the biggest of the sizes an .ico carries
            img = img.ico.getimage(max(img.ico.sizes()))
        img = img.convert("RGBA")
        img.thumbnail((size, size), Image.LANCZOS)
        img.save(dest, "PNG", optimize=True)
        return True
    except Exception:
        return False


async def fetch(c, sem, b) -> bool:
    host = b["site"].split("/")[0]
    final = urlsplit(b.get("url") or "").netloc or host  # the blog may have moved (brainpickings -> themarginalian)
    urls = [f"https://{h}/favicon.ico" for h in dict.fromkeys((final, host))]
    urls += [f"https://{final}/apple-touch-icon.png", f"https://icons.duckduckgo.com/ip3/{final}.ico"]
    async with sem:
        for url in urls:
            res = await get(c, url, max_bytes=200_000)
            if res and res[0] == 200 and res[2].lower().startswith(ICON_TYPES) and len(res[3]) > 50:
                if to_png(res[3], cache / f"{b['slug']}.png"):
                    return True
    return False


async def main(todo):
    sem = asyncio.Semaphore(a.concurrency)
    async with client() as c:
        return await asyncio.gather(*(fetch(c, sem, b) for b in todo))


blogs = json.loads((OUT / "site" / "blogs.json").read_text())
# sites without an icon are tried again when due (about monthly), with the newer fallbacks
skip = {s for s in json.loads(missing.read_text()) if not due(s)} if missing.exists() else set()
todo = [b for b in blogs if not (cache / f"{b['slug']}.png").exists() and b["site"] not in skip]
lg.info("%d blogs, %d icons to fetch", len(blogs), len(todo))
if todo:
    ok = asyncio.run(main(todo))
    skip |= {b["site"] for b, got in zip(todo, ok) if not got}
    missing.write_text(json.dumps(sorted(skip)))

dest = OUT / "site" / "icons"
dest.mkdir(exist_ok=True)
for b in blogs:  # the site only requests icons that exist
    src = cache / f"{b['slug']}.png"
    b["icon"] = src.exists()
    if b["icon"]:
        shutil.copyfile(src, dest / src.name)
(OUT / "site" / "blogs.json").write_text(json.dumps(blogs, ensure_ascii=False))
lg.info("icons for %d of %d blogs", sum(b["icon"] for b in blogs), len(blogs))
