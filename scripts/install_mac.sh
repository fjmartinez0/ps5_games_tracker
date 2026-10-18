#!/bin/bash
# Install (or reinstall) the nightly 8 pm job.   bash scripts/install_mac.sh [--run-now]
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.ps5gamestracker.daily"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$REPO/logs" "$HOME/Library/LaunchAgents"
sed "s#__REPO__#$REPO#g" "$REPO/launchd/$LABEL.plist" > "$DEST"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "Installed $LABEL: runs every day at 8:00 pm (Mac local time)."
[ -f "$REPO/config.env" ] || echo "Reminder: cp config.example.env config.env and fill it in."
if [ "${1:-}" = "--run-now" ]; then
  launchctl kickstart -k "gui/$(id -u)/$LABEL"
  echo "Started a run now. Follow it with: tail -f $REPO/logs/$(date +%F).log"
fi
