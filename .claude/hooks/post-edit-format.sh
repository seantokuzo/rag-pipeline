#!/usr/bin/env bash
# PostToolUse hook (matcher: Write|Edit|MultiEdit) — auto-format edited Python files.
# Wired in .claude/settings.json. Reads the tool call as JSON on stdin.
# (Fixes the proven repo's quirk: read file_path from stdin+jq, not an env var.)
set -euo pipefail

command -v jq >/dev/null 2>&1 || exit 0   # no jq -> no-op, never break an edit

INPUT=$(cat)
FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')
[ -z "$FILE_PATH" ] && exit 0
[ -f "$FILE_PATH" ] || exit 0

case "$FILE_PATH" in
  *.py)
    if command -v ruff >/dev/null 2>&1; then
      ruff format "$FILE_PATH" >/dev/null 2>&1 || true
      ruff check --fix "$FILE_PATH" >/dev/null 2>&1 || true
    elif command -v uv >/dev/null 2>&1; then
      uv run ruff format "$FILE_PATH" >/dev/null 2>&1 || true
      uv run ruff check --fix "$FILE_PATH" >/dev/null 2>&1 || true
    fi
    ;;
  *) exit 0 ;;   # skip non-Python (md/json/yaml/txt/...)
esac
exit 0
