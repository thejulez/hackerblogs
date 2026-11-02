"""Rules for which sites never get listed: the exclude list and homepage text of hijacked or parked domains.
Side-effect free, so laptop scripts can import it without the pipeline's data folders."""

import re
from pathlib import Path

# Homepage text that marks a hijacked, parked or dead domain (see data/audit/classification.md).
# ("Index of /" is not here: some real blogs have a bare root and the blog under a path)
SPAM = re.compile(
    r"casino|\bslots?\b|\bbetting\b|\btogel\b|\bgacor\b|ufabet|\bjudi\b|kèo|cá độ|poker online|online gambling"
    r"|บาคาร่า|แทงบอล|domain (is )?for sale|buy this domain|domain (is )?parked|parked (domain|with)|dynadot|\bsedo\b|hugedomains|is almost here"
    r"|under construction|sign in - google accounts|website not found|account suspended",
    re.I,
)


def exclude_list() -> list[tuple[str, bool]]:
    """exclude.txt as (domain, exact) pairs; a plain entry also matches its subdomains."""
    lines = (Path(__file__).parent / "exclude.txt").read_text().splitlines()
    return [(l.strip().lower().lstrip("="), l.strip().startswith("=")) for l in lines if l.strip() and not l.startswith("#")]


def excluded(site: str, rules: list[tuple[str, bool]]) -> bool:
    host = site.split("/")[0].lower()
    return any(host == e or (not exact and host.endswith("." + e)) for e, exact in rules)


def parked_url(final_url: str | None) -> bool:
    """Registrar landers: a homepage that redirects to /lander is a parked domain."""
    return bool(final_url) and "/lander" in final_url.lower()


def same_blog_key(site: str, final_url: str | None) -> str:
    """Key that collapses copies of one blog: country domains of a Blogspot blog, renamed domains that redirect
    to the same place. The site itself when there is no final URL."""
    from urllib.parse import urlsplit

    if not final_url:
        return site
    u = urlsplit(final_url.lower())
    host = u.netloc.removeprefix("www.")
    if ".blogspot." in host:  # name.blogspot.co.uk and name.blogspot.com are the same blog
        host = host.split(".blogspot.")[0] + ".blogspot"
    return host + u.path.rstrip("/")
