"""Judge which gone, parked or hijacked sites were blogs, from their Hacker News history alone.

    python classify/archive.py data/out/to_archive.json data/out/archive.json [--jobs 8]

The homepage tells nothing (it is dead or now something else), so the model sees only the titles and URLs
HN linked. Results are kept per site, so a stopped run resumes.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from claude_cli import ask

SYSTEM = """You judge sites that Hacker News linked often but that are now gone, parked or taken over.
From the HN story titles and linked URLs only, decide what each site was while HN linked it:
- `personal`: a blog or essay series by one identifiable person (or a named duo), e.g. diveintomark.org, blog.pmarca.com.
- `company`: a company or lab blog with long-form writing (engineering, research, essays), e.g. blog.fogcreek.com.
- `other`: anything else (news site, product, tool, forum, docs, aggregator, government, CDN, a single project).
Give `name` (the blog's name as HN knew it), `author` (the person, only if titles or URLs make it clear, else ""),
`what` (one plain sentence under 100 characters on what it was known for on HN) and `confidence` 0-1.
Return one result per input site, same order, `site` copied exactly."""

SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "site": {"type": "string"},
                    "was": {"type": "string", "enum": ["personal", "company", "other"]},
                    "name": {"type": "string"},
                    "author": {"type": "string"},
                    "what": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["site", "was", "name", "author", "what", "confidence"],
            },
        }
    },
    "required": ["results"],
}


def run_batch(batch: list[dict], model: str) -> list[dict]:
    payload = json.dumps([{k: s[k] for k in ("site", "titles", "urls")} for s in batch], ensure_ascii=False)
    data, _ = ask(f"Judge these sites:\n{payload}", SYSTEM, SCHEMA, model)
    want = {s["site"] for s in batch}
    return [r for r in (data or {}).get("results", []) if r.get("site") in want]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()
    out = Path(a.output)
    done = {r["site"]: r for r in json.loads(out.read_text())} if out.exists() else {}
    todo = [s for s in json.loads(Path(a.input).read_text()) if s["site"] not in done]
    batches = [todo[i : i + a.batch] for i in range(0, len(todo), a.batch)]
    print(f"{len(todo)} sites in {len(batches)} batches ({len(done)} already judged)", flush=True)
    with ThreadPoolExecutor(a.jobs) as pool:
        for n, f in enumerate(as_completed(pool.submit(run_batch, b, a.model) for b in batches), 1):
            for r in f.result():
                done[r["site"]] = r
            out.write_text(json.dumps(list(done.values()), ensure_ascii=False))
            print(f"batch {n}/{len(batches)} done, {len(done)} judged", flush=True)


if __name__ == "__main__":
    main()
