#!/usr/bin/env bash
# Stop hook — notify when Claude finishes a turn. Wired in .claude/settings.json.
# NOTE: the real "Claude finished" event is `Stop` (the proven repo mislabeled it "PostResponse").
set -euo pipefail

MSG="Claude finished working (RAG Lab)"

# Prefer a phone push via ntfy.sh when NTFY_TOPIC is set — useful when SSH'd from mobile,
# since a desktop notification on the Mac won't reach you. Set: export NTFY_TOPIC=your-topic
if [ -n "${NTFY_TOPIC:-}" ]; then
  curl -s -d "$MSG" "https://ntfy.sh/${NTFY_TOPIC}" >/dev/null 2>&1 || true
elif [[ "${OSTYPE:-}" == "darwin"* ]]; then
  osascript -e "display notification \"$MSG\" with title \"RAG Lab\" sound name \"Glass\"" >/dev/null 2>&1 || true
fi

# Option: Pushover (iPhone/Watch) — uncomment + set PUSHOVER_TOKEN / PUSHOVER_USER
# curl -s --form-string "token=${PUSHOVER_TOKEN:-}" --form-string "user=${PUSHOVER_USER:-}" \
#   --form-string "message=$MSG" https://api.pushover.net/1/messages.json >/dev/null 2>&1 || true

exit 0
