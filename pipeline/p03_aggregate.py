"""Phase 03: per-site stats from the mention table."""

from common import WORK, args, connect, log

a = args("aggregate sites")
lg = log("p03")
con = connect()

con.execute(f"""
CREATE OR REPLACE TABLE site_stats AS
SELECT site,
       count(*)                                         AS n_mentions,
       count(DISTINCT "by")                             AS n_people,
       count(*) FILTER (WHERE kind = 'story')           AS n_stories,
       count(*) FILTER (WHERE kind = 'comment')         AS n_comment_links,
       count(DISTINCT "by") FILTER (WHERE kind = 'comment') AS n_comment_people,
       coalesce(sum(story_score) FILTER (WHERE kind = 'story'), 0) AS story_points,
       count(DISTINCT "by") FILTER (WHERE ts >= now() - INTERVAL 2 YEAR) AS people_2y,
       min(ts) AS first_ts,
       max(ts) AS last_ts
FROM mention
GROUP BY site;
COPY site_stats TO '{WORK}/site_stats.parquet' (FORMAT parquet);
""")
n = con.execute("SELECT count(*) FROM site_stats WHERE n_people >= 3").fetchone()[0]
lg.info("sites with >=3 distinct people: %d", n)
