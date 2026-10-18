#!/bin/bash
# Run the Claude Code agent headless with locked-down permissions: it can search, read, and write only
# inside proposals/. Uses your Claude subscription (claude auth login done once on the Mac).
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
[ -f config.env ] && set -a && . ./config.env && set +a

TODAY="$(TZ=America/Toronto date +%F)"
WEEKDAY="$(TZ=America/Toronto date +%A)"
mkdir -p proposals .run
[ -f "proposals/$TODAY.json" ] || printf '{"date":"%s","searches":[],"new_games":[],"updates":[],"flyer_prices":[],"events":[]}\n' "$TODAY" > "proposals/$TODAY.json"

PROMPT="$(sed -e "s/{{TODAY}}/$TODAY/g" -e "s/{{WEEKDAY}}/$WEEKDAY/g" agent/discovery_prompt.md)"
MODEL="${CLAUDE_MODEL:-sonnet}"
TURNS="${CLAUDE_MAX_TURNS:-60}"
if [ "$WEEKDAY" = "Sunday" ]; then TURNS="${CLAUDE_MAX_TURNS_SUNDAY:-120}"; fi

claude -p "$PROMPT" \
  --model "$MODEL" \
  --tools "WebSearch,WebFetch,Read,Write,Edit,Glob,Grep" \
  --allowedTools "WebSearch,WebFetch,Read,Glob,Grep,Edit(./proposals/**)" \
  --permission-mode dontAsk --permission-prompts none \
  --max-turns "$TURNS" --no-session-persistence \
  --output-format json > ".run/claude_$TODAY.json" || echo "agent exited $?"

python3 -c "import json,sys; json.load(open('proposals/$TODAY.json'))" 2>/dev/null || {
  echo "proposal is not valid JSON"; exit 1; }
