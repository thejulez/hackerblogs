/** Copy /data/out from the drive to ../data/out (to_classify.json, site/ JSON), keeping the local classified.json. */
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join } from "node:path";
import { ROOT, sh, withReader } from "./lib.ts";

const dest = join(ROOT, "data");
mkdirSync(dest, { recursive: true });
const tgz = await withReader(async (s) => {
  await sh(s, "tar czf /tmp/out.tgz -C /data out");
  return s.readFileToBuffer({ path: "/tmp/out.tgz" });
});
if (!tgz) throw new Error("out.tgz missing in sandbox");
writeFileSync(join(dest, "out.tgz"), tgz);
// classified.json and summaries.json are written on this laptop: never let the drive's older copies replace them
rmSync(join(dest, "out", "site"), { recursive: true, force: true }); // stale per-blog files must not outlive an export
execFileSync("tar", ["xzf", "out.tgz", "--exclude", "out/classified.json", "--exclude", "out/summaries*.json"], { cwd: dest });
console.log(`pulled ${(tgz.length / 1e6).toFixed(1)} MB into ${dest}/out`);
