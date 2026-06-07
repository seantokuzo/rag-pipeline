---
paths:
  - "docs/**/*.md"
  - "CLAUDE.md"
---

# Planning-doc homes & status vocabulary

Keep planning content to these homes (don't spawn `NOTES.md` / `TODO.md` / `IDEAS.md`):
- `docs/PLANNING.md` — roadmap (phases, scope, status)
- `docs/STATE.md` — live context + fresh-session handoff
- `docs/SECURITY.md` — access-control threat model
- `docs/spec-*.md` — active build specs
- `docs/decisions/` — ADRs (locked, one per decision)
- `docs/history/` — per-phase / per-experiment retrospectives

Data files for a skill co-locate with the skill (e.g. `.agents/skills/<name>/`), not in `docs/`.

Status vocabulary — use these exact words: `queued` · `in-progress` · `blocked` · `done` · `deferred` · `cancelled`.
