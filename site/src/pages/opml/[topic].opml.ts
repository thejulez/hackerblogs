import type { APIRoute } from "astro";
import { blogs, opml, topics } from "../../lib/data";

export function getStaticPaths() {
  return topics.map((topic) => ({ params: { topic } }));
}

export const GET: APIRoute = ({ params }) =>
  new Response(
    opml(
      `Hacker Blogs: ${params.topic}`,
      blogs.filter((b) => b.status === "ok" || (b.status === "undated" && b.topics.includes(params.topic!))),
    ),
    { headers: { "Content-Type": "text/x-opml; charset=utf-8" } },
  );
