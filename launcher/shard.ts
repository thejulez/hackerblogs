/**
 * Probe the remaining candidates in parallel sandboxes, then hand the results to p05 through the drive.
 *   pnpm shard [n=8]
 * Needs the drive free (no pipeline run holding it). Afterwards run `pnpm launch --from 05` to classify-prep.
 */
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { Sandbox } from "@vercel/sandbox";
import { drive, pipelineFiles, REGION, ROOT, sh, withReader } from "./lib.ts";

const N = Number(process.argv[2] ?? 8);
const dir = join(ROOT, "data", "shards");
rmSync(dir, { recursive: true, force: true });
mkdirSync(dir, { recursive: true });

// 1. what is left: candidates without a successful probe, read from a snapshot of the drive
const list = await withReader(async (s) => {
  await sh(s, "pip install -q duckdb==2.0.0 >/dev/null 2>&1 || true");
  return sh(
    s,
    `python3 -c "
import duckdb
c = duckdb.connect()
done = \\"SELECT site FROM '/data/work/probe.parquet' WHERE status > 0\\"
for (s,) in c.execute(f\\"SELECT site FROM '/data/work/candidate.parquet' WHERE site NOT IN ({done})\\").fetchall(): print(s)
"`,
  );
});
const sites = list.split("\n").filter(Boolean);
console.log(`${sites.length} sites left to probe, ${N} shards`);
if (!sites.length) process.exit(0);

// 2. one sandbox per shard, probing in the background; poll until every shard has written its file
const shards = await Promise.all(
  Array.from({ length: N }, async (_, i) => {
    const part = sites.filter((_, j) => j % N === i); // interleaved, so slow hosts spread evenly
    const s = await Sandbox.create({
      image: "vercel/sandbox/python:3.14",
      region: REGION,
      persistent: false,
      resources: { vcpus: 4 },
      timeout: 3 * 3600_000,
    });
    await s.writeFiles([...pipelineFiles(), { path: "/tmp/sites.txt", content: Buffer.from(part.join("\n")) }]);
    await sh(
      s,
      "cd /vercel/sandbox/pipeline && uv venv -q /tmp/venv && uv pip install -q --python /tmp/venv/bin/python -r requirements.txt",
    );
    await s.runCommand({
      cmd: "bash",
      detached: true,
      args: [
        "-c",
        'cd /vercel/sandbox/pipeline && /tmp/venv/bin/python probe_shard.py /tmp/sites.txt /tmp/part.parquet > /tmp/log 2>&1; echo "=== SHARD EXIT $?" >> /tmp/log',
      ],
    });
    console.log(`shard ${i}: ${part.length} sites`);
    return { i, s };
  }),
);

try {
  const pending = new Set(shards.map((x) => x.i));
  while (pending.size) {
    await new Promise((r) => setTimeout(r, 60_000));
    for (const { i, s } of shards.filter((x) => pending.has(x.i))) {
      const log = await sh(s, "tail -2 /tmp/log 2>/dev/null || true");
      if (/^=== SHARD EXIT \d+$/m.test(log)) {
        const buf = await s.readFileToBuffer({ path: "/tmp/part.parquet" });
        if (buf) writeFileSync(join(dir, `part-${i}.parquet`), buf); // a failed shard still keeps its checkpoint
        pending.delete(i);
        if (/=== SHARD EXIT 0/.test(log) && buf) console.log(`shard ${i} done (${pending.size} left)`);
        else console.error(`shard ${i} failed (${buf ? "partial results kept" : "no results"}):\n${log}`);
      }
    }
    if (pending.size) console.log(new Date().toISOString(), [...pending].length, "shards running");
  }
} finally {
  await Promise.all(shards.map(({ s }) => s.stop()));
}

// 3. copy the parts onto the drive for p05 to fold in
const w = await Sandbox.create({
  region: REGION,
  persistent: false,
  resources: { vcpus: 1 },
  timeout: 15 * 60_000,
  mounts: { "/data": await drive() },
});
try {
  await sh(w, "sudo chown -R $(id -u):$(id -g) /data || true; mkdir -p /data/work/probe_shards");
  const parts = shards.filter(({ i }) => existsSync(join(dir, `part-${i}.parquet`)));
  await w.writeFiles(
    parts.map(({ i }) => ({
      path: `/data/work/probe_shards/part-${i}.parquet`,
      content: readFileSync(join(dir, `part-${i}.parquet`)),
    })),
  );
  console.log(await sh(w, "ls -la /data/work/probe_shards && sync"));
} finally {
  await w.stop();
}
console.log("next: pnpm launch --from 05");
