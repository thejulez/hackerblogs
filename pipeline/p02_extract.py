"""Phase 02: every outbound link on HN -> mention table.

One row per (item, link): story URLs and hrefs inside comment HTML. Comments are
walked up to their root story so each mention knows its thread.
"""

from common import WORK, args, connect, items_sql, log

a = args("extract links")
lg = log("p02")
con = connect()

con.execute(r"""
CREATE OR REPLACE MACRO host_of(u) AS
    lower(regexp_extract(u, '^[a-zA-Z]+://([^/:?#@]+)', 1));
-- one key per blog: the host without www/m., except medium.com/@user
CREATE OR REPLACE MACRO site_of(u) AS CASE
    WHEN regexp_replace(host_of(u), '^(www\d?|m|mobile)\.', '') = 'medium.com'
         AND regexp_matches(u, '^[a-zA-Z]+://[^/]+/@[^/?#]+')
        THEN 'medium.com/' || lower(regexp_extract(u, '^[a-zA-Z]+://[^/]+/(@[^/?#]+)', 1))
    ELSE regexp_replace(host_of(u), '^(www\d?|m|mobile)\.', '')
END;
CREATE OR REPLACE MACRO unescape(s) AS
    replace(replace(replace(replace(s, '&#x2F;', '/'), '&amp;', '&'), '&#x27;', ''''), '&quot;', '"');
""")

src = items_sql()
lg.info("building tree + stories")
con.execute(f"""
CREATE OR REPLACE TABLE tree AS
    SELECT id, parent, type FROM {src} WHERE coalesce(deleted, 0) = 0;
CREATE OR REPLACE TABLE stories AS
    SELECT id, title, "by", time, score, url FROM {src}
    WHERE type = 1 AND coalesce(deleted, 0) = 0 AND coalesce(dead, 0) = 0;
""")

lg.info("extracting comment hrefs")
con.execute(f"""
CREATE OR REPLACE TABLE comment_links AS
    SELECT id AS item_id, "by", time AS ts, parent AS root,
           unescape(unnest(regexp_extract_all(text, 'href="([^"]+)"', 1))) AS url
    FROM {src}
    WHERE type = 2 AND coalesce(deleted, 0) = 0 AND coalesce(dead, 0) = 0
      AND text LIKE '%href=%';
""")

lg.info("resolving root stories")
for depth in range(200):  # noqa: B007 -- read after the loop
    n = con.execute("""
        UPDATE comment_links SET root = t.parent
        FROM tree t WHERE comment_links.root = t.id AND t.type = 2
    """).fetchone()[0]
    if n == 0:
        break
lg.info("roots resolved after %d passes", depth)

con.execute(f"""
CREATE OR REPLACE TABLE mention AS
WITH m AS (
    SELECT id AS item_id, 'story' AS kind, "by", time AS ts, url, id AS story_id
    FROM stories WHERE url <> ''
    UNION ALL
    SELECT item_id, 'comment', "by", ts, url, root FROM comment_links
)
SELECT m.item_id, m.kind, m."by", m.ts, m.url, site_of(m.url) AS site,
       m.story_id, s.title AS story_title, s.score AS story_score
FROM m LEFT JOIN stories s ON s.id = m.story_id
WHERE m.url LIKE 'http%' AND site_of(m.url) <> '' AND m."by" IS NOT NULL;
COPY mention TO '{WORK}/mention.parquet' (FORMAT parquet);
""")
n, sites = con.execute("SELECT count(*), count(DISTINCT site) FROM mention").fetchone()
lg.info("mention rows %d, distinct sites %d", n, sites)
