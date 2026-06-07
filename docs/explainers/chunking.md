# Chunking — how it works

> Part of the [RAG explainer series](./README.md). Understanding-oriented: *how the concept works*, not the build steps. Step-agnostic (organized by process, not build order).

**Where it sits:** `ingest → `**`chunk`**` → embed → store/index → [query] retrieve`. Chunking is a **pure text transformation**: whole documents in, small text pieces out. No ML, no database.

## Why chunk at all?

1. **The embedding model has a hard input limit.** Our model (bge-small) maxes out at **512 tokens**. Feed it a whole book and everything past token 512 is *silently truncated* (dropped). Splitting is mandatory, not optional.
2. **Retrieval precision.** We want to return the *relevant passage*, not a whole book. Small chunk = sniper; whole book = shotgun. The chunk is the smallest unit retrieval can hand back.
3. **One vector = one coherent idea.** The embed stage turns each chunk into a single vector (a "meaning fingerprint"). A whole book has too many topics to compress into one fingerprint usefully; a ~2–3-paragraph chunk is focused enough that its fingerprint actually means something.

## Tokens & sizing

A **token** ≈ a word-piece: roughly **4 characters / ¾ of a word**. So **512 tokens ≈ ~380 words ≈ 2–3 paragraphs**.

We size chunks with **`tiktoken`** (a tokenizer) so "512" means *tokens*, not characters — character-based splitting would over/under-shoot wildly for the model.

> ⚠️ **Subtlety:** tiktoken is OpenAI's tokenizer; bge uses a slightly different one (BERT WordPiece). So "512 tiktoken tokens" is a *close approximation* of bge's 512-token limit, not an exact match. Fine in practice; if we ever see truncation at embed time, we lower the target to leave margin.

## Recursive splitting & overlap

We use a **recursive** splitter (`RecursiveCharacterTextSplitter.from_tiktoken_encoder`). "Recursive" = it splits on natural boundaries in priority order — **paragraphs (`\n\n`) → lines → sentences → words → characters** — using the biggest boundary that still gets the piece under the token limit. The payoff: it avoids hacking through the middle of a word or sentence, so chunks stay readable and semantically whole.

**Overlap** = how much text repeats between consecutive chunks (e.g. the last 50 tokens of chunk N also open chunk N+1) so an idea straddling a boundary isn't lost. We **start with overlap = 0** (disjoint slices); overlap is a tunable knob, not a guaranteed win. (The `chunking-lab` skill sweeps size/overlap against the eval metrics.)

## Where do the chunks go?

**During chunking: nowhere persistent.** They're just a `list[Chunk]` in memory — like building an array of DTOs. No database, no disk yet.

They get a *home* downstream:
- **embed:** attach a vector to each chunk.
- **store/index:** write `{id, text, vector, metadata}` into the vector DB (Chroma, on disk).

So the **chunk is the unit that flows through the rest of the pipeline** and ultimately lands as a row in the vector store. **Chunking is separate from embedding on purpose** — so you can inspect and tune the chunks *before* spending compute on embeddings.

## Metadata & the security tie-in 🔐

Every chunk **inherits `product_id` and `source`** from its parent document, stamped **at chunk time**. By the time chunks reach the DB, *every one* wears its "which product am I" tag.

That tag is **the hook the access-control filter grabs.** At query time we filter `WHERE product_id IN (the user's entitled products)` *before* the vector search. If even one chunk were unlabeled, it'd be un-securable → a potential leak. This is why ingest hard-errors on a missing `product_id`, and why chunking propagates it onto every piece. **The metadata stamped here is what makes the leak-stopping filter possible later.** (See [`../SECURITY.md`](../SECURITY.md).)

## The `Chunk` shape & stable ids

```
Chunk { id, text, product_id, source }
```

- **`text`** — the slice (what gets embedded and returned to the user).
- **`product_id` / `source`** — metadata: filtering + provenance.
- **`id`** — the primary key: `product_id:source:ordinal`, e.g. `detective:adventures-of-sherlock-holmes:0`, `:1`, `:2`…

**Ids are deterministic on purpose.** The eval harness will assert "the right answer to query X is chunk `detective:…:42`." If ids were random or shifted every re-run, that golden set would break. So id = `product_id` + `source` + position — stable across re-indexing as long as the source text and chunk settings don't change.

> This is also why we *freeze* the corpus text and don't casually re-trim it: changing the text shifts chunk boundaries → shifts ordinals → breaks ids.

## How the data shape evolves

```
SourceDoc { text:<whole book>, product_id, source }
   │  chunk  ── stamp product_id/source on each piece ──┐
   ▼                                                     │
Chunk { id, text:<~512-tok slice>, product_id, source } ×many
   │  embed                                              │
   ▼                                                     │
Chunk + vector[384]                                      │
   │  index                                              ▼
   ▼
Chroma row { id, document:text, embedding, metadata:{product_id, source} }
```

## Rough scale (this project)

At ~4 chars/token and 512-token chunks, our 3 books (~178K–933K chars) produce a **ballpark of ~800 chunks total** (a bit more in practice, since the recursive splitter breaks early at paragraph boundaries). Exact counts come out when we run it.

## TL;DR

Chunking slices whole documents into bite-size, **security-tagged** text pieces **in memory** — no vectors, no DB (those come at embed/index). The `product_id` stamp is what keeps retrieval leak-proof; the stable `id` is what keeps the eval reproducible.
