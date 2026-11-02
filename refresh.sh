#!/usr/bin/env bash
# Weekly refresh: new HN items -> new candidates -> classification -> feeds -> summaries -> checked links -> deploy.
#   ./refresh.sh            full refresh, deploys to production when validation passes
#   ./refresh.sh --preview  same, but deploys a preview only
# Needs: Node 24 + pnpm, Python 3.14 with uv, the Vercel CLI linked to the project, Claude Code signed in.
# Every step is resumable; rerunning after a failure picks up where it stopped. Logs go to data/refresh.log.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.nvm/versions/node/v24.21.0/bin:$PATH"
PROD="--prod"
[[ "${1:-}" == "--preview" ]] && PROD=""
exec > >(tee -a data/refresh.log) 2>&1

log() { echo "=== $(date -u +%FT%TZ) $*"; }
wait_run() { until (cd launcher && pnpm -s status 2>&1 | grep -q "=== exit"); do sleep 120; done; (cd launcher && pnpm -s status | tail -3); }

log "1. new HN items, links and candidates (Sandbox: phases 01-09 with last week's classification)"
(cd launcher && pnpm -s launch --from 01) && wait_run
(cd launcher && pnpm -s pull)

log "2. classify the new candidates (local Claude Code), then feeds, profiles and export for them"
python3 -u classify/classify.py data/out/to_classify.json data/out/classified.json --jobs 16
(cd launcher && pnpm -s push-classified && pnpm -s launch --from 06) && wait_run
(cd launcher && pnpm -s pull)

log "3. thread titles from the HN API, comment summaries for new blogs, second opinion on new listings"
uv run -q --with httpx==0.28.1 python pipeline/fill_titles.py data/out
python3 pipeline/merge_summaries.py data/out
python3 pipeline/to_summarize.py data/out
python3 -u classify/summarize.py data/out/to_summarize.json data/out/summaries.json --jobs 6
(cd classify && python3 -u verify.py ../data/out --jobs 12)

log "4. check every link from a Sandbox (dead links fall back or open the Web Archive)"
python3 pipeline/merge_summaries.py data/out
python3 pipeline/links_due.py data/out  # new links, failing ones and a monthly quarter of the rest
(cd launcher && pnpm -s check-urls)
python3 pipeline/merge_summaries.py data/out
python3 pipeline/validate.py data/out

log "5. build and deploy"
(cd site && pnpm -s data && pnpm -s build && pnpm -s vercel-output)
npx vercel deploy --prebuilt $PROD --archive=tgz
log "done"
