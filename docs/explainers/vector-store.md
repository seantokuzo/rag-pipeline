# The vector store & indexing — how it works

> Part of the [RAG explainer series](./README.md). Understanding-oriented: *how the concept works*, not the build steps. Step-agnostic (organized by process, not build order).

**Where it sits:** `ingest → chunk → embed → `**`store / index`**` → [query] retrieve`. Embedding handed us 990 vectors (384 floats each) with their text and metadata riding alongside. The **store** is where those land and become *searchable*; **indexing** is the one-time act of writing them in. Everything downstream — retrieval, the entitlement filter, eval — reads from here.

## What a vector store actually is

A normal database answers *"find rows where `author = 'Doyle'`"* — **exact-value** matching. A vector store answers a different question: *"find the rows whose meaning is **nearest** to this one."* It does **two jobs at once**, and you need both:

1. **Nearest-neighbour search over vectors** — given a query vector, return the stored vectors closest to it (by cosine angle, for us). This is the semantic-search engine.
2. **Metadata filtering** — narrow the candidate set by structured tags (`product_id`, `source`) *before or during* that search.

Job 2 is the part people forget exists — and it's the part our whole security model hangs on. A vector store isn't "just a list of vectors"; it's vectors **plus** the metadata that lets you say *who's allowed to see what*.

## Chroma, concretely

Phase 1 uses **Chroma** as an in-process library — `PersistentClient` writes an index to a folder on disk (`./.chroma`). No server, no Docker; it's the SQLite of vector stores.

The unit of storage is a **collection** (think: one table). We use a single collection, `corpus`. Each **row** is four things bound together:

```
row = {
  id:        "detective:adventures-of-sherlock-holmes:42"   # our stable chunk id
  embedding: [0.013, -0.07, … ]   # 384 normalized floats  → searched over
  document:  "<the chunk's full text>"                       → returned to the caller
  metadata:  { product_id: "detective", source: "adventures-…" }  → filtered on
}
```

Writing them in is one call:

```python
col.upsert(
    ids=[c.id for c in chunks],
    embeddings=embeddings,                # from embed_documents()
    documents=[c.text for c in chunks],   # FULL text, untruncated
    metadatas=[{"product_id": c.product_id, "source": c.source} for c in chunks],
)
```

Note **all four lists are positional** — index *i* of each must describe the same chunk. That 1:1 alignment (chunk ↔ embedding ↔ text ↔ metadata) is the contract the embed step set up, and it must hold here or rows get mismatched vectors. (This is also where the chunk's **full** text is stored — recall from [embedding](./embedding.md) that the 2 over-long chunks only had their *vector* truncated; the `document` written here is complete.)

## ★ Cosine space, not L2 — the headline footgun

When you create the collection you choose its **distance function**, and **Chroma defaults to L2** (straight-line / Euclidean distance). For our **normalized** vectors that default is wrong — we must set **cosine** explicitly:

```python
col = client.get_or_create_collection("corpus", configuration={"hnsw": {"space": "cosine"}})
```

Why this matters, and why it's a *silent* trap:

- Our embeddings are **unit length** (the embed step normalized them). The meaningful signal is **direction**, and direction-similarity = **cosine**. (See [embedding](./embedding.md) — normalization here and cosine there are a **matched pair**.)
- With normalized vectors, L2 and cosine happen to *rank* neighbours the same way — so a wrong L2 setting **won't crash and won't obviously break**; it just makes the distance *numbers* wrong, which quietly corrupts any score threshold, any "is this match good enough?" cutoff, and any comparison across runs.
- **The space is fixed at creation.** You can't change a collection's metric later — set it wrong and *every* query for the life of that index is subtly off. There's no error, just slow rot. This is exactly the kind of bug this lab exists to make you feel.

> ✅ Verified (chromadb **1.5.9**): use the typed `configuration={"hnsw": {"space": "cosine"}}` — the current 1.0+ form. The older `metadata={"hnsw:space": …}` still works but is the deprecated legacy form (and stores the space inconsistently in `collection.metadata`), so we don't use it. The *concept* is what's permanent: **cosine, chosen explicitly, once, at creation** — it cannot be changed afterward.

## HNSW — the index under the hood

How does it find the nearest of N vectors without comparing against all N? It builds an **HNSW** index (*Hierarchical Navigable Small World*) — a layered graph you can think of as "skip-lists for geometry": start coarse at the top layer, hop greedily toward the query, refine on the way down. It gives **approximate** nearest neighbours — ~99% of the true top-k for a *huge* speedup at scale.

At our **990 vectors** this is total overkill (brute-forcing all 990 would be instant and exact) — but it's the same machinery that lets production stores search **millions** of vectors in milliseconds, so it's worth knowing it's there. "ANN" (approximate NN) is the standard; the approximation is tunable, and at small scale it's effectively exact anyway.

## The metadata that rides along 🔐

Every row carries `product_id` and `source` *next to* its vector. This is **not** decoration:

- `product_id` is the **licensing/entitlement key** — which "product" (corpus folder) the chunk belongs to. The access-control filter narrows on exactly this.
- An **unlabelled** row is **un-securable** — there's no way to decide who may see it — which is why [ingest](./chunking.md) stamps it on *every* chunk and treats a missing tag as a hard error.

Storage is where that tag finally sits beside the vector it protects, ready for the filter. (Full threat model: [`../SECURITY.md`](../SECURITY.md).)

## ★ The `where` pre-filter — where the security lesson begins

Chroma's query takes an optional **`where`** clause that filters on metadata **as part of the search**:

```python
col.query(
    query_embeddings=[query_vec],
    n_results=k,
    where={"product_id": {"$in": ["detective", "science"]}},   # the entitlement filter
)
```

This is **THE seam** the whole project is built around. The critical property: the filter is applied **inside** the query — a **pre-filter** — so the nearest-neighbour search only ever *considers* rows you're allowed to see. Contrast the wrong way:

- **Pre-filter (correct):** "search only the entitled rows." You get the true top-k *among what you may see*, and forbidden rows are never even candidates.
- **Post-filter (broken):** "search everything, then drop the rows the user can't see." This (a) **leaks** — forbidden content reached the app layer before you dropped it — and (b) **silently loses authorized hits** — if 4 of your top-5 belonged to someone else, you return 1 result instead of refilling from allowed rows.

For now, the store just needs to **pass a `where` through to the query**. It does *not* invent the filter, and it does *not* accept one from the end user — that filter gets built **server-side from a trusted entitlements map** in `security.py` (step 7), and retrieval (step 8) AND-s it in. The store is the mechanism; the *policy* comes later. The available operators are `$eq $ne $gt $gte $lt $lte $in $nin $and $or`. Full treatment lands in the **retrieval & filtering** explainer; here, just lock in: *the store can filter inside the search, and that's the only kind of entitlement filtering we ever do.*

## The one real abstraction: the `VectorStore` seam

This is the **single** place we deliberately build an abstraction (everywhere else, premature abstraction is an [anti-pattern](../../CLAUDE.md)). A tiny Protocol:

```python
class VectorStore(Protocol):
    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...
    def query(self, embedding: list[float], k: int, where: dict | None) -> list[Hit]: ...

# Hit = {id, text, product_id, source, score}
```

- `store/base.py` — the Protocol + `Hit` shape (the contract).
- `store/chroma.py` — the Chroma implementation (Phase 1).
- `store/azure.py` — Azure AI Search (Phase 2), behind the *same* Protocol.

Why here and nowhere else: Phase 1→2 genuinely **swaps the store** (Chroma → Azure) and the embed adapter, and *nothing else* — the pipeline stages and the **security invariant** stay put. One clean seam earns its keep; a speculative "any database" layer would not.

## Indexing = filling the store (step 6)

"Indexing" is just the **one-time write**: run `ingest → chunk → embed → upsert` to populate the collection, then queries read it many times. Two things make re-indexing safe:

- **Stable ids** (`product_id:source:ordinal`) + **`upsert`** (not `add`) mean re-writing a chunk **overwrites** it in place instead of duplicating — so re-running the index after a code change is idempotent, not additive. (Verified footgun: Chroma's `add()` *silently keeps the first write* on a duplicate id — no error, no update — which is exactly why the store uses `upsert()`.)
- It's a **write-once, read-many** shape: the expensive embed happens at index time; queries are cheap lookups against the built index.

## The Hit shape & the score (distance, inverted)

A query returns parallel lists (`ids`, `distances`, `documents`, `metadatas`) — nested one level per query, so since we send a single query we read index `[0]` of each; we zip them into `Hit` records. One gotcha in the number: Chroma returns a **cosine distance**, where **smaller = closer** (`0` = identical direction, up to `2` = opposite) — the *inverse* of the cosine *similarity* (where bigger = closer) from the embedding explainer. **Our choice (locked):** `score = 1 − distance`, i.e. plain **cosine similarity** (`1.0` = identical, bigger = closer) — so "higher is better" holds everywhere downstream and the score reads in the same units as the embedding step's cosine numbers (the 0.9424 doc-vs-query readout). Pick one and be consistent, or every ranking readout lies.

## How the data shape evolves

```
Chunk { id, text, product_id, source }   +   embedding[384]
        │  upsert  (write all four, positionally aligned)
        ▼
Chroma collection "corpus"  (cosine space, HNSW index)
   row { id, embedding[384], document:text, metadata{product_id, source} }
        │  query(query_vec, k, where={product_id ∈ allowed})   ← pre-filter inside the search
        ▼
list[Hit] { id, text, product_id, source, score }   (only entitled rows, top-k by cosine)
```

The **embedding** is what the search ranks on; the **metadata** is what the filter narrows on; the **document** is what comes back to the reader. The store is the one place all three live together.

## TL;DR

The vector store (Chroma, on-disk, in-process) is where embeddings become **searchable** — it does **nearest-neighbour search** *and* **metadata filtering** together. Two things matter most. **(1) Cosine, not L2:** Chroma defaults to L2, our vectors are normalized, so we set `cosine` explicitly at creation — a wrong setting fails *silently* and can't be changed later. **(2) The `where` pre-filter:** Chroma filters on metadata *inside* the search, and that pre-filter is the exact seam the entitlement check plugs into (pre-filter, never post-filter — post leaks and drops hits). Each row binds id + 384-d vector + full text + `{product_id, source}`; the metadata is what makes a row *securable*. We wrap it all behind one small `VectorStore` Protocol — the only abstraction we build, because it's the one thing Phase 2 swaps. Indexing is the idempotent write-once that fills it; queries read it and return `Hit`s ranked by cosine, scored from Chroma's (inverted) distance.
