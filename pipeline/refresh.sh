#!/usr/bin/env bash
# Daily refresh wrapper.
#
#   1. (TODO) pull latest spoilage rows from SCM DB → cache/spec_*.csv|.json
#   2. transform: run build_v2.py → output/*.csv + output/dashboard_payload.json
#   3. render: run build_dashboard.py → output/dashboard.html
#   4. copy outputs to docs/ (GitHub Pages source)
#   5. write docs/data/build_meta.json with timestamp + commit
#   6. git commit + push if anything changed
#
# Usage:
#   pipeline/refresh.sh              # build + commit + push
#   pipeline/refresh.sh --no-push    # build + commit, no push
#   pipeline/refresh.sh --dry        # build only, no git
set -euo pipefail

PUSH=1
GIT=1
for arg in "$@"; do
  case "$arg" in
    --no-push) PUSH=0 ;;
    --dry)     PUSH=0; GIT=0 ;;
  esac
done

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"
LOG="$REPO_ROOT/output/refresh.log"
mkdir -p "$REPO_ROOT/output" "$REPO_ROOT/docs/data"
echo "=== $(date -u +%FT%TZ) refresh start ===" | tee -a "$LOG"

# Step 1 — refresh raw data cache.
# The mcp-db-gateway puller is documented in pipeline/pull.py (runbook). It writes
# cache/raw/batch_*.json + cache/spec_metadata.json from a Claude Code session.
if [ ! -f cache/spec_metadata.json ] || ! ls cache/raw/batch_*.json >/dev/null 2>&1; then
  echo "ERROR: cache/spec_metadata.json or cache/raw/batch_*.json missing — run pipeline/pull.py runbook" | tee -a "$LOG"
  exit 1
fi

# Step 2 — transform
python3 pipeline/build_v2.py 2>&1 | tee -a "$LOG"

# Step 2b — derive compact event table for the granularity selector
python3 pipeline/build_events.py 2>&1 | tee -a "$LOG"

# Step 3 — render
python3 pipeline/build_dashboard.py 2>&1 | tee -a "$LOG"

# Step 4 — promote outputs to docs/
cp output/dashboard.html        docs/index.html
cp output/loss_records.csv      docs/data/
cp output/store_benchmark.csv   docs/data/
cp output/store_month_matrix.csv docs/data/
cp output/spec_summary.csv      docs/data/
cp output/dashboard_payload.json docs/data/
cp output/events.json           docs/data/

# Step 5 — build_meta
python3 - <<'PY'
import json, subprocess, datetime, os
meta = {
  "build_time": datetime.datetime.utcnow().isoformat() + "Z",
  "git_commit": "",
  "rows": sum(1 for _ in open("docs/data/loss_records.csv")) - 1,
}
try:
    meta["git_commit"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
except Exception:
    pass
json.dump(meta, open("docs/data/build_meta.json", "w"), ensure_ascii=False, indent=2)
print(f"wrote docs/data/build_meta.json: {meta}")
PY

# Step 6 — commit + push
if [ "$GIT" -eq 1 ]; then
  git add docs/
  if git diff --cached --quiet; then
    echo "no changes to commit" | tee -a "$LOG"
  else
    git commit -m "auto: spoilage refresh $(date -u +%FT%TZ)"
    if [ "$PUSH" -eq 1 ]; then
      git push origin main
      echo "pushed to origin/main" | tee -a "$LOG"
    else
      echo "committed locally; skipped push" | tee -a "$LOG"
    fi
  fi
fi
echo "=== $(date -u +%FT%TZ) refresh end ===" | tee -a "$LOG"
