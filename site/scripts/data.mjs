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
  writeFileSync(`src/data/blog/${f}`, JSON.stringify(d));
}
cpSync(`${SRC}/meta.json`, "src/data/meta.json");
if (existsSync(`${SRC}/icons`)) cpSync(`${SRC}/icons`, "public/icons", { recursive: true });
const icons = new Set(existsSync("public/icons") ? readdirSync("public/icons") : []);

const blogs = JSON.parse(readFileSync(`${SRC}/blogs.json`, "utf8"));
for (const b of blogs) {
  b.icon = icons.has(`${b.slug}.png`);
  b.name = cleanName(b.name, b.site);
}
writeFileSync("src/data/blogs.json", JSON.stringify(blogs));
writeFileSync(
  "public/data/blogs.json",
  JSON.stringify(blogs.map((b) => Object.fromEntries(KEEP.filter((k) => k in b).map((k) => [k, b[k]])))),
);

const listed = new Set(blogs.map((b) => b.slug));
let n = 0;
if (existsSync(`${SRC}/mentions`)) {
  for (const f of readdirSync(`${SRC}/mentions`)) {
    if (!listed.has(f.replace(/\.json$/, ""))) continue;
    const rows = JSON.parse(readFileSync(`${SRC}/mentions/${f}`, "utf8"))
      .slice(0, MORE)
      .map(trim);
    writeFileSync(`public/data/mentions/${f}`, JSON.stringify(rows));
    n++;
  }
}
console.log(`${blogs.length} blogs, ${icons.size} icons, ${n} mention lists`);
