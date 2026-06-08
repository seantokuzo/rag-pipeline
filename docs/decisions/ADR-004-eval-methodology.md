# ADR-004: Evaluation methodology — source-anchored golden set + cost-tiered sweeps

**Status:** Accepted
**Date:** 2026-06-07
**Supersedes:** none
**Superseded by:** none

## Context

Phase 1 ships an eval harness (build-order step 10) and tuning "poke" experiments (step 11 / the `chunking-lab` skill), chief among them a **chunk-size sweep** (256/512/1024). Two design questions fall out of that, and the spec as first drafted (Part H.1) answered the first one wrong.

1. **What does the golden set point *at*?** The draft `golden.json` pinned each query's relevant results to **chunk ids** (`"relevant_ids": ["detective:...:12"]`). But a chunk id is an artifact of one chunking config: `product_id:source:ordinal`. Change `chunk_size` 512→256 and chunk `:12` is now a *different slice of text* — every chunk-id-pinned judgment silently points at the wrong content. A golden set keyed to chunk ids **cannot survive the very sweep it exists to measure.** Re-labeling by hand per config is tedious and, worse, injects labeler inconsistency that biases the comparison.

2. **How do we run the sweeps without burning compute?** Re-embedding the corpus is the expensive stage; most knobs don't actually require it. With no cost model you re-embed on every tweak — tolerable at 990 chunks, ruinous at enterprise scale. The lab's stated goal is to *mimic the production discipline* even on a tiny corpus, so we want the method, not just the result.

## Decision

### §1 — The golden set is anchored to the source text, never to chunk ids

A golden record names a **query, its product/source, and a verbatim `relevant_quote`** drawn from the source document — not a chunk id:

```json
{
  "q": "Who is Irene Adler to Holmes?",
  "user": "root",
  "product_id": "detective",
  "source": "adventures-of-sherlock-holmes",
  "relevant_quote": "To Sherlock Holmes she is always THE woman"
}
```

At eval time, for *whatever* chunking config is live, a retrieved chunk counts as **relevant if it contains the quote**, compared whitespace-normalized:

```python
" ".join(quote.split()) in " ".join(chunk.text.split())
```

Relevance is thus a property of the **content**, computed against the live chunks — invariant to `chunk_size`, `chunk_overlap`, and strategy. The golden set is authored once and survives every sweep. Quotes are kept **short and distinctive** (a sentence or clause) so they fit inside a single chunk even at the smallest swept size, and chosen mid-passage to avoid boundary straddling.

**Chunk ids do not go away** — they remain the vector store's primary key, give stable upserts/citations at a *fixed* config, and stay `product_id:source:ordinal`. They are simply not what the golden set is keyed to. Reproducible *eval* comes from the source anchor; stable *ids* keep the *store* consistent within one config — two different jobs.

### §2 — Sweeps are cost-tiered: never re-embed for a knob that didn't change the vectors

Knobs split by cost:

| Tier | Knobs | Cost | Why |
|---|---|---|---|
| **Cheap** | `k`, reranking, hybrid weight, query phrasing | ~free | query-time only — reuse the existing index |
| **Expensive** | `chunk_size`, `chunk_overlap`, strategy, embed model/dims | full corpus re-embed | they change the stored vectors |

Procedure:

1. **Sweep cheap axes first**, against one fixed/persisted index — lock them in for free.
2. **Then sweep expensive axes**, each value = one re-embed. For these, do a **corpus-sample pre-pass** (embed a subset, eval on the matching golden-set slice for a directional signal) and full-embed only the finalists — coarse-to-fine.
3. **Matrix ordering:** expensive axes on the *outer* loop, cheap axes *inner* — minimize re-embeds. One variable changes per *comparison*, so deltas stay attributable.

Our small-but-real matrix: `chunk_size ∈ {256, 512, 1024} × k ∈ {3, 5, 10}` → **3 re-embeds, 9 evals.**

#### On the embedding cache — the enterprise pattern we deliberately do *not* build

**How it works.** A content-addressed embedding cache keys each vector by `hash(model_id + normalization + chunk_text)` and skips the model call on a hit. Before embedding a chunk you look it up; you only pay to embed *misses*.

**Why it pays at scale.** When you have millions of chunks and embeddings cost real GPU-time/money, the cache turns several common operations near-free: re-running a pipeline after a code change, embedding only the *changed* slice of a corpus on update (the other 99% hit the cache), or A/B-ing **query-time** knobs while chunking is held fixed (the document vectors never change, so every one is a hit). It's the right lever precisely when re-embedding is both frequent and expensive.

**Why it's moot for *us*** — two concrete reasons:

- **Chroma's `PersistentClient` already gives us the win that matters here.** The index persists to disk, so a fixed-config corpus is embedded *once* across sessions, not on every run (ADR-001). That covers the only case we hit repeatedly.
- **It wouldn't even help our headline sweep.** A `chunk_size`/`overlap` change rewrites *every* chunk's text → every cache key is new → ~0 hits. A content cache pays off only when *identical* `(text, model)` pairs recur, which a chunking sweep by definition does not produce.

So a bespoke cache here would be **cargo-cult optimization** — the ritual without the conditions that make it pay. We document it (this section) so it's understood and reachable when a real condition appears (partial-corpus updates, or a model A/B at *fixed* chunking), and revisit then.

## Alternatives considered

- **Pin the golden set to chunk ids (the original Part H.1).** Rejected: cannot survive a re-chunk; defeats the chunk-size sweep that is a Phase-1 deliverable; manual re-labeling biases the comparison.
- **Span/offset anchoring instead of quotes** (`relevant_span: [start, end]`; relevance = chunk `[start,end]` overlaps the span). The *more* rigorous, production-grade form — handles partial overlap, multi-chunk answers, graded nDCG. **Deferred, not rejected:** it requires every chunk to carry source offsets (flip the splitter to `add_start_index=True`, store `start`/`end` on `Chunk`), which is more than 990 chunks of prose need. **This is the documented upgrade path** — adopt if/when graded relevance or multi-chunk answers matter, or in Phase 2. Quote-containment gives ~all the signal at our scale with zero chunk-record changes.
- **Build a content-addressed embedding cache now.** Rejected for the reasons in §2 (redundant with Chroma persistence; busts on the chunking sweep). Documented as the at-scale pattern.
- **Brute-force the full config grid (cartesian product).** Rejected: combinatorial re-embeds and hard-to-attribute interactions. Cost-tiered coordinate-descent gets the learning signal far cheaper; one variable per comparison keeps deltas readable.

## Consequences

### Positive
- The golden set is authored **once** and stays valid across every chunk/embed sweep — the chunk-size experiment becomes apples-to-apples.
- Sweeps cost the minimum: cheap knobs never trigger a re-embed; expensive ones get a sample pre-pass.
- The lab teaches the real production discipline — cost tiering, coarse-to-fine, *and* recognizing when an optimization (caching) is cargo-cult — on a corpus small enough to feel it instantly.

### Negative
- Quote-containment is **binary** relevance — no graded scoring, and a quote that accidentally straddles a chunk boundary at the smallest size reads as a miss (mitigated by short, mid-passage quotes). Graded relevance needs the deferred span upgrade.
- A little authoring discipline: quotes must be verbatim and short (whitespace-normalized matching absorbs formatting noise).

### Neutral
- Adds no code now; this is a design lock realized at steps 10–11. `chunk.py` is unchanged.
- The span upgrade and the embedding cache are both written down as conditional future moves, not lost.

## Links
- `docs/spec-phase-1.md` — Part H (eval), Part I (sweeps); H.1 updated to the source-anchored schema, Part I to the cost-tiered matrix.
- `.agents/skills/chunking-lab/SKILL.md` — the cost-tiered sweep procedure (the how-to to this ADR's why).
- `.agents/skills/rag-eval-harness/` — the metrics (recall@k / MRR / nDCG) this methodology feeds.
- `docs/explainers/chunking.md` — stable-id framing corrected to match §1.
- ADR-001 — Chroma `PersistentClient` (the persistence that subsumes our caching need) + bge-small.
- ADR-002 — pooled access control (the `user`/entitlement axis the golden set's `user` field exercises).
