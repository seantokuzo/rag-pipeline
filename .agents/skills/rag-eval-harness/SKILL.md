---
name: rag-eval-harness
description: Build and run a golden-query retrieval eval (recall@k, hit-rate, MRR, nDCG) for the RAG lab. Use when measuring retrieval quality, A/B-ing a chunk-size/embedding/retrieval change, or gating a change against regressions.
---

# RAG Eval Harness

A tiny, hand-rolled retrieval evaluator. It answers one question: *did we fetch the right chunks?* Keep it lighter than any framework — it's also how you learn the metrics. Lives in `src/rag_exp/eval.py` with a golden set at `eval/golden.json`.

## The golden set — anchored to source text (ADR-004)
A hand-authored list of queries, each with a verbatim **`relevant_quote`** from the source (built against the `root` user = full corpus, so entitlements don't confound retrieval quality). It anchors to the *source text*, **never to chunk ids** — so it survives any re-chunk (see ADR-004):
```json
[
  {"q": "how did Holmes deduce the visitor's profession?", "user": "root",
   "product_id": "detective", "source": "adventures-of-sherlock-holmes",
   "relevant_quote": "<short verbatim snippet from the source passage>"},
  {"q": "to be or not to be", "user": "root",
   "product_id": "shakespeare", "source": "hamlet",
   "relevant_quote": "To be, or not to be, that is the question"}
]
```
Start with ~5–10 queries per product. Keep quotes **short, distinctive, mid-passage** so they fit one chunk even at the smallest swept size. Authoring the golden set *is* part of the learning — you decide what "relevant" means.

## The metrics (what each tells you)
At eval time, **resolve each query's `relevant_quote` to the set of live chunks that contain it** (whitespace-normalized) — that's the relevant set for this run's chunking. Then retrieve top-k and compare, exactly as id-based eval would; the quote→ids resolution is the only added layer, the metric math is unchanged:
- **hit-rate@k** — did *any* relevant chunk make the top-k? (coarse: "did retrieval work at all?")
- **recall@k** — fraction of relevant chunks found in top-k. (coverage)
- **MRR** — 1/rank of the first relevant hit, averaged. (is the best answer near the top? ≥0.6 feels snappy)
- **nDCG@k** — position-weighted, graded relevance. (ranking quality)
Report the **mean per metric** over the golden set. That number is your regression gate.

## Procedure
1. Ensure the index is built (ingest → chunk → embed → upsert).
2. For each golden row: resolve `relevant_quote` → relevant chunk ids in the current index (scan chunks for the quote); `hits = retrieve(user, q, k)`; compute the four metrics from `hits` vs that resolved relevant set.
3. Print mean metrics; optionally per-query so you can see *which* queries fail.
4. Treat it as a gate: re-run after any chunk/embedding/retrieval change and compare. A drop = investigate before committing.

## Don't forget the security test (separate, mandatory)
Retrieval *quality* (this harness) is not retrieval *safety*. The **cross-tenant leak test** in `tests/` is a separate, mandatory pytest: for each non-root user, assert no returned `product_id` is outside their entitlements (+ unknown user → empty). Both must pass.

## Gotchas
- The golden set anchors to source **quotes**, not chunk ids (ADR-004), so it survives a re-chunk *without* re-mapping — quotes resolve to whatever chunks contain them at eval time. (Stable ids still matter as the store's key, just not as the eval anchor.)
- Eval the `root` user for quality; eval the *restricted* users for safety. Don't mix the two purposes.
- Keep k explicit and consistent across runs you're comparing.
