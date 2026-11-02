import type { APIRoute } from "astro";
import { ICONS, symbol } from "../lib/icons";

/** All icons as one SVG sprite, cached by the browser and shared by every page. */
export const GET: APIRoute = () =>
  new Response(`<svg xmlns="http://www.w3.org/2000/svg">${Object.keys(ICONS).map(symbol).join("")}</svg>`, {
    headers: { "Content-Type": "image/svg+xml" },
  });
