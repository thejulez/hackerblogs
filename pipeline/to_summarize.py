"""Pick the HN comments classify/summarize.py reads for each blog, from an out/site export.

Per blog, up to 40 comments, most-discussed threads first, with:
- at most 3 comments per thread, so one heated thread cannot dominate the sample,
- none by the blog's own author (their self-links are not recommendations),
- the thread title, so the model can tell criticism of the topic from criticism of the writing.
p08 calls build(); on the laptop, `python pipeline/to_summarize.py data/out` rebuilds the file from a pulled export.
"""

import json
import sys
from pathlib import Path

PER_THREAD = 3
PER_BLOG = 40


def sample(mentions: list[dict], authors: set[str]) -> list[dict]:
    per_thread: dict = {}
    out = []
    for m in mentions:
        if m["kind"] != "comment" or not m.get("snippet") or m.get("by") in authors:
            continue
        t = m.get("story_id")
        if per_thread.get(t, 0) >= PER_THREAD:
            continue
        per_thread[t] = per_thread.get(t, 0) + 1
        out.append({"id": m["id"], "thread": m.get("title") or "", "text": m["snippet"]})
        if len(out) >= PER_BLOG:
            break
    return out


def authors(b: dict, d: dict) -> set[str]:
    """The blog's own author on HN: named in their profile, or the one person who links it far more than anyone else."""
    found = {b["hn_author"]} if b.get("hn_author") else set()
    found |= {li["by"] for li in d.get("linkers", []) if li.get("is_author")}
    links = d.get("linkers", [])
    if links and links[0]["n_links"] >= max(5, 0.3 * d.get("n_mentions", 0)):
        found.add(links[0]["by"])
    return found


def build(site_dir: Path, done: set[str]) -> list[dict]:
    todo = []
    for b in json.loads((site_dir / "blogs.json").read_text()):
        if b["site"] in done:
            continue
        d = json.loads((site_dir / "blog" / f"{b['slug']}.json").read_text())
        more = site_dir / "mentions" / f"{b['slug']}.json"
        # only this export's own list: an old file left behind can belong to another blog with the same slug
        ms = d["mentions"] + (json.loads(more.read_text()) if more.exists() and d.get("n_more") else [])
        comments = sample(ms, authors(b, d))
        if comments:
            todo.append({"site": b["site"], "name": b.get("author") or b.get("name") or b["site"], "comments": comments})
    return todo


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "data/out")
    summaries = out / "summaries.json"
    # summaries made under the current rules (they carry praised_ids) are kept; older ones are redone
    done = {r["site"] for r in json.loads(summaries.read_text()) if "praised_ids" in r} if summaries.exists() else set()
    todo = build(out / "site", done)
    (out / "to_summarize.json").write_text(json.dumps(todo, ensure_ascii=False))
    print(f"{len(todo)} blogs to summarise, {sum(len(t['comments']) for t in todo)} comments")
