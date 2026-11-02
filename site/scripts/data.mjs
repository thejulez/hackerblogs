// Copy the pipeline export (../data/out/site) into the site, slimmed for the browser:
// - src/data/: everything the build reads (blogs.json, meta.json, blog/*.json)
// - public/data/blogs.json: only the fields the list, filters and search use
// - public/data/mentions/: the "show more" lists, capped
// - public/icons/: favicons, and an `icon` flag only where the file exists
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";

const SRC = "../data/out/site";
const MORE = 150; // mentions per blog behind "show more"
const EXCERPT = 420; // characters per comment excerpt
const trim = (m) =>
  m.snippet && m.snippet.length > EXCERPT
    ? {
        ...m,
        snippet:
          m.snippet
            .slice(0, EXCERPT - 1)
            .toWellFormed()
            .replace(/\uFFFD$/, "")
            .trimEnd() + "…" /* a cut emoji leaves half a surrogate pair, which breaks the JSON build */,
      }
    : m;
const KEEP = [
  "rank",
  "site",
  "slug",
  "type",
  "author",
  "name",
  "topics",
  "n_people",
  "people_2y",
  "first_seen",
  "last_seen",
  "feed_url",
  "feed_title",
  "last_post_at",
  "status",
  "why",
  "description",
  "stance",
  "spark",
  "icon",
];

// Page titles make poor names ("Home \\ Anthropic", "Blog - Astral", "Mailgun | Transactional Email API…"):
// split on title separators, drop generic parts and taglines, prefer the part that matches the domain
const GENERIC =
  /^(home|homepage|blog|the blog|blog posts|posts|articles|writing|writings|index|welcome|news|rss feed|atom feed|feed|rss|medium|substack|english)$/i;
const alnum = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
// homepage meta descriptions carry platform boilerplate ("Click to read X, a Substack publication with
// tens of thousands of subscribers."); keep the author's own words
const BOILER = [
  /\s*Click to read [^.]*?, (?:a|an) Substack publication(?: with [^.]*? subscribers)?\.?/gi,
  /\s*(?:A|a) Substack publication(?: with [^.]*? subscribers)?\.?/g,
  /\s*Read [^.]*? on Medium\.?/g,
  /\s*Subscribe (?:now|for free)[^.]*\.?/g,
];
function cleanDesc(s) {
  if (!s) return s;
  for (const re of BOILER) s = s.replace(re, "");
  return s.replace(/\s{2,}/g, " ").trim();
}

function cleanName(name, site) {
  if (!name) return name;
  const s = name
    .replace(/('s)?\s+(rss|atom)?\s*feed$|\s+rss$/i, "")
    .replace(/\s+(\||—|–|-|·|\\|::|»)\s*$/, "")
    .trim();
  const parts = [];
  for (const p of s.split(/\s+(?:\||—|–|-|·|\\|::|»)\s+/).map((p) => p.trim())) {
    if (p && !GENERIC.test(p) && !parts.some((q) => alnum(q) === alnum(p))) parts.push(p);
  }
  if (!parts.length) return site;
  if (parts.length === 1) return parts[0];
  const labels = site
    .replace(/^www\./, "")
    .split("/")[0]
    .split(".")
    .slice(0, -1)
    .map(alnum)
    .filter((l) => l.length > 2);
  const hit = parts.filter((p) => labels.some((l) => alnum(p).includes(l) || (alnum(p).length > 2 && l.includes(alnum(p)))));
  const shortest = (xs) => xs.reduce((a, b) => (b.length < a.length ? b : a));
  if (hit.length) return shortest(hit);
  const short = shortest(parts);
  return short.split(/\s+/).length <= 4 ? short : parts[0];
}

for (const d of ["src/data", "public/data", "public/icons"]) rmSync(d, { recursive: true, force: true });
mkdirSync("src/data/blog", { recursive: true });
mkdirSync("public/data/mentions", { recursive: true });

for (const f of readdirSync(`${SRC}/blog`)) {
  const d = JSON.parse(readFileSync(`${SRC}/blog/${f}`, "utf8"));
  d.mentions = d.mentions.map(trim);
  d.name = cleanName(d.name, d.site);
  d.description = cleanDesc(d.description);
  writeFileSync(`src/data/blog/${f}`, JSON.stringify(d));
}
cpSync(`${SRC}/meta.json`, "src/data/meta.json");
// the archive: heavily linked blogs that are gone, parked or changed hands (classify/archive.py, checked by hand rules)
const ARCHIVE = "../data/out/archive.keep.json";
writeFileSync("src/data/archive.json", existsSync(ARCHIVE) ? readFileSync(ARCHIVE, "utf8") : "[]");
if (existsSync(`${SRC}/icons`)) cpSync(`${SRC}/icons`, "public/icons", { recursive: true });
const icons = new Set(existsSync("public/icons") ? readdirSync("public/icons") : []);

const blogs = JSON.parse(readFileSync(`${SRC}/blogs.json`, "utf8"));
for (const b of blogs) {
  b.icon = icons.has(`${b.slug}.png`);
  b.name = cleanName(b.name, b.site);
  b.description = cleanDesc(b.description);
}
writeFileSync("src/data/blogs.json", JSON.stringify(blogs));
writeFileSync(
  "public/data/blogs.json",
  JSON.stringify(
    blogs.map((b) => Object.fromEntries(KEEP.filter((k) => k in b && b[k] != null && b[k] !== "").map((k) => [k, slim(k, b)]))),
  ),
);

// the browser list only searches, sorts and filters: dates to the day, search text cut short, no feed title when a name exists
function slim(k, b) {
  const v = b[k];
  if (k === "first_seen" || k === "last_seen" || k === "last_post_at") return v.slice(0, 10);
  if (k === "description" || k === "why") return v.slice(0, 140);
  if (k === "feed_title" && (b.author || b.name)) return undefined;
  return v;
}

const listed = new Set(blogs.map((b) => b.slug));
let n = 0;
if (existsSync(`${SRC}/mentions`)) {
  for (const f of readdirSync(`${SRC}/mentions`)) {
    const slug = f.replace(/\.json$/, "");
    // skip files an older export left behind: only blogs with more mentions than their page shows have a list
    if (!listed.has(slug) || !JSON.parse(readFileSync(`src/data/blog/${f}`, "utf8")).n_more) continue;
    const rows = JSON.parse(readFileSync(`${SRC}/mentions/${f}`, "utf8"))
      .slice(0, MORE)
      .map(trim);
    writeFileSync(`public/data/mentions/${f}`, JSON.stringify(rows));
    n++;
  }
}
console.log(`${blogs.length} blogs, ${icons.size} icons, ${n} mention lists`);
