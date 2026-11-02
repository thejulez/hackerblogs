import type { APIRoute } from "astro";
import { blogs, meta, topics } from "../lib/data";

/** Every list, topic and blog page, with the export date as lastmod. */
export const GET: APIRoute = ({ site }) => {
  const lastmod = meta.generated_at.slice(0, 10);
  const paths = [
    "/",
    "/top",
    "/recommended",
    "/rising",
    "/about",
    "/opml",
    ...topics.map((t) => `/topic/${t}`),
    ...blogs.map((b) => `/${b.slug}`),
  ];
  const urls = paths.map((p) => `  <url><loc>${new URL(p, site)}</loc><lastmod>${lastmod}</lastmod></url>`).join("\n");
  return new Response(
    `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`,
    { headers: { "Content-Type": "application/xml" } },
  );
};
