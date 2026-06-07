# Path-scoped rules

Each `*.md` here has YAML frontmatter with a `paths:` glob array. Claude **natively** auto-injects the rule body into context when it *reads* a file matching any glob (see Claude Code docs → "How Claude remembers your project" / memory). Rules without a `paths:` field load unconditionally.

Keep rules **short** — every line costs context tokens — and don't duplicate `CLAUDE.md`.

```yaml
---
paths:
  - "src/rag_exp/**/*.py"
---
```

Current rules:
- `planning-doc-homes.md` — where planning docs live + the status vocabulary (fires on `docs/`)
- `access-control.md` — the entitlement-filter invariant (fires on `security.py` / `retrieve.py`)
- `rag-conventions.md` — embedding parity, cosine, metadata, chunking (fires on pipeline code)
