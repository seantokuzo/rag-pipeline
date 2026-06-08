---
name: chunking-lab
description: Experiment with chunking strategies (size, overlap, recursive vs semantic) and measure the impact via the rag-eval-harness. Use when tuning chunking or exploring how chunk choices move retrieval quality.
---

# Chunking Lab

Chunking is the highest-leverage, least-glamorous RAG knob. This skill is how you *feel* that, empirically, instead of guessing. Pair every change with the `rag-eval-harness` and write findings to `docs/history/`.

## The knobs (in `chunk.py`, all parameters)
- **size** (tokens) — token-accurate via tiktoken, not characters.
- **overlap** (tokens) — shared tokens between adjacent chunks.
- **strategy** — recursive (default) → semantic → late/contextual (later stages).

## 2026 starting point & progression
1. **Start:** recursive, **512 tokens, NO overlap**. Strong 2026 default; overlap is no longer a free win and adds index cost. (`langchain-text-splitters` `RecursiveCharacterTextSplitter.from_tiktoken_encoder`.)
2. **Tune size to query type:** factoid/lookup 64–256; prose 512–1024 (prose often peaks ~1024). Sweep 256/512/1024 against the eval metrics.
3. **Add overlap only if** boundary-sensitive content (a relevant answer keeps getting split) shows up in failing eval queries.
4. **Semantic / late / contextual chunking** — only when the eval says recursive is the bottleneck. Semantic chunking can be ~14× slower for modest gains; Anthropic's *contextual retrieval* (prepend an LLM-generated context blurb per chunk before embedding) is powerful (~35% fewer retrieval failures, more with BM25+rerank) but costs an LLM pass. Earn these with data.

## Procedure (the A/B loop)
1. Pick one variable (e.g. size ∈ {256, 512, 1024}); hold the rest fixed.
2. Re-chunk → re-embed → re-index for each value (chunk ids *and* vectors change — see gotcha).
3. Run `rag-eval-harness` for each; record recall@k / MRR / nDCG.
4. Pick the winner by the metric you care about; write a short entry in `docs/history/` (what you tried, the numbers, what surprised you).

## Cost-tiered sweeping — don't re-embed when you don't have to (ADR-004 §2)

The A/B loop above is the *unit*; this is how you *order* many of them cheaply. Split knobs by cost:

| Tier | Knobs | Cost | Reuse |
|---|---|---|---|
| **Cheap** | `k`, rerank, hybrid weight, query phrasing | ~free | re-query the **same index** |
| **Expensive** | `chunk_size`, `chunk_overlap`, strategy, embed model/dims | full re-embed | rebuild from the chunks up |

1. **Cheap axes first**, against one fixed/persisted index — lock them in for free.
2. **Then expensive axes.** Each value = one re-embed; do a **corpus-sample pre-pass** (embed a subset, eval the matching golden-set slice) and full-embed only the finalists.
3. **Order the matrix:** expensive on the outer loop, cheap on the inner. One variable per comparison so deltas stay attributable.
4. **No embedding cache here** — Chroma already persists the fixed-config index, and a size/overlap change busts every content key (~0 hits). It's an at-scale pattern; ADR-004 §2 covers when it *does* pay.

Small matrix for this corpus: `size ∈ {256,512,1024} × k ∈ {3,5,10}` → 3 re-embeds, 9 evals.

## Per-content-type notes
- **Prose** (Holmes, Shakespeare, Darwin): recursive/structure-aware splitting works well.
- **Transcripts** (the future "video" product): no document structure — align windows to speaker turns / timestamps; this is where semantic chunking can earn its cost.

## Gotchas
- **Max sequence:** keep size ≤ the embedding model's limit (bge-small = 512 tokens) or text is silently truncated at embed time.
- **Stable ids shift when you re-chunk** — and that's fine: the golden set anchors to source *quotes*, not ids (ADR-004), so it survives sweeps without re-mapping. (Pre-ADR-004 this meant manual re-labeling — no longer.)
- **Re-index every change:** the store holds the *old* chunks until you rebuild. Don't compare a new chunker against a stale index.
- **Parity is untouched by chunking** — you still embed query vs document the same way (`encode_query`/`encode_document`).
