# Embedding — how it works

> Part of the [RAG explainer series](./README.md). Understanding-oriented: *how the concept works*, not the build steps. Step-agnostic (organized by process, not build order).

**Where it sits:** `ingest → chunk → `**`embed`**` → store/index → [query] retrieve`. Embedding is **pure compute**: text pieces in, vectors out. It's the first stage that runs an ML model — and the **first run downloads bge-small (~130 MB)** from Hugging Face, then caches it locally.

## What *is* an embedding?

An **embedding** turns a piece of text into a **vector** — a fixed-length list of numbers (for bge-small, **384 floats**). Picture it as a **coordinate in a 384-dimensional "meaning space."** Texts about similar things land **near each other**; unrelated texts land far apart. *"A study in deduction"* and *"Holmes reasoned from the mud on his boots"* point in nearly the same direction; *"the origin of species by natural selection"* points somewhere else entirely.

That's the whole trick of semantic search: we stop matching **words** and start matching **meaning-as-geometry**. The query becomes a point; retrieval returns the chunks whose points sit closest.

## The vector: 384 numbers, length 1

- **384 dimensions** — bge-small's fixed output size. Every chunk, whatever its length, becomes exactly 384 floats. (A full 512-token chunk gets *compressed* into those 384 numbers — which is exactly why chunk size matters: cram too many ideas in and the fingerprint goes muddy.)
- **Normalized to unit length** (`normalize_embeddings=True`) — each vector is scaled so its length is exactly 1, leaving only its **direction** meaningful. Why bother: it makes **cosine similarity** (the angle between vectors) equal to a plain dot product, and it's what makes the **cosine** distance space correct. This is the same `cosine` we set on the Chroma collection — the normalization here and the cosine space there are a **matched pair**; break one and the other lies to you.

## How "closeness" is measured: cosine similarity

We compare two vectors by the **angle** between them, not the straight-line distance:

- same direction (angle ≈ 0°) → **cosine ≈ 1** → very similar.
- unrelated (angle ≈ 90°) → **cosine ≈ 0**.
- opposite → cosine ≈ −1.

Because everything is normalized, *"points the same way" = "means the same thing."* Retrieval is then just: **find the chunk vectors with the highest cosine to the query vector.** (Chroma actually stores cosine *distance* = `1 − cosine similarity`, so there **smaller = closer** — same idea, inverted.)

## ★ The parity rule (the big lesson of this step)

**Index and query must be embedded the *exact same way*** — same model, same normalization, same prompt convention. Break parity and retrieval **silently** gets worse: no error, no crash, just garbage rankings. It is the single most common RAG footgun.

bge makes the rule sharp, because **bge is asymmetric** — it was trained to embed a *question* and a *passage* differently. A query gets a hidden instruction prefix (roughly *"Represent this sentence for searching relevant passages:"*); a document gets none. The point of that asymmetry: nudge the query vector to land near the **passages that answer it**, not near **other questions that look like it**.

sentence-transformers 5.x hands us this for free with two methods, and our `Embedder` wraps exactly them:

```python
class Embedder:
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...  # → encode_document()
    def embed_query(self, text: str) -> list[float]: ...                   # → encode_query()
```

- **`encode_document()`** — for the chunks (no query prefix). Used at **index** time.
- **`encode_query()`** — for the user's search text (adds the prefix). Used at **retrieve** time.

**The rule in one line:** chunks go through `embed_documents`, queries through `embed_query`, and *nothing* mixes the two. Embed a query as if it were a document and you've quietly tanked your recall — with green tests and a clean-looking pipeline.

## Where the model runs (and what it costs)

- **Model:** `BAAI/bge-small-en-v1.5`, **on CPU** (`device="cpu"`) — small and fast enough that we need no GPU.
- **First run downloads ~130 MB** (weights + tokenizer); after that it's cached and offline-fast.
- **Batched:** the ~990 chunks embed in batches for throughput — expect a one-time minute-or-few on CPU, then done.
- **Deterministic:** same text + same model → the same vector every time. That reproducibility is what lets the eval harness compare two runs and trust the difference is the *change*, not noise.

## The truncation check we deferred from chunking 🔎

Recall the chunking note: tiktoken (our **sizing** tokenizer) ≠ bge's **WordPiece** tokenizer, so "≤ 512 tiktoken tokens" is a close approximation, not a guarantee. **Embed is where the real limit bites.** bge silently drops anything past **512 of *its own* tokens**. So this stage is where we actually *verify*: count bge's real token lengths and flag any chunk that would be truncated. If some exceed 512, we lower the chunk-size target to leave margin and re-chunk. (We expect few or none — our tiktoken max was 510 — but "expect" isn't "verified.")

## Metadata & security: untouched here 🔐

Embedding only **adds a vector**; it does not touch `product_id` / `source`. The security tags ride along on the `Chunk`, unchanged, ready for the store/index step to write them next to the vector. Embedding is meaning-only — authorization stays the **filter's** job, downstream. (See [`../SECURITY.md`](../SECURITY.md).)

## How the data shape evolves

```
Chunk { id, text:<~512-tok slice>, product_id, source }
   │  embed  ── run text through bge-small (CPU) ──┐
   ▼                                               │
Chunk + vector[384]   (384 normalized floats)      │
   │  index                                        ▼
   ▼
Chroma row { id, document:text, embedding:[384], metadata:{product_id, source} }
```

The chunk's **text** is what gets embedded; the resulting **vector** is what retrieval searches over; the **metadata** is what the security filter narrows on. Embed produces the middle piece — and leaves the other two alone.

## TL;DR

Embedding runs each chunk through bge-small (CPU, ~130 MB on first download) to get a **384-float, unit-length vector** — a coordinate in "meaning space" where **cosine angle = similarity**. The one rule that matters: **parity** — chunks via `encode_document()`, queries via `encode_query()`, never mixed, or recall silently dies (bge's asymmetric query prefix is *why* the two methods exist). This step also **verifies** nothing exceeds bge's real 512-token limit (the check deferred from chunking). Vectors land in the store next; the security tags ride along untouched.
