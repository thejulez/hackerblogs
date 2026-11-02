/** Write ../data/out/classified.json (or the file given) to the drive as out/classified.json.
 * Fails while a pipeline run holds the drive.   pnpm push-classified [file] */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Sandbox } from "@vercel/sandbox";
import { drive, REGION, ROOT, sh } from "./lib.ts";

const content = readFileSync(process.argv[2] ?? join(ROOT, "data", "out", "classified.json"));
JSON.parse(content.toString("utf8")); // refuse to upload a broken file
const s = await Sandbox.create({
  region: REGION,
  persistent: false,
  resources: { vcpus: 1 },
  timeout: 10 * 60_000,
  mounts: { "/data": await drive() },
});
try {
  await sh(s, "sudo chown -R $(id -u):$(id -g) /data || true; mkdir -p /data/out");
  await s.writeFiles([{ path: "/data/out/classified.json", content }]);
  console.log(await sh(s, "wc -c /data/out/classified.json"));
} finally {
  await s.stop();
}
