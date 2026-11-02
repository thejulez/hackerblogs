import type { APIRoute } from "astro";
import { blogs, opml } from "../../lib/data";

export const GET: APIRoute = () =>
  new Response(opml("Hacker Blogs: top 100", blogs.filter((b) => b.status === "ok" || b.status === "undated").slice(0, 100)), {
    headers: { "Content-Type": "text/x-opml; charset=utf-8" },
  });
