---
name: rag-eval-harness
description: Build and run a golden-query retrieval eval (recall@k, hit-rate, MRR, nDCG) for the RAG lab. Use when measuring retrieval quality, A/B-ing a chunk-size/embedding/retrieval change, or gating a change against regressions.
---

# RAG Eval Harness

A tiny, hand-rolled retrieval evaluator. It answers one question: *did we fetch the right chunks?* Keep it lighter than any framework — it's also how you learn the metrics. Lives in `src/rag_exp/eval.py` with a golden set at `eval/golden.json`.

## The golden set
A hand-authored list of queries with their known-relevant chunk ids (built against the `root` user = full corpus, so entitlements don't confound retrieval quality):
```json
[
  {"q": "how did Holmes deduce the visitor's profession?", "user": "root", "relevant_ids": ["detective:adventures:42", "detective:adventures:43"]},
  {"q": "to be or not to be", "user": "root", "relevant_ids": ["shakespeare:hamlet:18"]}
]
```
Start with ~5–10 queries per product. Authoring the golden set *is* part of the learning — you decide what "relevant" means.

## The metrics (what each tells you)
For a query, retrieve top-k ids, compare to `relevant_ids`:
- **hit-rate@k** — did *any* relevant chunk make the top-k? (coarse: "did retrieval work at all?")
- **recall@k** — fraction of relevant chunks found in top-k. (coverage)
- **MRR** — 1/rank of the first relevant hit, averaged. (is the best answer near the top? ≥0.6 feels snappy)
- **nDCG@k** — position-weighted, graded relevance. (ranking quality)
Report the **mean per metric** over the golden set. That number is your regression gate.

## Procedure
1. Ensure the index is built (ingest → chunk → embed → upsert).
2. For each golden row: `hits = retrieve(user, q, k)`; compute the four metrics from `hits` vs `relevant_ids`.
3. Print mean metrics; optionally per-query so you can see *which* queries fail.
4. Treat it as a gate: re-run after any chunk/embedding/retrieval change and compare. A drop = investigate before committing.

## Don't forget the security test (separate, mandatory)
Retrieval *quality* (this harness) is not retrieval *safety*. The **cross-tenant leak test** in `tests/` is a separate, mandatory pytest: for each non-root user, assert no returned `product_id` is outside their entitlements (+ unknown user → empty). Both must pass.

## Gotchas
- Stable chunk ids (`product_id:source:ordinal`) are required for the golden set to survive re-indexing — if you change chunking, ids shift and the golden set needs re-mapping.
- Eval the `root` user for quality; eval the *restricted* users for safety. Don't mix the two purposes.
- Keep k explicit and consistent across runs you're comparing.
