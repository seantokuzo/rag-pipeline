# RAG Learning Lab (`rag-exp`)

> A small, from-scratch RAG pipeline built to *learn* every moving part: ingest → chunk → embed → vector store → retrieve → multi-tenant access control. Local-first, zero-cost, no Docker.

This repo reproduces — at small scale — what a production RAG system does, so the author (a senior fullstack/TS engineer, new to Python + RAG) can understand each stage instead of treating it as a black box. The corpus is three folders of public-domain Project Gutenberg text, each standing in for a separately licensed "product." A mock entitlements map (`user → [product_ids]`) drives the security boundary.

## The headline lesson

A user entitled to only one product runs a query — run it two ways:

- **No filter** → the top-k results leak chunks from products the user isn't licensed for. *This is the leak.*
- **Server-side, pre-retrieval filter** → the same query returns only entitled content. *This is the fix.*

The filter is built server-side from the trusted entitlements map, applied *inside* the vector search (pre-filter), and structurally impossible for the caller to weaken or remove. Seeing the leak, then seeing it stopped — and being able to explain *why* the filter is the boundary and why it can't live on the client — is the entire point. See `docs/SECURITY.md`.

## Quick start

Phase 1 isn't built yet — we're in Phase 0 (scaffolding). When Phase 1 starts:

```bash
uv sync   # resolve + install deps into .venv — the first run pulls torch, so it's a chunky download
```

The first pipeline run also downloads the CPU embedding model (`BAAI/bge-small-en-v1.5`) — a one-time fetch, cached thereafter.

## Repo layout

```
rag-exp/
├── CLAUDE.md       # project instructions for Claude Code (tech stack, conventions, anti-patterns)
├── docs/           # planning, the Phase 1 spec, and the security threat model (the doc homes)
├── .claude/        # Claude Code workspace: settings, hooks, rules, agents, skills
├── src/rag_exp/    # the pipeline of record — laid down stage-by-stage during Phase 1
├── products/       # the corpus: 3 folders = 3 mock licensed products (Gutenberg .txt)
└── tests/          # pytest — including the mandatory cross-tenant leak test (Phase 1)
```

## Key docs

- `CLAUDE.md` — tech stack, conventions, anti-patterns, review priorities
- `docs/PLANNING.md` — architecture + the two-phase roadmap (Local → Azure)
- `docs/STATE.md` — current phase, live session state, fresh-session handoff
- `docs/SECURITY.md` — ★ the access-control threat model and the pre-retrieval-filter rule (the heart of the project)
- `docs/spec-phase-1.md` — the active build spec for Phase 1
