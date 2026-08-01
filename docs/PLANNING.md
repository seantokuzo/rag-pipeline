# RAG Learning Lab — Architecture & Roadmap

> The north star: what this system is, how it's built, and the ordered plan to build it. Pairs with `docs/SECURITY.md` (the access-control model) and `docs/spec-phase-1.md` (the active build spec).

---

## Versioning Cadence (pre-1.0)

| Version | Meaning | Earned by |
|---|---|---|
| `0.0.x` | Active development, expect breakage. **We are here.** | Patch-bump anything during scaffolding + Phase 1 build. |
| `0.1.0` | First version trusted as a working teaching artifact. | Phase 1 end-to-end: leak demo reproducible + cross-tenant test green + eval harness runs. |
| `0.x.y` | Feature waves. | Multi-format ingestion (Phase 1.5), Azure backend, hybrid search, reranking, the transcript "video" product. |
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

### Phase 0 — Scaffolding (Session 1) · status: done
**Goal:** a clean, RAG-adapted Claude Code workspace + planning/spec docs so later sessions build cleanly.
**Deliverables:** CLAUDE.md; this doc; STATE.md; SECURITY.md; SESSION-GUIDE.md; spec-phase-1.md; ADR + history systems; `.claude/` (settings, hooks, rules, agents, skills); Python skeleton; `products/` corpus folders.
**Acceptance:** docs coherent and cross-linked; tooling wired; next session can start Phase 1 from STATE.md alone.

### Phase 1 — Local, zero-cost pipeline · status: done
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
**Acceptance:** leak demo reproducible and explained; cross-tenant test green; eval harness runs over a golden set; chunk-size + query-type experiments documented in `docs/history/`. — **ALL MET.**
**Result (step 11, `docs/history/EXP-chunk-size-sweep.md`):** the sweep **disproved** the "smaller chunks win" hypothesis — at k=5 overall hit-rate is **512 (0.333) > 256 (0.286) > 1024 (0.238)**, so **512 stays the default, now earned with data**. Exact and paraphrase queries want **opposite** sizes (exact best @512 = 0.625; paraphrase best @1024 = 0.538 @k10), and 1024 breaks against bge-small's **512-token max sequence** (433/444 chunks tail-truncated → exact recall collapses to 0.125). Dense cosine scores are **not thresholdable** (a wrong top-1 outscores relevant hits) → motivates hybrid/BM25 + a cross-encoder reranker in Phase 2.

### Phase 1.5 — Multi-format ingestion · status: queued ◀ **NEXT UP**
**Goal:** prove Design Principle #5 — the pipeline doesn't care about source modality — by ingesting formats beyond `.txt` through a new **loader seam**, while `chunk → embed → store → retrieve` and the security invariant stay byte-for-byte the same. Every source becomes `text + metadata`; a chunk from a scanned PDF or a transcribed clip is `product_id`-stamped and entitlement-filtered identically to a Gutenberg chunk. Scope decided as **Option A** (see ADR-005).

**Why here (after eval, before Azure):**
- *After eval (step 10):* the harness lets us **measure** whether an extraction/serialization choice (table→sentence, OCR quality) actually helps retrieval — Principle #2, not faith.
- *Before Azure:* each scrappy local loader has a managed Azure twin, so we learn the *concept* by hand-rolling it, then Phase 2 swaps in the real service. This phase is the on-ramp to Azure, not a detour.

**The loader seam (the one new abstraction — ADR-005):** an `ingest/` package with a `Loader` Protocol (`load(path) -> SourceDoc`) + one concrete loader per format behind it, mirroring `store/`. Dispatch by file extension. The metadata schema grows from `{product_id, source}` to also carry `{page | sheet/row | timestamp}` provenance (the timestamp is the hook the transcript "video product" needs).

**Build order (each ≈ one atomic commit), Option A scope:**
1. **Refactor `ingest.py` → `ingest/` package** — extract the current `.txt` path behind the `Loader` Protocol (`text.py`), **no behavior change**; the leak test + eval stay green. (Proves the seam before adding formats.)
2. **Tabular** (`tabular.py`) — CSV / `.xlsx` via `csv`/`openpyxl`; decide + document the row→text serialization (row-as-sentence with header context). Metadata: `sheet`, `row`.
3. **PDF, text layer** (`pdf.py`) — `pypdf`/`pymupdf`; page-level metadata; layout gotchas (columns, headers/footers, tables) written up in `docs/history/`.
4. **PDF, scanned** — Tesseract OCR fork (detect a missing text layer → OCR); OCR quality measured against the eval harness.
5. **Audio spike** — `faster-whisper` (`tiny`/`base`) on a ~60s clip → transcript + segment timestamps; small, to *feel* ASR + timestamped chunks, not a production path.
6. **Video spike** — `ffmpeg` extract the audio track → reuse the audio loader; note the visual tier (keyframes / slide-OCR) as advanced/deferred.

**Acceptance:** a mixed-format product ingests end-to-end; the **cross-tenant leak test passes over non-text sources** (the invariant is modality-blind); a short write-up per format in `docs/history/`; extraction/serialization choices scored on the eval harness where it applies. Full-scale audio/video ingestion is explicitly **deferred to Phase 2** (Azure Speech / Video Indexer), where it's production-real.

**Intel-Mac caveat (ADR-003 redux):** `pymupdf`, `ctranslate2`/`faster-whisper`, and Tesseract bindings all need an x86_64-macOS wheel-availability probe *before* we pin versions — the same wheel-wall that produced ADR-003. Probe first (rag-researcher / a throwaway `uv` env), then pin per the caps.

**Azure twins (the Phase-2 bridge):** pypdf + Tesseract → **Azure Document Intelligence** · faster-whisper → **Azure AI Speech** · ffmpeg + whisper → **Azure Video Indexer**.

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
3. **Swap components, keep logic.** We build **two** deliberate abstraction seams, each justified by 3+ real implementations (never speculation): the **vector-store seam** (Phase 1→2 swaps Chroma↔Azure) and the **ingest loader seam** (Phase 1.5 — text/tabular/PDF/audio loaders behind one contract; ADR-005). Everything between them — chunk, embed, retrieve, and the security invariant — stays put.
4. **Parity is sacred.** Query and index embeddings must match in model, normalization, and prompt convention.
5. **Everything normalizes to text.** Products are folders of text; later a transcript drops in as a "video" product to prove the pipeline doesn't care about source modality. **Phase 1.5 makes this concrete** — Excel/PDF/audio/video all normalize to `text + metadata` through the loader seam, and the cross-tenant leak test must pass unchanged over them.
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
5. **Ingest loader seam — exact shape (Phase 1.5)?** A `Loader` Protocol (`load(path) -> SourceDoc`) dispatched by extension, mirroring `store/`; metadata grows to carry `page`/`sheet`/`timestamp`. *Open until build time:* single-vs-iterable return, typed provenance fields vs a flexible `dict`, the row→sentence table serialization, and per-format library pins (gated on an x86_64-macOS wheel probe — `pymupdf`/`faster-whisper`/Tesseract, the ADR-003 wheel-wall). See ADR-005 (Proposed).
