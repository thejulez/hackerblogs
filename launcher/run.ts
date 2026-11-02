/**
 * Start the pipeline in a fresh Vercel Sandbox with the hackerblogs-data drive at /data.
 *   pnpm launch                   full run (00-05, then 06-08 if classified.json is on the drive)
 *   pnpm launch --sample 2024-01  one month smoke run
 *   pnpm launch --from 06         feeds, profiles, export after push-classified
 *   pnpm launch --from 04 --top 50000  more candidates; only new sites get probed
 * The run is detached: the laptop can close. Follow it with `pnpm status`.
 */
import { Sandbox } from "@vercel/sandbox";
import { drive, pipelineFiles, REGION, saveRun, sh } from "./lib.ts";

const args = process.argv.slice(2);
if (args.some((a) => !/^(--sample|--from|--top|\d{4}-\d{2}|\d+)$/.test(a))) {
  throw new Error(`unexpected arguments: ${args.join(" ")}`);
}
const sample = args.includes("--sample");
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const name = `hackerblogs-pipeline-${stamp.toLowerCase()}`;
const log = `/data/logs/run-${stamp}.log`;

const d = await drive();
const s = await Sandbox.create({
  name,
  image: "vercel/sandbox/python:3.14",
  region: REGION,
  persistent: false,
  resources: { vcpus: 8 },
  timeout: (sample ? 2 : 24) * 3600_000,
  mounts: { "/data": d },
});
console.log(`sandbox ${name} up`);

await s.writeFiles(pipelineFiles());
await sh(s, "sudo chown -R $(id -u):$(id -g) /data || true; mkdir -p /data/logs /vercel/sandbox/tmp");
await sh(
  s,
  [
    "cd /vercel/sandbox/pipeline",
    "uv venv -q /vercel/sandbox/.venv",
    "uv pip install -q --python /vercel/sandbox/.venv/bin/python -r requirements.txt",
  ].join(" && "),
);
console.log("dependencies installed");

const run = [
  "cd /vercel/sandbox/pipeline",
  `PYTHON=/vercel/sandbox/.venv/bin/python HB_DATA=/data HB_TMP=/vercel/sandbox/tmp ./run_all.sh ${args.join(" ")} >> ${log} 2>&1`,
  `echo "=== exit $?" >> ${log}`,
  "sync",
].join("; ");
await s.runCommand({ cmd: "bash", args: ["-c", run], detached: true });
saveRun({ name, log, startedAt: new Date().toISOString() });
console.log(`running detached, log ${log}\nfollow with: pnpm status (stops the sandbox once the run has exited)`);
