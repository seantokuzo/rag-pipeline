# RAG Learning Lab — Architecture & Roadmap

> The north star: what this system is, how it's built, and the ordered plan to build it. Pairs with `docs/SECURITY.md` (the access-control model) and `docs/spec-phase-1.md` (the active build spec).

---

## Versioning Cadence (pre-1.0)

| Version | Meaning | Earned by |
|---|---|---|
| `0.0.x` | Active development, expect breakage. **We are here.** | Patch-bump anything during scaffolding + Phase 1 build. |
| `0.1.0` | First version trusted as a working teaching artifact. | Phase 1 end-to-end: leak demo reproducible + cross-tenant test green + eval harness runs. |
| `0.x.y` | Feature waves. | Azure backend, hybrid search, reranking, the transcript "video" product. |
| `1.0.0` | N/A for a learning lab. | — |

---

## Vision & Learning Goals

Reproduce, at small scale and with full understanding, the production RAG pattern:
**ingest → chunk → embed → vector store → retrieve → multi-tenant access control.**

The single most important learning outcome: **see a licensing-based content leak happen, then see it stopped by a server-side pre-retrieval filter** — and be able to explain *why* the filter is the security boundary and why it cannot live on the client.

Secondary learnings: how chunking choices move retrieval quality; why query/index embedding parity matters; dense vs hybrid retrieval; when reranking helps; how to measure retrieval (recall@k / MRR / nDCG); how the same logic maps onto cloud infra (Azure AI Search + Azure OpenAI).

---

## Current State

- Empty repo being scaffolded in Session 1 (Phase 0).
- No pipeline code yet. Workflow scaffolding (CLAUDE.md, docs, `.claude/`, `.agents/`, Python skeleton, corpus folders) is being laid down.
- See `docs/STATE.md` for live session state.

---

## Target Architecture

### Pipeline

```
products/<product>/*.txt   (3 mock "licensed products")
  → ingest      load text → Documents, stamp metadata {product_id, source}
  → chunk       recursive splitter, 512 tokens, no overlap (Stage 1)
  → embed       bge-small, encode_document()
  → index       upsert to Chroma collection (cosine space), metadata travels with each vector

[query time]
  user_id ──► entitlements map ──► server-side filter: {"product_id": {"$in": allowed}}
  query  ──► embed, encode_query()  (SAME model/normalization/prompt as index side)
        ──► vector search with the filter applied INSIDE the query (pre-filter)
        ──► [optional rerank]
        ──► top-k chunks  (un-entitled products are structurally unreachable)
```

### Target module tree

> Created incrementally during Phase 1 per `docs/spec-phase-1.md`. Session 1 lays down only the package root.

```
src/rag_exp/
├── __init__.py
├── config.py        # paths, model name, k, collection name
├── ingest.py        # load product folders → records w/ {product_id, source}
├── chunk.py         # chunkers (recursive first; pluggable for the chunking-lab)
├── embed.py         # embedding wrapper; enforces query/doc parity
├── store/
│   ├── base.py      # VectorStore protocol (the one real abstraction seam)
│   ├── chroma.py    # Phase 1 adapter
│   └── azure.py     # Phase 2 adapter
├── security.py      # ★ entitlements map + server-side filter builder (the boundary)
├── retrieve.py      # query pipeline: build filter → embed → search → top-k
├── eval.py          # golden-query metrics: recall@k, hit-rate, MRR, nDCG
└── demo.py          # the leak experiment (no-filter vs server-side filter)
```

### The two backends (what swaps between phases)

| Concern | Phase 1 (local) | Phase 2 (Azure) |
|---|---|---|
| Vector store | Chroma `PersistentClient` | Azure AI Search index |
| Filtering | Chroma `where` pre-filter | `filter` + `vectorFilterMode: preFilter` |
| Embeddings | sentence-transformers `bge-small` | Azure OpenAI `text-embedding-3-small` (`dimensions` param) |
| Hybrid | optional local BM25 + RRF experiment | native keyword+vector RRF |
| Rerank | optional local `bge-reranker` | semantic ranker (free monthly allowance) |

Everything else — ingest, chunk, the security invariant, eval — is identical across phases.

---

## Roadmap

### Phase 0 — Scaffolding (Session 1) · status: in-progress
**Goal:** a clean, RAG-adapted Claude Code workspace + planning/spec docs so later sessions build cleanly.
**Deliverables:** CLAUDE.md; this doc; STATE.md; SECURITY.md; SESSION-GUIDE.md; spec-phase-1.md; ADR + history systems; `.claude/` (settings, hooks, rules, agents, skills); Python skeleton; `products/` corpus folders.
**Acceptance:** docs coherent and cross-linked; tooling wired; next session can start Phase 1 from STATE.md alone.

### Phase 1 — Local, zero-cost pipeline · status: queued
**Goal:** end-to-end ingest→embed→Chroma→retrieve with server-side entitlement filtering, and a reproducible, explainable leak demo.
**Build order (each step ≈ one atomic commit):**
1. `corpus` — download 3 products' Gutenberg texts into `products/` (distinct vocabularies).
2. `config` + `ingest` — load folders → records, stamp `{product_id, source}`.
3. `chunk` — recursive splitter @ 512 tokens, no overlap (token-accurate via tiktoken).
4. `embed` — `bge-small` wrapper; enforce query/doc parity + normalization.
5. `store/chroma` — collection with `hnsw:space: cosine`; metadata stamped on every chunk.
6. index script — wire ingest→chunk→embed→upsert.
7. `security` — entitlements map `{user → [product_ids]}` + server-side filter builder.
8. `retrieve` — query pipeline with the filter applied **inside** the search.
9. ★ **leak experiment** (`demo.py`) — run a query (a) with NO filter (watch un-licensed products leak in) and (b) WITH the server-side filter (clean). The payoff lesson.
10. `eval` harness — golden queries → recall@k / hit-rate / MRR / nDCG; **cross-tenant leak test** in `pytest` asserting zero unauthorized `product_id` ever returned.
11. poke experiments — vary chunk size; exact-term vs paraphrased queries (motivates hybrid); print similarity scores.
**Acceptance:** leak demo reproducible and explained; cross-tenant test green; eval harness runs over a golden set; chunk-size + query-type experiments documented in `docs/history/`.

### Phase 2 — Graduate to Azure · status: queued
**Goal:** mirror the company's infra — swap the vector DB and embeddings to Azure, keep the pipeline logic and the invariant.
**Deliverables:**
- `store/azure.py` — Azure AI Search adapter (vector search + filtered vector search via `preFilter`).
- `embed.py` Azure path — Azure OpenAI `text-embedding-3-small` with the `dimensions` param (Matryoshka experiment).
- The same entitlement filter expressed as an Azure `filter` (the invariant, ported).
- Experiments: hybrid (keyword+vector RRF), semantic ranker reranking, dimensions/Matryoshka truncation.
- Re-run the leak demo + cross-tenant test against Azure.
**Acceptance:** leak demo + cross-tenant test pass on Azure; hybrid/rerank/dimensions explored and written up.
**Fallback:** if Azure OpenAI access is gated, keep local embeddings (or use OpenAI's API) and use Azure only for the vector DB.

---

## Design Principles

1. **Security is the lesson.** The entitlement filter is the centerpiece; the pipeline exists to demonstrate and explain it.
2. **Start simple, measure, then add complexity.** Recursive-512 + dense retrieval first. Let the eval harness justify hybrid, reranking, or fancier chunking — don't add them on faith.
3. **Swap components, keep logic.** The only abstraction we build is the vector-store seam. Phase 1→2 changes adapters, not the pipeline or the invariant.
4. **Parity is sacred.** Query and index embeddings must match in model, normalization, and prompt convention.
5. **Everything normalizes to text.** Products are folders of text; later a transcript drops in as a "video" product to prove the pipeline doesn't care about source modality.
6. **Explain as we go.** Decisions → `docs/decisions/` (ADRs). Learnings/surprises → `docs/history/`.

---

## Tech Stack

See `CLAUDE.md` → Tech Stack for the table and version notes.

## Anti-Patterns

See `CLAUDE.md` → Anti-Patterns. The cardinal one: **the entitlement filter is never client-supplied.**

---

## Open Questions

1. **Reranking in Phase 1?** *Recommendation:* defer; add local `bge-reranker` only if eval shows precision@k is the bottleneck (Azure's semantic ranker covers Phase 2).
2. **Hybrid search in Phase 1?** *Recommendation:* a minimal local BM25 + RRF experiment to *feel* exact-term vs paraphrase, but treat Azure as where hybrid is "real."
3. **LLM synthesis (generation)?** Out of scope for now — retrieval returns chunks. A generation step is a possible later wave.
4. **Golden eval set size?** Hand-author a small set per product (start ~5–10 queries/product with known relevant chunks); grow as needed.
