import { readdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { config } from "dotenv";
import { Drive, Sandbox } from "@vercel/sandbox";

// OIDC token from `vercel env pull .env.local` in the repo root (valid ~12 h).
config({ path: join(import.meta.dirname, "..", ".env.local"), quiet: true });

export const ROOT = join(import.meta.dirname, "..");
export const REGION = "iad1"; // a sandbox must run in its drive's region
export const STATE = join(import.meta.dirname, ".last-run.json");

export async function drive(): Promise<Drive> {
  return Drive.getOrCreate({ name: "hackerblogs-data", region: REGION, maxSize: 200 * 2 ** 30 });
}

export function pipelineFiles(): { path: string; content: Buffer; mode?: number }[] {
  const dir = join(ROOT, "pipeline");
  return readdirSync(dir)
    .filter((f) => /\.(py|sh|txt)$/.test(f))
    .map((f) => ({
      path: `/vercel/sandbox/pipeline/${f}`,
      content: readFileSync(join(dir, f)),
      ...(f.endsWith(".sh") ? { mode: 0o755 } : {}),
    }));
}

export function lastRun(): { name: string; log: string; startedAt: string } | null {
  return existsSync(STATE) ? JSON.parse(readFileSync(STATE, "utf8")) : null;
}

export function saveRun(run: { name: string; log: string; startedAt: string }) {
  writeFileSync(STATE, JSON.stringify(run, null, 1));
}

/** Throwaway 1-vCPU sandbox with a read-only snapshot of the drive at /data. */
export async function withReader<T>(fn: (s: Sandbox) => Promise<T>): Promise<T> {
  const d = await drive();
  const s = await Sandbox.create({
    region: REGION,
    persistent: false,
    resources: { vcpus: 1 },
    timeout: 15 * 60_000,
    mounts: { "/data": d.snapshot() },
  });
  try {
    return await fn(s);
  } finally {
    await s.stop();
  }
}

/** Run a shell command; throw with stderr on non-zero exit. */
export async function sh(s: Sandbox, script: string, opts: { sudo?: boolean } = {}): Promise<string> {
  const r = await s.runCommand({ cmd: "bash", args: ["-c", script], sudo: opts.sudo });
  if (r.exitCode !== 0) throw new Error(`${script}\n-> exit ${r.exitCode}\n${await r.stderr()}`);
  return r.stdout();
}
