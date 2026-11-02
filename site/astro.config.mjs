import { defineConfig } from "astro/config";

export default defineConfig({ site: "https://www.hackerblogs.org", trailingSlash: "never", build: { format: "file" } });
