#!/usr/bin/env bash
# Run the pipeline phases in order. Each phase is idempotent.
#   ./run_all.sh                      full run
#   ./run_all.sh --sample 2024-01     one dump month, no API gap fill
#   ./run_all.sh --from 06            start at phase 06 (after classified.json is on the Drive)
#   ./run_all.sh --from 04 --top 50000  go deeper: more candidates, probe only the new ones
# Phases 06-08 need $HB_DATA/out/classified.json from the local classify step;
# without it the run stops after 05.
set -euo pipefail
cd "$(dirname "$0")"

SAMPLE=""
FROM=00
TOP=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sample) SAMPLE="$2"; shift 2 ;;
    --from) FROM="$2"; shift 2 ;;
    --top) TOP="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

PY=${PYTHON:-python3}
DATA=${HB_DATA:-/data}
mkdir -p "$DATA/logs"
SAMPLE_ARGS=()
[[ -n "$SAMPLE" ]] && SAMPLE_ARGS=(--sample "$SAMPLE")

phase() {
  local n="$1"; shift
  [[ "$n" < "$FROM" ]] && return 0
  local script
  script=$(ls p"$n"_*.py)
  echo "=== $(date -u +%FT%TZ) phase $n: $script $*"
  local t0=$SECONDS
  "$PY" "$script" "${SAMPLE_ARGS[@]}" "$@"
  echo "=== phase $n done in $((SECONDS - t0)) s"
}

phase 00
[[ -z "$SAMPLE" ]] && phase 01   # the gap fill only makes sense on top of the full dump
phase 02
phase 03
phase 04 ${TOP:+--top "$TOP"}
phase 05

if [[ ! -f "$DATA/out/classified.json" ]]; then
  echo "=== no classified.json yet: pull to_classify.json, run classify/classify.py, push-classified, then --from 06"
  exit 0
fi
phase 06
phase 07
phase 08
phase 09
echo "=== $(date -u +%FT%TZ) all phases done"
