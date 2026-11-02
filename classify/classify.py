"""Classify candidate sites with the local Claude Code CLI (subscription, no API key).

Reads to_classify.json, writes/extends classified.json. Resumable: sites already
in classified.json are skipped. Usage:
    python classify/classify.py data/to_classify.json data/classified.json [--batch 100] [--jobs 3] [--limit N]
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from claude_cli import ask

HERE = Path(__file__).parent
PROMPT = (HERE / "prompt.md").read_text()
KINDS = ["personal", "company", "publication", "community", "project", "other"]
TOPICS = [
    "programming",
    "systems",
    "web",
    "security",
    "ai",
    "data",
    "math",
    "science",
    "startups",
    "business",
    "economics",
    "design",
    "writing",
    "career",
    "culture",
    "politics",
    "history",
    "philosophy",
    "hardware",
    "games",
    "productivity",
    "health",
    "other",
]
SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "site": {"type": "string"},
                    "kind": {"type": "string", "enum": KINDS},
                    "homepage": {"type": "string", "enum": ["ok", "spam", "parked", "changed", "empty"]},
                    "longform": {"type": "boolean"},
                    "blog_path": {"type": "string"},
                    "author": {"type": "string"},
                    "topics": {"type": "array", "items": {"type": "string", "enum": TOPICS}, "maxItems": 3},
                    "confidence": {"type": "number"},
                },
                "required": ["site", "homepage", "kind", "longform", "blog_path", "author", "topics", "confidence"],
            },
        }
    },
    "required": ["results"],
}
FIELDS = ["site", "n_people", "titles", "urls", "status", "final_url", "home_title", "home_desc", "site_name", "has_feed_hint"]


def run_batch(batch: list[dict], model: str) -> list[dict]:
    """Classify a batch; keeps what comes back and re-asks only for missing sites. Unanswered sites are left
    for the next run (classify.py is resumable)."""
    got: dict[str, dict] = {}
    for attempt in range(3):
        missing = [s for s in batch if s["site"] not in got]
        if not missing:
            break
        payload = json.dumps([{k: s.get(k) for k in FIELDS} for s in missing], ensure_ascii=False)
        data, err = ask(f"Classify these sites:\n{payload}", PROMPT, SCHEMA, model)
        wanted = {s["site"] for s in missing}
        for r in (data or {}).get("results", []):
            if r.get("site") in wanted:
                got[r["site"]] = r
        if len(got) < len(batch):
            print(f"  attempt {attempt + 1}: {len(got)}/{len(batch)} {err}", file=sys.stderr)
    return list(got.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("todo")
    ap.add_argument("out")
    ap.add_argument("--batch", type=int, default=50)  # 150 often came back incomplete
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--model", default="haiku")
    a = ap.parse_args()

    out = Path(a.out)
    done = json.loads(out.read_text()) if out.exists() else []
    done = [r for r in done if "homepage" in r]  # results from before the audited rules get redone
    seen = {r["site"] for r in done}
    todo = [s for s in json.loads(Path(a.todo).read_text()) if s["site"] not in seen]
    # most-linked first, so the best tier is ready (and shippable) first; homepages that did not answer or are
    # gone (404/410) go last: they rarely become listings, but are still classified
    dead = lambda s: s.get("status") in (0, 404, 410)
    todo = sorted(todo, key=lambda s: (dead(s), -(s.get("n_people") or 0)))[: a.limit]
    batches = [todo[i : i + a.batch] for i in range(0, len(todo), a.batch)]
    print(f"{len(todo)} sites in {len(batches)} batches ({len(seen)} already classified)")

    with ThreadPoolExecutor(a.jobs) as pool:
        futures = {pool.submit(run_batch, b, a.model): i for i, b in enumerate(batches)}
        for n, f in enumerate(as_completed(futures), 1):
            done += f.result()
            out.write_text(json.dumps(done, ensure_ascii=False, indent=0))  # checkpoint every batch
            print(f"batch {n}/{len(batches)} done, {len(done)} classified")

    kinds = {}
    for r in done:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print("kinds:", kinds)


if __name__ == "__main__":
    main()
