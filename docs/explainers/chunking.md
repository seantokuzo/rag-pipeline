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

**Ids are deterministic on purpose.** `id = product_id + source + position`, so the same text + same chunk settings always reproduce the same id — which lets the vector store re-index without churn and lets a retrieved hit cite its exact source slice. **Note:** the *eval golden set* is **not** keyed to these ids — it anchors to a verbatim source quote instead, so it survives a re-chunk that renumbers every ordinal (see [ADR-004](../decisions/ADR-004-eval-methodology.md)). Stable ids keep the *store* consistent at a fixed config; the source anchor keeps the *eval* reproducible across configs — two different jobs.

> This is also why we *freeze* the corpus text and don't casually re-trim it: changing the source text shifts chunk boundaries (renumbering ids) **and** can invalidate the verbatim quotes the eval golden set anchors to (ADR-004). The frozen corpus is the shared ground both stand on.

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

## Rough scale (this project — measured)

At ~4 chars/token and 512-token chunks, our 3 books produce **990 chunks total**: detective 317 · science 563 · shakespeare 110. Counts track book size (science is biggest at ~933K chars; Hamlet smallest at ~178K). Per-chunk token lengths land at **min 6 · max 510 · mean 396** — the mean sits ~77% of the 512 budget because the recursive splitter breaks *early* at paragraph boundaries rather than packing each chunk to the brim. (The original ~800 estimate undershot; those early breaks add chunks.)

## Tuning the knobs (when retrieval feels off) 🎛️

Chunking is the highest-leverage RAG knob — and it's **empirical**. You don't guess the right settings; you *measure* them. When retrieval seems off — it misses an answer you *know* is in the corpus, returns half-thoughts, or that tiny trailing chunk starts mattering — these are the levers. All are (or will be) parameters of `chunk_document(...)`, so the [`chunking-lab` skill](../../.agents/skills/chunking-lab/SKILL.md) can sweep them.

| Knob | In our code | Default | What turning it does |
|---|---|---|---|
| **size** (tokens) | `chunk_size` | 512 | **Smaller** → more precise hits, but more fragments & a thought can split across chunks. **Bigger** → more context per chunk, but a fuzzier vector (one fingerprint averaging more ideas) & you risk the 512 truncation wall. |
| **overlap** (tokens) | `chunk_overlap` | 0 | **>0** repeats the last N tokens of each chunk at the start of the next, so an answer straddling a boundary survives — at the cost of a bigger index & near-duplicate hits. Not a free win. |
| **strategy** | recursive (hardcoded today) | recursive | Swap *how* boundaries are chosen: recursive (structure) → **semantic** (embedding-aware) → **contextual** (an LLM blurb prepended per chunk). More power, more cost. |

**Rules of thumb (2026):** factoid/lookup corpora like small chunks (64–256); prose like ours (Holmes, Darwin, Hamlet) likes 512–1024 and often *peaks ~1024*. Reach for **size** first, **overlap** only if a *specific* failing query turns out to be an answer cut in half, and **strategy** upgrades last (semantic ≈ 14× slower for modest gains; contextual retrieval cuts failures ~35% but costs an LLM pass — earn them with data).

**The method — the A/B loop** (this is the whole game):

1. Change **one** knob; hold the rest fixed.
2. **Re-chunk → re-embed → re-index** — chunk ids *and* vectors both change, so the store must be rebuilt. Never compare a new chunker against a stale index.
3. Run the **eval harness** → `recall@k` / `MRR` / `nDCG`. The *number* decides, not the vibe.
4. Keep the winner; write up what you tried + the numbers in `docs/history/`.

*(That's the unit. The **cost-tiered** version — sweep cheap query-time knobs against one fixed index first, sample before full re-embeds — lives in the [`chunking-lab` skill](../../.agents/skills/chunking-lab/SKILL.md) and [ADR-004](../decisions/ADR-004-eval-methodology.md) §2. Re-embedding is the expensive part; don't pay it for a knob that didn't change the vectors.)*

> ⚠️ **You can't tune blind — and the measuring instrument isn't built yet.** The eval harness lands at **step 10**. Until then we hold the locked defaults (recursive · 512 · 0) and don't twiddle on a hunch. *Measure, then tune.*

**The specific "tiny trailing chunk" case** (our `min = 6` tokens): almost certainly cosmetic — a 6-token vector simply won't match much, so it rarely surfaces. *If* the eval ever shows it dragging precision, the fix isn't a global knob but a targeted **min-chunk merge**: fold any sub-threshold tail back into its predecessor. We'd add that only when the data asks — premature, it's just complexity.

## TL;DR

Chunking slices whole documents into bite-size, **security-tagged** text pieces **in memory** — no vectors, no DB (those come at embed/index). The `product_id` stamp is what keeps retrieval leak-proof; the stable `id` keeps the *store* consistent at a fixed config — while the eval stays reproducible by anchoring its golden set to the **source text**, not to ids ([ADR-004](../decisions/ADR-004-eval-methodology.md)).
