#!/bin/bash
# Nightly run (8 pm Toronto time via launchd). Order matters; see README "How a night runs".
set -uo pipefail
export PATH="/Library/Frameworks/Python.framework/Versions/Current/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
[ -f config.env ] && set -a && . ./config.env && set +a
TODAY="$(TZ=America/Toronto date +%F)"
mkdir -p logs .run
LOG="logs/$TODAY.log"
exec >>"$LOG" 2>&1
echo "=== run started $(date) ==="

LOCK=".run/lock"
if ! mkdir "$LOCK" 2>/dev/null; then echo "another run is in progress"; exit 0; fi
trap 'rmdir "$LOCK"' EXIT

fail() { echo "FAILED: $1"; python3 scripts/notify.py --problem "$1 (see logs/$TODAY.log)"; exit 1; }

git pull --rebase --autostash || fail "git pull failed"
cp data/games.json .run/games_before.json

python3 scripts/recheck.py            || echo "recheck: some checks failed (continuing)"
python3 scripts/enrich.py             || echo "enrich: errors (continuing)"
python3 scripts/prices.py             || echo "prices: errors (continuing)"
python3 scripts/discover.py           || echo "discover: errors (continuing)"
bash scripts/run_agent.sh             || fail "agent produced no valid proposal"
python3 scripts/coverage_check.py
if [ -s .run/coverage.txt ]; then python3 scripts/notify.py --problem "Weak agent run: $(cat .run/coverage.txt)"; fi
python3 scripts/apply_proposals.py    || fail "merging the proposal failed"
python3 scripts/recheck.py --new-only || echo "recheck new: some checks failed (continuing)"
NEW_IDS="$(python3 -c "import json;print(','.join(g['id'] for g in json.load(open('data/games.json')) if g.get('first_seen')=='$TODAY'))")"
if [ -n "$NEW_IDS" ]; then python3 scripts/prices.py --only "$NEW_IDS" --all-disc || true; fi
python3 scripts/build_stats.py        || fail "stats build failed"
python3 scripts/validate.py           || fail "validation failed - nothing was published"

python3 - <<'EOF'
import json, datetime, zoneinfo
p = "data/meta.json"; m = json.load(open(p))
m["last_run_at"] = datetime.datetime.now(zoneinfo.ZoneInfo("America/Toronto")).replace(microsecond=0).isoformat()
json.dump(m, open(p, "w"), indent=1)
EOF

git add data proposals
if ! git diff --cached --quiet; then
  git commit -m "Nightly update $TODAY" -q || fail "git commit failed"
  git push -q || { git pull --rebase -q && git push -q; } || fail "git push failed"
fi
python3 scripts/notify.py --before .run/games_before.json
git add data/sales.json && git diff --cached --quiet || { git commit -qm "Mark alerts sent $TODAY" && git push -q; }
echo "=== run finished $(date) ==="
