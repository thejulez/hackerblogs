"""Check every listed blog in an export for broken references: python pipeline/validate.py data/out

Each mention must be an HN item linking to this blog, comments must name their story and thread, recommendation
citations must point at sampled comments with that stance, and the list, detail and "show more" files must agree.
Prints counts per problem and a few examples; exits 1 when anything is wrong.
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

out = Path(sys.argv[1] if len(sys.argv) > 1 else "data/out")
site_dir = out / "site"
blogs = json.loads((site_dir / "blogs.json").read_text())
problems: Counter = Counter()
examples: dict = defaultdict(list)


def flag(kind: str, slug: str, detail: str = "") -> None:
    problems[kind] += 1
    if len(examples[kind]) < 5:
        examples[kind].append(f"{slug} {detail}".strip())


def host_of(url: str) -> str:
    return urlsplit(url).hostname.removeprefix("www.") if urlsplit(url).hostname else ""


# threads the HN API returns without a title were deleted on HN (pipeline/fill_titles.py caches them as "")
titles_file = out / "thread_titles.json"
deleted = {int(k): v for k, v in json.loads(titles_file.read_text()).items()} if titles_file.exists() else {}
slugs = Counter(b["slug"] for b in blogs)
for s, n in slugs.items():
    if n > 1:
        flag("duplicate slug", s)

for b in blogs:
    slug, site = b["slug"], b["site"]
    if b.get("type") not in ("personal", "company"):
        flag("unknown type", slug, str(b.get("type")))
    if not b.get("url", "").startswith("http"):
        flag("no link", slug)
    if b.get("status") != "none" and not b.get("feed_url"):
        flag("feed status without feed", slug, b.get("status", ""))
    f = site_dir / "blog" / f"{slug}.json"
    if not f.exists():
        flag("missing detail file", slug)
        continue
    d = json.loads(f.read_text())
    more = site_dir / "mentions" / f"{slug}.json"
    ms = d["mentions"] + (json.loads(more.read_text()) if more.exists() and d.get("n_more") else [])
    if d.get("n_more") and not more.exists():
        flag("show-more file missing", slug)
    own = site.split("/", 1)[0].removeprefix("www.")
    path = site.split("/", 1)[1] if "/" in site else ""
    ids = set()
    for m in ms:
        ids.add(m["id"])
        if m.get("kind") not in ("story", "comment"):
            flag("mention kind", slug, str(m.get("id")))
        h = host_of(m.get("url") or "")
        if not (h == own or h.endswith("." + own)) or (path and path not in (m.get("url") or "")):
            flag("mention links another site", slug, f"{m['id']} {m.get('url', '')[:60]}")
        if m.get("kind") == "story" and m.get("story_id") not in (None, m["id"]):
            flag("story with another story id", slug, str(m["id"]))
        if m.get("kind") == "comment" and not m.get("story_id"):
            flag("comment without story", slug, str(m["id"]))
        if m.get("kind") == "comment" and not m.get("title") and deleted.get(m.get("story_id")) != "":
            flag("comment without thread title", slug, str(m["id"]))
        if not m.get("by") or not m.get("date"):
            flag("mention without author or date", slug, str(m["id"]))
    if len(ids) < len(ms):
        flag("repeated mention", slug)
    labels = {int(k): v for m in ms if m.get("stance") for k, v in [(m["id"], m["stance"])]}
    for key, stance in (("praised_ids", "recommend"), ("criticized_ids", "critical")):
        for cid in d.get(key) or []:
            if cid not in ids:
                flag(f"{key} not among mentions", slug, str(cid))
            elif labels.get(cid) != stance:
                flag(f"{key} without that stance", slug, str(cid))
    for p in d.get("posts", []):
        h = host_of(p.get("url") or "")
        if not (h == own or h.endswith("." + own)):
            flag("post on another site", slug, (p.get("url") or "")[:60])

print(f"{len(blogs)} blogs checked")
for kind, n in problems.most_common():
    print(f"{n:7}  {kind}: {'; '.join(examples[kind])}")
sys.exit(1 if problems else 0)
