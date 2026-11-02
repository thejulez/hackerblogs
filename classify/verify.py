"""Second opinion on every listed blog: is it really a personal blog, or a company blog with long-form writing?

    python classify/verify.py data/out [--jobs 12]

Reads data/out/site/blogs.json and the probe/HN evidence in data/out/to_classify.json, writes data/out/verified.json
({site: {verdict, type, confidence, reason}}); resumes where it stopped. merge_summaries.py applies the verdicts.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from claude_cli import ask

SYSTEM = """You audit a directory of blogs that Hacker News links to. It lists only:
- personal blogs: ongoing writing by one identifiable person (or a named duo) in their own voice;
- company blogs with long-form writing: engineering, research or essay posts by a company or lab.
Everything else must go: product or landing pages with a post or two, SEO content marketing, shops, news outlets and
magazines with staff writers, group or community sites, forums, docs, tools, single projects, webcomics, wikis,
aggregators, newsletters of links, government and university pages.

For each site you get our current label, its name, homepage title and description, and the titles of the HN stories
that linked it. Answer with:
- `verdict`: `keep` (label is right), `retype` (it is a blog, but the other type), or `drop` (not a blog we list);
- `type`: `personal` or `company` (the right one when kept or retyped, else the closest);
- `confidence` 0-1 and a `reason` under 80 characters.
Only drop or retype when the evidence is clear; keep when unsure. Return one result per input site, same order."""

SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "site": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["keep", "retype", "drop"]},
                    "type": {"type": "string", "enum": ["personal", "company"]},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["site", "verdict", "type", "confidence", "reason"],
            },
        }
    },
    "required": ["results"],
}


def run_batch(batch: list[dict], model: str) -> list[dict]:
    data, _ = ask(f"Audit these listings:\n{json.dumps(batch, ensure_ascii=False)}", SYSTEM, SCHEMA, model)
    want = {s["site"] for s in batch}
    return [r for r in (data or {}).get("results", []) if r.get("site") in want]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="data/out")
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--batch", type=int, default=40)
    ap.add_argument("--jobs", type=int, default=12)
    a = ap.parse_args()
    out = Path(a.out)
    target = out / "verified.json"
    done = json.loads(target.read_text()) if target.exists() else {}
    probe = {r["site"]: r for r in json.loads((out / "to_classify.json").read_text())}
    todo = []
    for b in json.loads((out / "site" / "blogs.json").read_text()):
        if b["site"] in done:
            continue
        p = probe.get(b["site"], {})
        todo.append(
            {
                "site": b["site"],
                "label": b["type"],
                "name": b.get("name") or "",
                "author": b.get("author") or "",
                "home_title": (p.get("home_title") or "")[:120],
                "home_desc": (p.get("home_desc") or b.get("description") or "")[:200],
                "hn_titles": (p.get("titles") or [])[:8],
            }
        )
    batches = [todo[i : i + a.batch] for i in range(0, len(todo), a.batch)]
    print(f"{len(todo)} listings in {len(batches)} batches ({len(done)} already checked)", flush=True)
    with ThreadPoolExecutor(a.jobs) as pool:
        for n, f in enumerate(as_completed(pool.submit(run_batch, b, a.model) for b in batches), 1):
            for r in f.result():
                done[r.pop("site")] = r
            target.write_text(json.dumps(done, ensure_ascii=False))
            print(f"batch {n}/{len(batches)} done, {len(done)} checked", flush=True)


if __name__ == "__main__":
    main()
