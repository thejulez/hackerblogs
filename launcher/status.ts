/**
 * Show the last run's sandbox state and log tail. `pnpm status [--stop]`
 * A finished run (log ends with "=== exit") is stopped so it does not idle until its timeout;
 * the drive's data is readable by other sandboxes only after that.
 */
import { Sandbox } from "@vercel/sandbox";
import { lastRun, sh, withReader } from "./lib.ts";

const run = lastRun();
if (!run) throw new Error("no run recorded in .last-run.json");
const s = await Sandbox.get({ name: run.name, resume: false });
console.log(`${run.name}: ${s.status} (started ${run.startedAt})`);

const tail = `tail -n 40 ${run.log} 2>/dev/null || echo 'no log yet'`;
const out = s.status === "running" ? await sh(s, tail) : "";
const finished = /=== exit \d+/.test(out);
if (s.status === "running" && (finished || process.argv.includes("--stop"))) {
  await s.stop();
  console.log("stopped");
}
console.log(s.status === "running" ? out : await withReader((r) => sh(r, tail)));
