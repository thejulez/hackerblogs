"""Readable URL slugs: the author's or blog's name ("jeff-atwood"), falling back to the site ("blog-codinghorror-com")."""

import re
import unicodedata

# top-level paths the site uses itself
RESERVED = {
    "top",
    "recommended",
    "rising",
    "about",
    "random",
    "opml",
    "topic",
    "data",
    "icons",
    "pagefind",
    "_astro",
    "favicon",
    "404",
    "index",
    "blog",
    "search",
    "rss",
    "feed",
}


def slugify(text: str) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60].strip("-")


def assign(rows: list[dict]) -> dict[str, str]:
    """site -> slug for rows in rank order ({site, author, name}); better-ranked blogs get the plain name."""
    taken, out = set(RESERVED), {}
    for r in rows:
        name = slugify(r.get("author") or "") or slugify(r.get("name") or "")
        site = slugify(r["site"])
        for cand in (name, site, f"{name}-{site}" if name else ""):
            if cand and len(cand) >= 3 and cand not in taken:
                break
        else:
            n = 2
            while f"{site}-{n}" in taken:
                n += 1
            cand = f"{site}-{n}"
        taken.add(cand)
        out[r["site"]] = cand
    return out
