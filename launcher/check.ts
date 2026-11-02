/**
 * Check every listed blog link from a Sandbox (not the home network):
 *   pnpm check-urls   reads ../data/out/urls.json, writes ../data/out/url_check.json
 */
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { Sandbox } from "@vercel/sandbox";
import { pipelineFiles, REGION, ROOT, sh } from "./lib.ts";

const s = await Sandbox.create({
  image: "vercel/sandbox/python:3.14",
  region: REGION,
  persistent: false,
  resources: { vcpus: 4 },
  timeout: 60 * 60_000,
});
try {
  await s.writeFiles([
    ...pipelineFiles(),
    { path: "/tmp/urls.json", content: readFileSync(join(ROOT, "data", "out", "urls.json")) },
  ]);
  await sh(
    s,
    "cd /vercel/sandbox/pipeline && uv venv -q /tmp/venv && uv pip install -q --python /tmp/venv/bin/python -r requirements.txt",
  );
  const r = await s.runCommand({
    cmd: "bash",
    args: [
      "-c",
      "cd /vercel/sandbox/pipeline && HB_DATA=/tmp/hb /tmp/venv/bin/python check_urls.py /tmp/urls.json /tmp/out.json",
    ],
    stdout: process.stdout,
    stderr: process.stderr,
  });
  if (r.exitCode !== 0) throw new Error(`check_urls exit ${r.exitCode}`);
  const buf = await s.readFileToBuffer({ path: "/tmp/out.json" });
  if (!buf) throw new Error("no result");
  writeFileSync(join(ROOT, "data", "out", "url_check.json"), buf);
  console.log("wrote data/out/url_check.json");
} finally {
  await s.stop();
}
