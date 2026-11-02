import blogs from "../data/blogs.json";
import meta from "../data/meta.json";

type Blog = (typeof blogs)[number];
type Stance = "recommend" | "neutral" | "critical";
type Mention = {
  id: number;
  kind: "story" | "comment";
  by: string;
  date: string | null;
  story_id: number | null;
  title: string;
  points: number | null;
  url: string;
  snippet: string;
  stance?: Stance;
};
type BlogDetail = Blog & {
  feed_kind: string;
  n_entries: number;
  blog_path: string;
  description: string;
  praised_for?: string;
  criticized_for?: string;
  author_profile: { id: string; karma: number | null; created: string | null; about: string } | null;
  years: { year: number; people: number; mentions: number }[];
  linkers: { by: string; n_links: number; karma: number | null; is_author: boolean }[];
  posts: { url: string; title: string; people: number; mentions: number; first: string | null }[];
  related: { site: string; slug: string; shared: number }[];
  mentions: Mention[];
  n_more: number;
};

const details = import.meta.glob<BlogDetail>("../data/blog/*.json", { eager: true, import: "default" });

export { blogs, meta };
export const detail = (slug: string): BlogDetail => details[`../data/blog/${slug}.json`];
export const bySlug = new Map(blogs.map((b) => [b.slug, b]));
export const topics = [...new Set(blogs.flatMap((b) => b.topics))].sort();

export const HN = "https://news.ycombinator.com";
export const day = (iso: string | null) => (iso ? iso.slice(0, 10) : "");
export const blogName = (b: Blog) => b.author || b.name || b.feed_title || b.site;

const xml = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&apos;");

export function opml(title: string, list: Blog[]): string {
  const items = list
    .map(
      (b) =>
        `    <outline type="rss" text="${xml(blogName(b))}" title="${xml(blogName(b))}" xmlUrl="${xml(b.feed_url)}" htmlUrl="${xml(b.url ?? `https://${b.site}`)}"/>`,
    )
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>${xml(title)}</title></head>
  <body>
${items}
  </body>
</opml>
`;
}

/** Facts the page texts quote, computed from the data at build time so the copy never drifts from it. */
const sampled = blogs.map((b) => (b.stance ? b.stance.recommend + b.stance.neutral + b.stance.critical : 0));
export const facts = {
  minPeople: Math.min(...blogs.map((b) => b.n_people)),
  firstYear: Number(meta.years?.[0]?.year ?? 2007),
  maxSample: Math.max(0, ...sampled),
  summarized: sampled.filter((n) => n > 0).length,
  kinds: blogs.some((b) => b.type === "company") ? "personal and company blogs" : "personal blogs",
  candidates: Number(meta.n_candidates ?? 0),
  candidateMin: Number(meta.candidate_min_people ?? 3),
  classified: Number(meta.n_classified ?? 0),
  updated: new Date(meta.generated_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }),
};
