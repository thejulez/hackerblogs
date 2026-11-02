/**
 * Re-run the export phases (08 export, 09 icons) on a read-only snapshot of the drive and pull the result
 * into ../data/out. Works while a pipeline run holds the drive: the snapshot is the drive as of the last stop.
 *   pnpm export
 */
import { mkdirSync, writeFileSync, existsSync, readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join } from "node:path";
import { Sandbox } from "@vercel/sandbox";
import { drive, pipelineFiles, REGION, ROOT, sh } from "./lib.ts";

const d = await drive();
const s = await Sandbox.create({
  image: "vercel/sandbox/python:3.14",
  region: REGION,
  persistent: false,
  resources: { vcpus: 8 },
  timeout: 60 * 60_000,
  mounts: { "/data": d.snapshot() },
});
try {
  await s.writeFiles(pipelineFiles());
  const local = join(ROOT, "data", "out", "summaries.json");
  if (existsSync(local)) await s.writeFiles([{ path: "/tmp/out/summaries.json", content: readFileSync(local) }]);
  await sh(
    s,
    [
      "mkdir -p /tmp/out /tmp/tmp /tmp/icons && cp /data/out/classified.json /tmp/out/",
      "cd /vercel/sandbox/pipeline && uv venv -q /tmp/venv && uv pip install -q --python /tmp/venv/bin/python -r requirements.txt",
    ].join(" && "),
  );
  console.log("exporting from the snapshot");
  const env = "HB_READONLY=1 HB_OUT=/tmp/out HB_LOGS=/tmp/logs HB_TMP=/tmp/tmp HB_ICON_CACHE=/tmp/icons";
  const r = await s.runCommand({
    cmd: "bash",
    args: [
      "-c",
      `set -o pipefail; cd /vercel/sandbox/pipeline && ${env} /tmp/venv/bin/python p08_export.py 2>&1 | tail -25 && ${env} /tmp/venv/bin/python p09_icons.py 2>&1 | tail -5`,
    ],
  });
  console.log(await r.stdout());
  if (r.exitCode !== 0) throw new Error(`export failed (exit ${r.exitCode})`);
  await sh(s, "tar czf /tmp/export.tgz -C /tmp out/site out/to_summarize.json");
  const tgz = await s.readFileToBuffer({ path: "/tmp/export.tgz" });
  if (!tgz) throw new Error("export.tgz missing");
  const dest = join(ROOT, "data");
  mkdirSync(dest, { recursive: true });
  writeFileSync(join(dest, "export.tgz"), tgz);
  execFileSync("rm", ["-rf", join(dest, "out", "site")]);
  execFileSync("tar", ["xzf", "export.tgz"], { cwd: dest });
  console.log(`pulled ${(tgz.length / 1e6).toFixed(1)} MB into ${dest}/out`);
} finally {
  await s.stop();
}
