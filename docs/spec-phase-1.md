# Phase 1 — Local Pipeline Spec

> Implementation north star for the local, zero-cost RAG pipeline and the licensing-leak demonstration.

**Status:** Spec — not yet implemented. Every section is binding unless marked `[uncertain]`.
**Source research:** completed 2026-06-06 against current tool versions (chromadb 1.5.9, sentence-transformers 5.5.1, langchain-text-splitters 1.1.2, tiktoken 0.13.0, pytest 9.0.3).
**Companions:** `docs/PLANNING.md` (roadmap), `docs/SECURITY.md` (the invariant this spec must satisfy).

---

## 0. Executive summary

Build an end-to-end local pipeline: load three Gutenberg "products" → chunk → embed locally → store in Chroma with per-chunk `product_id` → retrieve with a **server-side entitlement pre-filter** → demonstrate the leak (no filter) vs. the fix (filter). Then add a golden-query eval harness + a cross-tenant leak test, and run a few "poke" experiments.

### Locked decisions
| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Vector store: **Chroma `PersistentClient`** (on-disk, no Docker) | zero-cost, in-process, survives restarts |
| 2 | Embeddings: **`BAAI/bge-small-en-v1.5`** via sentence-transformers, CPU, `normalize_embeddings=True` | strong/fast on CPU; its asymmetric query prefix forces learning the parity rule |
| 3 | Distance: **cosine** (`metadata={"hnsw:space":"cosine"}`) | normalized embeddings; Chroma defaults to L2 — must override |
| 4 | Chunking: **recursive, 512 tokens, NO overlap**, token-accurate (tiktoken) | 2026 strong default; overlap is no longer a free win |
| 5 | Entitlements: **pooled** model — one collection, `product_id` metadata filter | the filter *is* the lesson (see SECURITY.md §4) |
| 6 | Filter: **server-side, in-query, AND-composed, fail-closed** | the invariant (SECURITY.md §3, §5) |
| 7 | Retrieval: **dense only** to start | measure before adding hybrid/rerank |
| 8 | No LLM synthesis | retrieval returns chunks |

### Non-goals (explicitly out)
Hybrid/BM25 as core (only a poke experiment), reranking, Azure, generation, auth, a web API. See PLANNING §Open Questions.

### Build order (each step ≈ one atomic commit)
1. corpus prep · 2. `config` + `ingest` · 3. `chunk` · 4. `embed` · 5. `store/chroma` · 6. index script · 7. `security` · 8. `retrieve` · 9. **leak demo** · 10. `eval` + cross-tenant test · 11. poke experiments.

---

## Part A — Corpus & ingest

### A.0 Scope
**In:** three product folders of `.txt`; a loader that yields per-chunk-able records with metadata. **Out:** chunking, embedding.

### A.1 The products
| Folder | `product_id` | Content (distinct vocabulary) |
|---|---|---|
| `products/detective/` | `detective` | Sherlock Holmes (e.g. *Adventures of Sherlock Holmes*, *Hound of the Baskervilles*) |
| `products/shakespeare/` | `shakespeare` | Shakespeare (e.g. *Hamlet*, *Macbeth*, sonnets) |
| `products/science/` | `science` | Science classics (e.g. Darwin, *On the Origin of Species*) |

Distinct vocabularies make leaks eyeball-obvious ("deduction" vs "thou art" vs "natural selection"). Strip Gutenberg license headers/footers during ingest.

### A.2 Ingest contract
```python
@dataclass
class SourceDoc:
    text: str
    product_id: str   # from the folder
    source: str       # filename / book title
```
`load_products(root: Path) -> list[SourceDoc]` walks `products/*/*.txt`, deriving `product_id` from the folder name. A file whose `product_id` can't be derived is a hard error (T4).

### A.3 Gotchas
- Gutenberg files carry `*** START/END OF THE PROJECT GUTENBERG EBOOK ***` boilerplate — trim it.
- Encoding: read as UTF-8.

---

## Part B — Chunking

### B.0 Scope
Split each `SourceDoc` into chunks with stable ids and inherited metadata.

### B.1 Strategy
`RecursiveCharacterTextSplitter.from_tiktoken_encoder(chunk_size=512, chunk_overlap=0)` (langchain-text-splitters + tiktoken). Token-accurate so "512" means tokens, not characters.

### B.2 Chunk record
```python
@dataclass
class Chunk:
    id: str          # f"{product_id}:{source}:{ordinal}" — stable, unique
    text: str
    product_id: str
    source: str
```
`chunk_size`/`overlap`/`strategy` are parameters (the `chunking-lab` skill sweeps them).

### B.3 Gotchas
- Keep `chunk_size` ≤ the model's max sequence (bge-small = 512) so nothing is silently truncated at embed time.

---

## Part C — Embeddings

### C.0 Scope
A wrapper that embeds documents and queries **identically** (the parity rule).

### C.1 Contract
```python
class Embedder:
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...  # encode_document()
    def embed_query(self, text: str) -> list[float]: ...                   # encode_query()
```
- Model `BAAI/bge-small-en-v1.5`, `device="cpu"`, `normalize_embeddings=True`.
- Use sentence-transformers 5.x `encode_query` / `encode_document` so bge's asymmetric query prefix is handled automatically.

### C.2 Gotchas (the classic footguns)
- **Parity:** index and query MUST use the same model + normalization + prompt convention. A mismatch silently tanks recall.
- If using Chroma's `embedding_function`, the collection embeds both sides consistently — but still respect the query/document distinction.

---

## Part D — Vector store (Chroma)

### D.0 Scope
A thin adapter behind a protocol so Phase 2 can swap in Azure.

### D.1 Protocol (the one real abstraction)
```python
class VectorStore(Protocol):
    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...
    def query(self, embedding: list[float], k: int, where: dict | None) -> list[Hit]: ...
# Hit = {id, text, product_id, source, score}
```

### D.2 Chroma specifics
```python
client = chromadb.PersistentClient(path="./.chroma")
# chromadb 1.5.x: configuration= is the current form; legacy metadata={"hnsw:space":...} is
# deprecated. embedding_function=None — we hand Chroma our own bge vectors; it never embeds.
col = client.get_or_create_collection(
    "corpus", configuration={"hnsw": {"space": "cosine"}}, embedding_function=None
)
# upsert, NOT add: add() silently keeps the first write on a duplicate id; upsert overwrites,
# so re-indexing on stable ids stays idempotent.
col.upsert(ids=[...], embeddings=[...], documents=[...],
           metadatas=[{"product_id": c.product_id, "source": c.source} for c in chunks])
col.query(query_embeddings=[emb], n_results=k, where=where)   # where = the entitlement filter
```
`where` operators available: `$eq $ne $gt $gte $lt $lte $in $nin $and $or`.

### D.3 Gotchas
- **Default space is L2** — set cosine explicitly (decision #3).
- **Distance → score:** a cosine collection returns *distance* in [0, 2] (0 = identical); expose `score = 1 - distance` (cosine similarity, bigger = closer).
- `.chroma/` is git-ignored (it's a rebuildable artifact).

---

## Part E — Security (the boundary) · satisfies SECURITY.md

### E.0 Scope
The entitlements map + the server-side filter builder + the compose/fail-closed logic.

### E.1 Contract
```python
ENTITLEMENTS: dict[str, list[str]]            # {user_id: [product_id]}
def entitlement_filter(user_id: str) -> dict   # {"product_id": {"$in": allowed}}; empty→$in:[] (fail closed)
def compose(entitlement: dict, caller_filter: dict | None) -> dict  # AND; caller can only narrow
```
See SECURITY.md §5 for the reference implementation. This module is the single source of authorization and the focus of the `access-control-reviewer`.

---

## Part F — Retrieval pipeline

### F.0 Scope
`retrieve(user_id, query, k=5, caller_filter=None) -> list[Hit]`:
```
flt = compose(entitlement_filter(user_id), caller_filter)
assert "product_id" in str(flt)          # T1 defense: never query unfiltered
emb = embedder.embed_query(query)
return store.query(emb, k=k, where=flt)  # filter INSIDE the query (pre-filter)
```

---

## Part G — The leak experiment (`demo.py`) · the payoff

For a user entitled to only `detective`, run the SAME query both ways and print results with `product_id` + score:
- **(a) `store.query(emb, k, where=None)`** → leaks `shakespeare`/`science` chunks.
- **(b) `retrieve("alice", query)`** → only `detective`.
Print them side by side. Optionally a third user (`root`) to show full-corpus retrieval. The visible diff between (a) and (b) is the lesson.

---

## Part H — Evaluation

### H.0 Scope
A golden-query harness (the `rag-eval-harness` skill) + the mandatory cross-tenant leak test.

### H.1 Golden set — anchored to source text (ADR-004)

Relevance is keyed to a verbatim **quote** from the source, never to a chunk id (ids shift under any re-chunk, so an id-pinned set can't survive the sweeps — ADR-004):
```python
# golden.json: [
#   {"q": "...", "user": "root", "product_id": "detective",
#    "source": "adventures-of-sherlock-holmes",
#    "relevant_quote": "<short verbatim snippet from the source>"}, ...
# ]
```
Hand-author ~5–10 queries/product against the `root` user (full corpus). At eval time a chunk counts as relevant if it **contains the quote** (whitespace-normalized), computed against whatever chunking is live — so the golden set is authored once and survives every sweep. Keep quotes short + mid-passage so they fit one chunk at the smallest swept size. (Span/offset anchoring is the documented rigor upgrade — ADR-004 Alternatives.)

### H.2 Metrics
`recall@k`, `hit-rate@k`, `MRR`, `nDCG@k` — mean over the golden set. This is the regression gate for chunk/embedding/retrieval changes.

### H.3 Cross-tenant leak test (mandatory · pytest)
For each non-root user, fire queries that *should* surface other products, assert every returned `product_id ∈ entitlements[user]`. Plus: unknown user → empty; caller filter can narrow not widen. Lands the moment E + F exist.

---

## Part I — Poke experiments (learning, write up in `docs/history/`)

Run these as a **cost-tiered sweep**, not ad-hoc (ADR-004 §2; procedure in the `chunking-lab` skill): sweep the **cheap** query-time axes (`k`, later rerank/hybrid) against one fixed index first, then the **expensive** re-embed axes (chunk size/overlap/model), each with a corpus-sample pre-pass before a full embed. Expensive axes on the outer loop, cheap on the inner; one variable per comparison.

- **Chunk size sweep** — 256 / 512 / 1024 vs the eval metrics (the headline expensive-axis sweep). Small matrix: `size ∈ {256,512,1024} × k ∈ {3,5,10}` = 3 re-embeds, 9 evals.
- **Exact vs paraphrased query** — show dense retrieval handling paraphrase, and where exact-term queries motivate hybrid/BM25.
- **Scores** — print similarity scores to build intuition for thresholds.

---

## Part J — Acceptance & open questions

### J.1 Acceptance criteria
- [ ] `products/` holds the 3 collections; ingest trims Gutenberg boilerplate and stamps `product_id`.
- [ ] Index builds into Chroma (cosine) with metadata on every chunk.
- [ ] `retrieve()` applies the server-side filter inside the query and refuses to run unfiltered.
- [ ] **Leak demo** shows un-filtered leak and filtered clean result, explained.
- [ ] **Cross-tenant test green** — no unauthorized `product_id` ever returned; unknown user → empty.
- [ ] Eval harness runs over the golden set and reports the 4 metrics.
- [ ] At least the chunk-size and exact-vs-paraphrase experiments written up.

### J.2 Open questions
**Resolved:** golden-set *anchoring* → source-text/quote (ADR-004). Still open — see PLANNING §Open Questions (reranking, local hybrid, generation, golden-set *size*). Resolve via ADRs as they come up.

---

## Appendix — config defaults
```
COLLECTION = "corpus"        MODEL = "BAAI/bge-small-en-v1.5"
CHUNK_SIZE = 512             CHUNK_OVERLAP = 0
K = 5                        SPACE = "cosine"
CHROMA_PATH = "./.chroma"    PRODUCTS_ROOT = "./products"
```

## Sources
chromadb 1.5.x docs (Context7); sentence-transformers 5.5.x; langchain-text-splitters 1.1.x; research brief 2026-06-06. Azure mappings deferred to the Phase-2 spec.
