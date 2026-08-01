# Retrieval — how it works

> Part of the [RAG explainer series](./README.md). Understanding-oriented: *how the concept works*, not the build steps. Step-agnostic (organized by process, not build order).

**Where it sits:** `ingest → chunk → embed → store / index →` **`[query] retrieve`**. Everything before this runs **once, offline**, and leaves a built Chroma collection: 990 chunks, each a normalized vector next to its `{product_id, source}` metadata (the *write* path — [vector-store](./vector-store.md)). Retrieval is the **read** path: it runs **online, once per question**, and turns a user's query string into a short ranked list of the chunks most relevant to it — *and only the ones that user is licensed to see*. (Contract: spec Part F; code: `src/rag_exp/retrieve.py`.)

## What retrieval actually is

Dense **nearest-neighbour search in vector space**. Indexing already turned every chunk into a 384-dim unit vector whose *direction* encodes its meaning. Retrieval does the same thing to the **question**, then asks the store: *which chunk vectors point most nearly the same way?* Closeness is cosine similarity; the k closest come back.

> Retrieval = **embed the question into the same space as the chunks, then ask the store for the nearest vectors — narrowed, before the search, to what the user may see.**

Two things have to be true for that to work, and they're the two halves of this doc: the question must be embedded **exactly like the chunks were** (parity), and the search must be **constrained to entitled rows** (the filter).

## The read path, stage by stage

`Retriever.retrieve(user_id, query, ...)` is the whole thing (spec F). Four stages:

```python
flt = compose(entitlement_filter(user_id), caller_filter)  # 1. authorize (server-side)
assert "product_id" in str(flt)                            # 2. refuse to run unfiltered
emb = self._embedder.embed_query(query)                    # 3. embed the query (PARITY)
return self._store.query(emb, k=k, where=flt)              # 4. nearest-k, filter INSIDE
```

1. **Authorize.** `user_id` → a server-side `where` filter from the trusted map; a caller filter (if any) is AND-ed *under* it so it can only narrow. Full story: [access control](./access-control.md). If the user has no licenses this **raises here**, before any embedding or store work.
2. **Refuse to run unfiltered.** A backstop assertion: if the filter ever lacked a `product_id` term, crash rather than fall through to a full-corpus search (threat T1).
3. **Embed the query** — the parity stage, below.
4. **Nearest-k, pre-filtered** — hand the query vector *and* the filter to the store together, so the filter constrains the candidate set *before* ranking. Out comes `list[Hit]`.

## The one rule that makes it work: parity

The query must be embedded with the **same model, the same normalization, and the matching prompt convention** as the chunks were — or the two vectors live in subtly different spaces and cosine similarity becomes noise. **A parity break doesn't error; it silently tanks recall.** That makes it the most dangerous footgun in the pipeline, because everything still "works," just worse.

bge-small is **asymmetric**, which makes parity a little counter-intuitive: passages are embedded **bare**, but a query gets a short instruction prefix (`"Represent this sentence for searching relevant passages: "`). So "same convention" here means *different calls on purpose*:

| Side | Call | Prefix? |
|---|---|---|
| Index (chunks) | `embed_documents` → `encode_document()` | no |
| Query | `embed_query` → `encode_query()` | yes |

Same model, same normalization, asymmetric-by-design prompt — that *is* the parity. (Why bge wants this, and how we register the prefix so it actually fires: [embedding](./embedding.md).) The demo leans on this: its (a) and (b) panels use the **same query vector** and differ *only* in the filter — so any difference you see is the filter, never an embedding artifact.

## What comes back — `Hit` and its score

Each result is a `Hit`:

```python
@dataclass(frozen=True, slots=True)
class Hit:
    id: str          # stable chunk id
    text: str        # the chunk's text
    product_id: str  # which product it belongs to  ← the thing the filter gates
    source: str      # which document within the product
    score: float     # cosine SIMILARITY in [-1, 1] — higher = closer
```

`score` is **cosine similarity**, derived as `1 - cosine_distance` in the store, so **higher is always better** (1.0 = identical direction). We expose similarity rather than raw distance so "bigger = more relevant" holds everywhere downstream and reads in the same units as the embedding step. Low or even negative scores are *informative*, not a bug: a detective-only user firing a science query gets back her best-matching *detective* chunks, and their low scores honestly say "these aren't a great match — but they're the best you're **entitled** to." (Score is also the raw material for a later relevance threshold or reranker — [poke experiments](../spec-phase-1.md).)

> 🚫 **Don't build a relevance threshold on this score — we measured it, and it doesn't separate.** Step 11 dumped the cosine of every top-1 hit next to every *relevant* hit across the golden set ([`EXP-chunk-size-sweep.md`](../history/EXP-chunk-size-sweep.md)). At 512 the mean score of **relevant** hits was **0.646** while the mean of top-1 hits that were **wrong** was **0.670** — the wrong answers scored *higher*. At 256 relevant edged ahead (0.712 vs 0.674) but the two ranges overlapped completely. **No global cutoff cleanly divides relevant from irrelevant.**
>
> The reason is structural, not a quirk of our corpus: a cosine score says *"these two vectors point in a similar direction"* — it's **similarity, not calibrated relevance**, and its scale drifts with query length, chunk length, and topic. "Everything above 0.75 is a good hit" is a tempting one-liner that quietly drops real answers and keeps confident wrong ones.
>
> The actual fix is a **cross-encoder reranker**: instead of comparing two independently-computed vectors, it feeds the query and the chunk through a model *together* and scores the pair jointly. Far more accurate, far too slow to run over the whole corpus — which is exactly why it goes **after** retrieval, re-ranking a top-k of ~20 down to the best 5. That's the Phase-2 candidate, and this measurement is why we want it.

## top-k, and why pre-filter changes what k means

`k` is how many hits you want back (`config.K = 5`). The subtle part: because the filter is a **pre-filter** (applied *inside* the search), `k` counts **entitled** rows. Alice asking for `k=5` gets *the 5 best chunks she's allowed to see*.

Contrast the wrong design — retrieve-then-drop (post-filter): fetch the global top-5, *then* remove the ones she can't see. That leaks (forbidden chunks reached the app layer) **and** silently returns fewer than 5 (some of her 5 got dropped, and the 6th-best *entitled* chunk never got a look). Pre-filtering is therefore both the security boundary *and* the thing that keeps top-k honest. (Store mechanism: the `where` section of [vector-store](./vector-store.md).)

## Why a `Retriever` object (not a bare function)

Retrieval holds two **expensive, reusable** things: a loaded embedding model (hundreds of MB, seconds to load) and an open store connection. Re-creating them per query would be absurd. So `Retriever` builds them **once** in `__init__`, and every `retrieve()` call is a cheap read against the warm model + connection:

```python
retriever = Retriever()             # load model + open store ONCE
retriever.retrieve("alice", q1)     # cheap
retriever.retrieve("alice", q2)     # cheap
```

Both collaborators are **injectable** (`Retriever(embedder=…, store=…)`) so the cross-tenant test and the ADR-004 sweeps can pass fakes or an alternate store — and so the demo can share one warm model across all its panels. (The spec sketched a bare `retrieve()`; the method keeps that signature, the class just owns the lifecycle.)

## The guarantee retrieval upholds

Retrieval is where the security invariant is *enforced*: `security.py` **builds** the filter, `retrieve` **refuses to run without it**. The stage-2 assertion is the backstop; the mandatory **cross-tenant leak test** is the proof it holds against real queries; the **leak demo** is the visible before/after. All three: [access control](./access-control.md).

## Same seam, Phase 2 (preview)

The read path is written against the `VectorStore` **seam**, so Phase 2 swaps engines without touching retrieval's shape:

| Concern | Phase 1 — Chroma | Phase 2 — Azure AI Search |
|---|---|---|
| Query embedding | bge-small `encode_query()` | Azure OpenAI `text-embedding-3-small` (+ `dimensions`) |
| Parity | same local model both sides | same Azure model + `dimensions` both sides |
| Nearest-k | `collection.query(query_embeddings=…)` | vector query (HNSW) |
| Pre-filter | `where={product_id …}` | `vectorFilterMode: preFilter` + OData filter |

Parity and pre-filter are **invariants**, not Chroma details — only the dialect changes.

## Control flow, end to end

```
   request: { user_id, query, k?, caller_filter? }
                 │
   user_id ─► entitlement_filter ─► compose(caller_filter)     ← authorize (server-side, AND-narrow)
                 │         └─ no licenses? raise NoEntitlementsError → deny, no query
                 ▼
   query ─► embed_query()  (bge encode_query, prefixed)         ← PARITY with the index side
                 ▼
   store.query(emb, k, where=flt)                               ← nearest-k, filter INSIDE (pre-filter)
                 ▼
   list[Hit]  — top-k entitled chunks, ranked by cosine similarity
```

## TL;DR

Retrieval is the **read path**: embed the question into the *same* vector space the chunks live in (**parity** — same model + normalization + bge's asymmetric query prefix, or recall silently dies), then ask the store for the **k nearest** chunk vectors by cosine similarity — with the server-side entitlement filter applied **inside** the search (**pre-filter**, so `k` counts only entitled rows and nothing forbidden ever reaches the app layer). Results come back as `Hit`s scored by cosine similarity (higher = better). A `Retriever` loads the model + store **once** and serves many cheap queries; it **refuses to query without an entitlement filter**. The authorization details live in [access control](./access-control.md); this doc is how a *question* becomes *ranked, authorized answers*.
