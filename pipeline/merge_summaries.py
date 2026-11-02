"""Merge out/summaries.json (from classify/summarize.py) into an existing out/site export, without DuckDB.

p08 merges summaries too; this lets the laptop add new summaries to a pulled export and rebuild the site
while the Drive is busy. Usage: python pipeline/merge_summaries.py data/out
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rules import SPAM, blog_url, exclude_list, excluded, parked_url, same_blog_key  # noqa: E402

MIN_CONFIDENCE = 0.7  # as in common.listed()

out = Path(sys.argv[1] if len(sys.argv) > 1 else "data/out")
site = out / "site"
summary_file = out / "summaries.json"
summaries = {r["site"]: r for r in json.loads(summary_file.read_text())} if summary_file.exists() else {}
summaries = {k: v for k, v in summaries.items() if "praised_ids" in v}  # made under the audited rules
# older runs only lend their "why" line until a blog is redone: their stances and reasons failed the audit
for older in sorted(out.glob("summaries.v*.json"), reverse=True):
    for r in json.loads(older.read_text()):
        summaries.setdefault(r["site"], {"site": r["site"], "why": r["why"], "stances": {}})


def stance_counts(st: dict) -> dict | None:
    return {k: sum(v == k for v in st.values()) for k in ("recommend", "neutral", "critical")} if st else None


blogs = json.loads((site / "blogs.json").read_text())
# same health rules as p08, for exports made before they existed
rules = exclude_list()
conf = {r["site"]: r.get("confidence", 1) for r in json.loads((out / "classified.json").read_text())}
drop = {
    b["site"]
    for b in blogs
    if excluded(b["site"], rules)
    or conf.get(b["site"], 1) < MIN_CONFIDENCE
    or SPAM.search(f"{b.get('name', '')} {b.get('description', '')}")
    # a company linked from fewer than two HN stories is mostly a product page with a post or two (audit: 8 of 9 wrong)
    or (b["type"] == "company" and b.get("n_stories", 0) < 2)
}
# second opinion on every listing (classify/verify.py): drop clear non-blogs, fix clear type errors
verified_file = out / "verified.json"
verified = json.loads(verified_file.read_text()) if verified_file.exists() else {}
sure = {k: v for k, v in verified.items() if v.get("confidence", 0) >= 0.8}
drop |= {b["site"] for b in blogs if sure.get(b["site"], {}).get("verdict") == "drop"}
for b in blogs:
    if sure.get(b["site"], {}).get("verdict") == "retype":
        b["type"] = sure[b["site"]]["type"]
probe = out / "to_classify.json"  # carries each site's final URL from the probe
probed = {r["site"]: r for r in json.loads(probe.read_text())} if probe.exists() else {}
final = {k: r.get("final_url") for k, r in probed.items()}
# results of launcher/check.ts: every listed link requested once from a Sandbox
checked = out / "url_check.json"
link_status = {r["url"]: r["status"] for r in json.loads(checked.read_text())} if checked.exists() else {}
drop |= {b["site"] for b in blogs if parked_url(final.get(b["site"]))}
blogs = [b for b in blogs if b["site"] not in drop]
seen_blog, kept = set(), []
for b in blogs:  # already ranked: the most-linked copy of a blog wins
    key = same_blog_key(b["site"], final.get(b["site"]))
    if key not in seen_blog:
        kept.append(b)
    seen_blog.add(key)
if len(kept) < len(blogs):
    print(f"merged {len(blogs) - len(kept)} duplicate listings")
blogs = kept
for rank, b in enumerate(blogs, 1):
    b["rank"] = rank
if drop:
    print(f"dropped {len(drop)} excluded, spam, parked or low-confidence sites")
n = 0
for b in blogs:
    if "description" not in b or "spark" not in b:  # exports from before p08 added these to the list
        d = json.loads((site / "blog" / f"{b['slug']}.json").read_text())
        b["description"] = d["description"][:200]
        by = {y["year"]: y["mentions"] for y in d["years"]}
        b["spark"] = [by.get(y, 0) for y in range(2007, datetime.now(UTC).year + 1)]
    f = site / "blog" / f"{b['slug']}.json"
    d = json.loads(f.read_text())
    d["type"] = b["type"]  # after a retype by the second opinion
    p = probed.get(b["site"], {})
    # a personal site's homepage is the blog; p06's blog_path there is only where the feed was found
    path = d.get("blog_path", "") if b["type"] == "company" else ""
    url = blog_url(b["site"], path, p.get("final_url"), p.get("status"))
    if link_status.get(url) in (404, 410):  # a blog section that is not a page, or a root with nothing on it
        root = url.split("://", 1)[0] + "://" + url.split("://", 1)[1].split("/", 1)[0] + "/"
        top = next((x["url"] for x in d.get("posts", []) if x.get("url")), None)
        url = root if url.rstrip("/") != root.rstrip("/") else top or url
    b["url"] = d["url"] = url
    # listed from its HN history although the server did not answer our crawler: say so on the page
    b["unverified"] = d["unverified"] = not p.get("status") or p["status"] < 0 or link_status.get(url) == 0
    s = summaries.get(b["site"])
    if not s:
        f.write_text(json.dumps(d, ensure_ascii=False))
        continue
    n += 1
    b["why"], b["stance"] = s["why"], stance_counts(s["stances"])
    d["why"], d["stance"] = b["why"], b["stance"]
    d["praised_for"], d["criticized_for"] = s.get("praised_for", ""), s.get("criticized_for", "")
    present = {m["id"] for m in d["mentions"]}
    more = site / "mentions" / f"{b['slug']}.json"
    if more.exists() and d.get("n_more"):
        present |= {m["id"] for m in json.loads(more.read_text())}
    # the comments cited, when they are still in this export's mention lists
    d["praised_ids"] = [i for i in s.get("praised_ids", []) if i in present]
    d["criticized_ids"] = [i for i in s.get("criticized_ids", []) if i in present]
    for m in d["mentions"]:
        m["stance"] = s["stances"].get(str(m["id"]))  # only current-rule labels
    f.write_text(json.dumps(d, ensure_ascii=False))
    more = site / "mentions" / f"{b['slug']}.json"
    if more.exists():
        ms = json.loads(more.read_text())
        for m in ms:
            m["stance"] = s["stances"].get(str(m["id"]))  # only current-rule labels
        more.write_text(json.dumps(ms, ensure_ascii=False))
(site / "blogs.json").write_text(json.dumps(blogs, ensure_ascii=False))
print(f"merged summaries into {n} of {len(blogs)} blogs")
