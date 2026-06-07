# RAG Learning Lab — Project Instructions

> A small-scale, from-scratch RAG pipeline built to *learn* ingestion → embedding → vector storage → retrieval → multi-tenant access control. The centerpiece lesson: a licensing-based content leak, stopped by a server-side pre-retrieval filter.

---

## Project Overview

This repo reproduces — at small scale — what a production RAG system does, so the author (a senior fullstack/TS engineer, new to Python + RAG) can understand every moving part. The corpus is three folders of public-domain Project Gutenberg text, each acting as a licensed "product." A mock entitlements map (`user → [product_ids]`) drives a **server-side, pre-retrieval metadata filter** that is the security boundary.

**This is a learning collaboration, not a delivery.** Move incrementally, explain Python and RAG choices as you go, present options at decision points, and keep the human in the loop. Don't autonomously slam out whole phases.

**Key docs (read these to orient):**
- `docs/PLANNING.md` — architecture + the two-phase roadmap (Local → Azure)
- `docs/STATE.md` — current phase, session state, and the **Fresh-session handoff** block (read this first when resuming)
- `docs/SECURITY.md` — ★ the access-control threat model and the pre-retrieval-filter rule (the heart of this project)
- `docs/spec-phase-1.md` — the active build spec for Phase 1
- `docs/SESSION-GUIDE.md` — human-operator playbook (how to drive these sessions)
- `docs/decisions/` — ADRs (why each RAG trade-off was chosen)
- `docs/history/` — per-phase / per-experiment learning retrospectives

**Current phase:** Phase 0 — Session 1 scaffolding. No pipeline code yet. On a fresh session, read `docs/STATE.md` → "Fresh-session handoff."

---

## Tech Stack

| Category | Choice | Notes |
|----------|--------|-------|
| Language | Python 3.12+ | new to the author; explain idioms as we go |
| Project/dep manager | **uv** (0.11.x) | ≈ npm + npx + pyenv + lockfile in one Rust binary |
| Lint + format | **ruff** (0.15.x) | one tool replacing black + flake8 + isort (≈ Prettier+ESLint) |
| Types | pyright (IDE) / mypy (CI), optional | not enforced day 1 |
| Tests | **pytest** (9.x) | the cross-tenant leak assertions live here |
| Vector store (Phase 1) | **chromadb** (1.5.x) | in-process `PersistentClient`, no Docker |
| Embeddings (Phase 1) | **sentence-transformers** (5.5.x) | local, CPU; default model `BAAI/bge-small-en-v1.5` |
| Chunking | **langchain-text-splitters** + **tiktoken** | recursive splitter w/ token-accurate sizing |
| Vector store (Phase 2) | Azure AI Search (`azure-search-documents` 12.x) | vector + hybrid (RRF) + filtered vector search + semantic ranker |
| Embeddings (Phase 2) | Azure OpenAI `text-embedding-3-small` | `dimensions` param for Matryoshka truncation |

Never guess versions — `uv add <pkg>` resolves them. Pins live in `pyproject.toml` / `uv.lock`.

---

## Architecture

The pipeline (detail in `docs/PLANNING.md`):

```
products/<product>/*.txt
  → ingest      load text, stamp metadata {product_id, source} on EVERY chunk
  → chunk       recursive, 512 tokens, no overlap (to start)
  → embed       bge-small, encode_document()  ──┐ same model + normalization +
  → index       Chroma collection (cosine)      │ prompt convention BOTH sides
                                                 │
[query time]                                     │
  user_id → entitlements map → SERVER-SIDE filter {product_id $in allowed}
  query text → embed, encode_query() ────────────┘
  → vector search WITH the filter applied INSIDE the query (pre-filter)
  → [optional rerank]
  → top-k chunks (only entitled products can ever be returned)
```

**Module rules:**
- The **only** abstraction we build is the vector-store seam (`store/base.py` → `chroma.py`, later `azure.py`). Phase 1→2 swaps the store + embed adapters; pipeline logic and the security invariant stay put.
- The entitlement filter is built **server-side** in `security.py` from the trusted map — never accepted from the caller. See `docs/SECURITY.md`.
- Each pipeline stage owns its module; no god files.
- Exploration in notebooks is fine; the pipeline of record lives in `src/rag_exp/`.

---

## Code Conventions

### Python
- **Type hints** on public functions; prefer explicit over clever.
- **No mutable default args** (`def f(x=[])` is a bug); use `None` + assign inside.
- **No bare `except:`** — catch specific exceptions; surface clear messages.
- **f-strings** for formatting; `pathlib.Path` over string paths.
- **Dataclasses / Pydantic** for structured records (a chunk = `{text, product_id, source, chunk_id}`).
- Match existing patterns — read a module before extending it.

### Git
**Branch:** `phase-N/description` or `fix/description`
**Commit format:** `type(scope): description`
- **Types:** `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
- **Scopes:** `ingest`, `chunk`, `embed`, `index`, `retrieve`, `rerank`, `eval`, `security`, `corpus`, `cli`, `infra`, `docs`

### Versioning cadence (pre-1.0)
| Version | Earned by |
|---|---|
| `0.0.x` | Active development, expect breakage. **We are here.** |
| `0.1.0` | Phase 1 works end-to-end: leak demo reproducible + cross-tenant test green + eval harness runs |
| `0.x.y` | Subsequent waves (Azure / hybrid / rerank / transcript product) |
| `1.0.0` | N/A for a learning lab — may never apply |

---

## Quality Gates

Before every commit (once code exists):

```bash
uv run ruff format . && uv run ruff check . && uv run pytest
```

`pytest` MUST include the cross-tenant leak test once `security.py` + `retrieve.py` exist — a green suite that doesn't prove "no leak" is a false sense of safety.

---

## Anti-Patterns

- **Client-supplied auth filters** — the entitlement filter is ALWAYS built server-side from the trusted map, never from request params. This is the cardinal sin to prevent.
- **Post-filtering for entitlements** — filter *inside* the query (pre-filter), never retrieve-then-drop. Post-filter leaks data to the app layer and silently loses authorized hits.
- **Query/index embedding mismatch** — different model, normalization, or prompt convention on the two sides silently tanks recall.
- **L2 distance with normalized embeddings** — set `hnsw:space: cosine` on the Chroma collection (L2 is the default).
- **Premature abstraction** — two concrete store adapters beat a speculative "any vector DB" layer; three similar lines beat a bad abstraction.
- **God modules** — keep each pipeline stage in its own file.
- **Silent corpus/config failures** — log what loaded and what didn't.
- **Guessed dependency versions** — let `uv` resolve; don't hand-edit pins from memory.

---

## Reviewing (local-first)

This project uses **lightweight, local review** — no GitHub Actions tiers (deliberate departure from the global PR-review loop, which assumes a GitHub remote). Review happens two ways:
1. **`/code-review` skill** for general correctness/cleanup on the working diff.
2. **`access-control-reviewer` subagent** (`.claude/agents/access-control-reviewer.md`) — spawn it (`@agent-access-control-reviewer`) whenever `security.py`, `retrieve.py`, or any entitlement/filter logic changes. It is the security gate.

If we later push to GitHub, we can add a single `@claude` review Action; the priorities below port directly.

### Standing review priorities (in order)
1. **ACCESS CONTROL / SECURITY** — entitlement filter is server-side, pre-retrieval, applied inside the query, sourced from the trusted map, structurally un-overridable by the caller; `product_id` metadata stamped on every chunk at ingestion; a cross-tenant leak test exists and passes; no secret/API-key leakage; retrieved text treated as untrusted (prompt-injection awareness).
2. **RETRIEVAL CORRECTNESS** — query/index embedding parity (model + normalization + prompt convention); cosine space set; pre-filter not post-filter; sane top-k.
3. **PYTHON CORRECTNESS** — type hints, no mutable defaults, no bare except, clear errors, no dead code.
4. **CONVENTIONS** — see Anti-Patterns; module organization; commit format.

### Path-aware focus
| Path | Primary focus |
|------|---------------|
| `src/rag_exp/security.py`, `src/rag_exp/retrieve.py` | the access-control invariant (the filter boundary) |
| `src/rag_exp/embed.py`, `retrieve.py` | embedding parity (model/normalization/prompt) |
| `src/rag_exp/store/**`, `index*` | metadata stamping + cosine space |
| `src/rag_exp/eval.py` | metric correctness (recall@k / MRR / nDCG) |
| `docs/SECURITY.md` | cross-check changes against the threat model |

### What NOT to flag
- **Defensive code for impossible cases** — validate at boundaries (user input, external APIs, retrieved content); trust internal invariants.
- **Tests for code that doesn't exist yet** — this is a phased lab; ask for tests on *shipped* stages, not future ones. (Exception: the cross-tenant leak test is mandatory the moment retrieval+entitlements land.)
- **Architecture re-litigation** — the pipeline shape and the pooled access-control model are locked in `PLANNING.md` / `SECURITY.md` / ADRs. Don't propose alternatives without strong evidence.
- **Premature abstraction / DRY-for-its-own-sake** — see Anti-Patterns.
- **Scope creep** — review the change's stated scope, not future phases.
- **Style nits** — ruff handles formatting; ignore.
- **Comment density** — clear names beat comments; only flag missing *why*.
- **Micro-optimization** — at learning-lab corpus scale, correctness and clarity win.

---

## Docs discipline

- **Doc homes** (keep planning content to these; see `.claude/rules/planning-doc-homes.md`): `docs/PLANNING.md` (roadmap), `docs/STATE.md` (live context + handoff), `docs/SECURITY.md` (threat model), `docs/spec-*.md` (active specs), `docs/decisions/` (ADRs, locked), `docs/history/` (retrospectives), `docs/explainers/` (concept "how it works" docs). Don't spawn `NOTES.md`/`TODO.md`/`IDEAS.md`.
- **Explainer series** (`docs/explainers/`, step-agnostic, tracked/not-ignored): plain-English "how does this work" docs, one per concept (e.g. `chunking.md`). **Process:** before each handoff the human asks how the next step works; Claude explains *in-session* **and** writes/updates the matching explainer at the same time. Understanding-oriented — distinct from specs (how-to-build) and ADRs (why-decided). See `docs/explainers/README.md`.
- **Data files co-locate with their skill**, not in `docs/` (e.g. a skill's reference data lives under `.agents/skills/<name>/`).
- **Status enum** (use these exact words): `queued` · `in-progress` · `blocked` · `done` · `deferred` · `cancelled`.
- **End every session by updating `docs/STATE.md`** so the next session resumes cleanly.
