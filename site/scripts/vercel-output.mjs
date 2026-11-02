// Turn dist/ into Vercel's prebuilt output (../.vercel/output) for `vercel deploy --prebuilt`:
// clean URLs (/jeff-atwood serves jeff-atwood.html), the 404 page, and long caching for static assets.
import { cpSync, mkdirSync, rmSync, writeFileSync } from "node:fs";

const OUT = "../.vercel/output";
rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });
cpSync("dist", `${OUT}/static`, { recursive: true });

const year = "public, max-age=31536000, immutable";
writeFileSync(
  `${OUT}/config.json`,
  JSON.stringify(
    {
      version: 3,
      routes: [
        { src: "^/_astro/(.*)$", headers: { "cache-control": year }, continue: true },
        { src: "^/icons/(.*)$", headers: { "cache-control": "public, max-age=604800" }, continue: true },
        { src: "^/(.+)\\.html$", status: 308, headers: { location: "/$1" } },
        { handle: "filesystem" },
        { src: "^/(.+)$", dest: "/$1.html", check: true },
        { handle: "error" },
        { status: 404, src: "^/(.*)$", dest: "/404.html" },
      ],
    },
    null,
    1,
  ),
);
console.log("wrote", OUT);
