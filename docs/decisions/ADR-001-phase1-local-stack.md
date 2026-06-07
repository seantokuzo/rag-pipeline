# ADR-001: Phase 1 local stack — Chroma + bge-small + uv

**Status:** Accepted
**Date:** 2026-06-06
**Supersedes:** none
**Superseded by:** none

## Context

Phase 1 exists to *learn* RAG end-to-end — ingest → chunk → embed → store → retrieve → entitlement filter — with full understanding of every moving part. The author is a senior TS/fullstack engineer, new to Python and RAG. That fixes the constraints:

- **Zero cost** — no API bills, no cloud account gating progress.
- **Fully local & in-process** — no Docker, no server to babysit; runnable on a laptop and over mobile SSH.
- **Understandable** — every component small enough to read and reason about; nothing magic.
- **Teaches the load-bearing lessons** — query/index embedding parity, cosine-vs-L2, metadata filtering.

We need one concrete stack that satisfies all four before the Phase 2 Azure swap.

## Decision

We will build Phase 1 on a **local, zero-cost stack**, because it is the only combination that is free, in-process, and still teaches the real RAG footguns:

- **Vector store:** Chroma `PersistentClient` — in-process, on-disk, **no Docker**. Collection forced to cosine (`metadata={"hnsw:space": "cosine"}`).
- **Embeddings:** sentence-transformers **`BAAI/bge-small-en-v1.5`**, `device="cpu"`, `normalize_embeddings=True`, cosine. Use `encode_query` / `encode_document` so bge's asymmetric query prefix lands on the right side.
- **Chunking:** `langchain-text-splitters` `RecursiveCharacterTextSplitter.from_tiktoken_encoder` — recursive, 512 tokens, no overlap, token-accurate via **tiktoken**.
- **Tooling:** **uv** (deps + venv + lockfile), **ruff** (lint + format), **pytest** (the cross-tenant leak test lives here).

## Alternatives considered

**Vector store**
- **FAISS** — fast and local, but weaker metadata-filter ergonomics. Metadata filtering *is* the whole point of this lab (it's the entitlement boundary), so a store where filtering is second-class is the wrong teaching tool. Rejected.
- **pgvector / Qdrant** — both excellent, both want a server / Docker. That violates the zero-friction, in-process constraint. Rejected for Phase 1; a Qdrant-class server is moot anyway since Phase 2 goes to Azure AI Search.

**Embeddings**
- **OpenAI API (`text-embedding-3-*`)** — great quality, but costs money and needs a key. Defeats the zero-cost learning goal. Rejected for Phase 1 (Azure OpenAI is the Phase-2 path).
- **`all-MiniLM-L6-v2`** — a perfectly fine, slightly faster local model. But it's symmetric — no query/document prefix — so it *hides* the parity lesson. bge-small's asymmetric query prefix forces us to handle query-vs-document encoding correctly, which is exactly what we want to internalize. Rejected.

**Tooling**
- **Poetry** — solid, but a separate, slower resolver/runner. uv is the 2026 default. Rejected.
- **pip + venv (+ requirements.txt)** — lowest common denominator, no real lockfile ergonomics. Rejected.
- uv wins on speed, single-binary simplicity, and it's the closest mental model to the author's Node toolchain (≈ npm + npx + pyenv + lockfile in one).

## Consequences

### Positive
- Zero cost, zero servers — clone and run, even over mobile SSH.
- Small enough to read end-to-end; nothing hidden behind a managed service.
- Teaches the load-bearing lessons: **query/index embedding parity**, **cosine vs L2** (Chroma defaults to L2 — we override), and metadata pre-filtering.

### Negative
- CPU embedding is slower than GPU/API — fine at learning-lab corpus size, noticeable on a big chunk-size sweep.
- Local small models trail frontier embeddings; absolute retrieval quality is lower than e.g. OpenAI's.

### Neutral
- Phase 2 swaps the **store** (→ Azure AI Search) and **embeddings** (→ Azure OpenAI `text-embedding-3-small`) behind the `store/base.py` adapter seam. Ingest, chunk, the security invariant, and eval stay put — that's the design (PLANNING → "two backends").

## Links
- `docs/PLANNING.md` — roadmap + the two-backend table.
- `docs/spec-phase-1.md` — build spec (locked decisions #1–#4, #7; Appendix config defaults).
- `docs/SECURITY.md` — the invariant this stack must satisfy.
- ADR-002 — the access-control model layered on this stack.
