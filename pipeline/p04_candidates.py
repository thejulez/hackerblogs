"""Phase 04: top sites by distinct people, minus the exclude list -> candidate table."""

from pathlib import Path

from common import WORK, args, connect, log


def extra(p):
    p.add_argument("--top", type=int, default=15_000)
    p.add_argument("--min-people", type=int, default=3)


a = args("pick candidate blogs", extra)
lg = log("p04")
con = connect()

exclude = [
    l.strip().lower()
    for l in (Path(__file__).parent / "exclude.txt").read_text().splitlines()
    if l.strip() and not l.startswith("#")
]
con.execute("CREATE OR REPLACE TEMP TABLE exclude(e VARCHAR, exact BOOLEAN)")
con.executemany("INSERT INTO exclude VALUES (?, ?)", [(e.lstrip("="), e.startswith("=")) for e in exclude])

con.execute(f"""
CREATE OR REPLACE TABLE candidate AS
WITH top AS (
    SELECT * FROM site_stats
    WHERE n_people >= {a.min_people}
      AND site LIKE '%.%'
      AND NOT regexp_matches(site, '^[0-9.]+$')           -- bare IPs
    ORDER BY n_people DESC, story_points DESC
    LIMIT {a.top * 2}
)
SELECT t.* FROM top t
WHERE NOT EXISTS (
    SELECT 1 FROM exclude x WHERE t.site = x.e OR (NOT x.exact AND t.site LIKE '%.' || x.e)
)
ORDER BY n_people DESC, story_points DESC
LIMIT {a.top};

-- what HN linked on each candidate: best stories and a few distinct paths
CREATE OR REPLACE TABLE candidate_samples AS
SELECT c.site,
       list(DISTINCT m.story_title ORDER BY m.story_title)
           FILTER (WHERE m.kind = 'story' AND m.story_title IS NOT NULL)[1:6] AS titles,
       list(DISTINCT m.url)[1:6] AS urls
FROM candidate c JOIN mention m USING (site)
GROUP BY c.site;
COPY candidate TO '{WORK}/candidate.parquet' (FORMAT parquet);
""")
n = con.execute("SELECT count(*) FROM candidate").fetchone()[0]
lg.info("candidates: %d (excluded list: %d entries)", n, len(exclude))
