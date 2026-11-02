"""Find the writer's name for personal blogs that have none, from what the blog itself publishes.

    python classify/authors.py data/out [--jobs 12]

Evidence per blog: its name, homepage title and description, feed title, its own HN profile text (when the profile
links the site) and top post titles. Never outside knowledge: a pseudonymous blog stays without a name.
Writes data/out/authors.json ({site: name}); merge_summaries.py applies it.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from claude_cli import ask

SYSTEM = """You read evidence a personal blog publishes about itself and give the writer's full name.
Use only the input: a byline ("by X"), a site or feed title that is a person's name, "Hi, I'm X", or the blog's own
Hacker News profile text. Do not use anything you know from elsewhere: if the input does not name the writer,
answer "". Never answer an organisation, a handle, or a first name alone.
Return one result per input site, same order, with `site` copied and `author`."""

SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"site": {"type": "string"}, "author": {"type": "string"}},
                "required": ["site", "author"],
            },
        }
    },
    "required": ["results"],
}


def run_batch(batch: list[dict], model: str) -> list[dict]:
    data, _ = ask(f"Name the writers:\n{json.dumps(batch, ensure_ascii=False)}", SYSTEM, SCHEMA, model)
    want = {s["site"] for s in batch}
    return [r for r in (data or {}).get("results", []) if r.get("site") in want]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="data/out")
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--jobs", type=int, default=12)
    a = ap.parse_args()
    out = Path(a.out)
    target = out / "authors.json"
    done = json.loads(target.read_text()) if target.exists() else {}
    probe = {r["site"]: r for r in json.loads((out / "to_classify.json").read_text())}
    todo = []
    for b in json.loads((out / "site" / "blogs.json").read_text()):
        if b["type"] != "personal" or b.get("author") or b["site"] in done:
            continue
        d = json.loads((out / "site" / "blog" / f"{b['slug']}.json").read_text())
        prof = d.get("author_profile") or {}
        todo.append(
            {
                "site": b["site"],
                "name": b.get("name") or "",
                "home_title": (probe.get(b["site"], {}).get("home_title") or "")[:120],
                "description": (d.get("description") or "")[:200],
                "feed_title": b.get("feed_title") or "",
                "own_hn_profile": (prof.get("about") or "")[:300],
                "posts": [p["title"] for p in d.get("posts", [])[:5] if p.get("title")],
            }
        )
    batches = [todo[i : i + a.batch] for i in range(0, len(todo), a.batch)]
    print(f"{len(todo)} blogs in {len(batches)} batches ({len(done)} already done)", flush=True)
    with ThreadPoolExecutor(a.jobs) as pool:
        for n, f in enumerate(as_completed(pool.submit(run_batch, b, a.model) for b in batches), 1):
            for r in f.result():
                done[r["site"]] = r["author"].strip()
            target.write_text(json.dumps(done, ensure_ascii=False))
            print(f"batch {n}/{len(batches)} done, {sum(1 for v in done.values() if v)} named", flush=True)


if __name__ == "__main__":
    main()
