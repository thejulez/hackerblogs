/** One list row, rendered on the server (first page) and in the browser (filters, show more). */
import { icon, topicIcon } from "./icons";

export type Row = {
  rank: number;
  site: string;
  slug: string;
  type: string;
  author: string;
  name: string;
  topics: string[];
  n_people: number;
  n_mentions: number;
  people_2y: number;
  first_seen: string | null;
  last_seen: string | null;
  feed_url: string | null;
  feed_title: string;
  last_post_at: string | null;
  status: string;
  why: string;
  description?: string;
  stance: { recommend: number; neutral: number; critical: number } | null;
  icon?: boolean;
  spark?: number[];
};

const SPARK_FROM = 2007;

/** Links per year since 2007 as a small line; the title names the peak. Hidden when there is too little to draw. */
function sparkline(values: number[] | undefined, w = 72, h = 20): string {
  if (!values || values.filter((v) => v > 0).length < 2) return "";
  const max = Math.max(...values);
  const step = w / (values.length - 1);
  const pts = values.map((v, i) => `${(i * step).toFixed(1)},${(h - 2 - (v / max) * (h - 4)).toFixed(1)}`).join(" ");
  const peak = values.indexOf(max) + SPARK_FROM;
  const last = values.at(-1)!;
  return (
    `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="Links per year since ${SPARK_FROM}, peak ${max} in ${peak}">` +
    `<title>Links per year since ${SPARK_FROM} · peak ${max.toLocaleString("en")} in ${peak} · ${last.toLocaleString("en")} this year</title>` +
    `<polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>`
  );
}

const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");

const rowName = (b: Pick<Row, "author" | "name" | "feed_title" | "site">) => b.author || b.name || b.feed_title || b.site;

/** Favicon with the initial underneath; a missing icon hides itself and leaves the initial. */
export const avatar = (b: Pick<Row, "slug" | "author" | "name" | "feed_title" | "site" | "icon">, size = 36) =>
  `<span class="avatar" style="width:${size}px;height:${size}px;font-size:${Math.round(size * 0.45)}px">` +
  `<span>${esc(
    rowName(b)
      .replace(/^[^\p{L}\p{N}]+/u, "")
      .charAt(0)
      .toUpperCase() || "•",
  )}</span>` +
  (b.icon ? `<img src="/icons/${encodeURIComponent(b.slug)}.png" alt="" loading="lazy" onerror="this.remove()">` : "") +
  `</span>`;

const pickData = (b: Row) => esc(JSON.stringify({ slug: b.slug, name: rowName(b), feed: b.feed_url, site: b.site }));

export function card(b: Row, extra = ""): string {
  const name = rowName(b);
  const meta = [
    sparkline(b.spark),
    `<span title="Different HN people who linked it">${b.n_people.toLocaleString("en")} people</span>`,
    b.stance && b.stance.recommend
      ? `<span title="Sampled HN comments that recommend the writing">${b.stance.recommend} recommend</span>`
      : "",
    extra,
    b.last_post_at ? `<span title="Newest post in the blog's feed">last post ${b.last_post_at.slice(0, 10)}</span>` : "",
    b.status === "stale" ? `<span class="chip" title="No new post in the last two years">inactive</span>` : "",
    b.status === "none"
      ? `<span class="chip" title="No RSS, Atom or JSON feed found, so it can't be followed">no feed</span>`
      : "",
    b.type === "company" ? `<span class="chip" title="A company or engineering blog">${icon("company", 12)}company</span>` : "",
  ].join("");
  const topics = b.topics
    .map((t) => `<a class="chip" href="/topic/${t}" title="All ${t} blogs">${icon(topicIcon(t), 12)}${t}</a>`)
    .join("");
  return `<li class="card">
  <a class="who" href="/${encodeURIComponent(b.slug)}">${avatar(b)}</a>
  <div class="body">
    <a class="name" href="/${encodeURIComponent(b.slug)}">${esc(name)}</a> <span class="muted site">${esc(b.site)}</span>
    <div class="meta muted">${meta}${topics}</div>
  </div>
  ${
    b.feed_url
      ? `<button type="button" class="pick" data-pick="${pickData(b)}" aria-pressed="false" title="Add to the blogs you follow">
    <svg class="icon" width="16" height="16" aria-hidden="true"><use href="/icons.svg#i-plus"/></svg><span class="label">Follow</span>
  </button>`
      : `<span class="pick off" title="No feed found for this blog">No feed</span>`
  }
</li>`;
}
