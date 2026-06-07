#!/usr/bin/env bash
# PreToolUse hook (matcher: Read|Write|Edit|MultiEdit|Bash) — fail-secure guard.
# Exit 0 = allow, exit 2 = BLOCK (the stderr message is shown to Claude).
# Wired in .claude/settings.json. Reads the tool call as JSON on stdin.
set -euo pipefail

# Fail secure: if we can't parse the call (no jq), block rather than allow blind.
command -v jq >/dev/null 2>&1 || { echo "pre-tool-security: jq not found; blocking." >&2; exit 2; }

INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT"   | jq -r '.tool_name // empty')
TARGET=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // .tool_input.command // empty')

case "$TOOL" in
  Read|Write|Edit|MultiEdit)
    case "$TARGET" in
      *.env.example|*.env.sample|*.env.template)
        : ;;  # safe templates carry no secrets — allow
      *.env|*.env.*|.env|*credentials*|*secrets*|*.pem|*.key)
        echo "Blocked: '$TARGET' looks like a secret file. Open it yourself if this is intended." >&2
        exit 2 ;;
    esac
    ;;
  Bash)
    case "$TARGET" in
      *"rm -rf /"*|*"rm -rf ~"*|*"git push --force"*|*"git push -f"*|*"git reset --hard"*)
        echo "Blocked: destructive command pattern detected -> '$TARGET'." >&2
        exit 2 ;;
    esac
    ;;
esac
exit 0
