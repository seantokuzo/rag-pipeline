# EXP-chunk-size-sweep: Chunk size × k, exact vs paraphrase, and the bge-512 ceiling

**Status:** done
**Started / Completed:** 2026-07-27 / 2026-08-01
**Commits/PRs (if any):** Phase 1, step 11 (poke experiments) — committed on `phase-1/env-and-corpus`

## What shipped / what was tested

The Phase-1 headline "poke": how does **chunk size** move retrieval quality, and does the
step-10 baseline's low score come from chunk dilution (the stated hypothesis: *smaller
chunks → less dilution → higher recall*)?

- **Golden set** grown 18→**21 rows** and tagged `exact` / `paraphrase` (8 exact / 13
  paraphrase, 7 per product). "exact" = the query shares verbatim lexical overlap with the
  quote; "paraphrase" = a natural-language question with little/no lexical overlap. Every
  quote re-verified `|R|=1` at **256, 512, and 1024** (pre-flight, so the sweep can't
  hard-error on an unresolvable quote).
- **`eval.py`** extended to report **per-tier means** (the `exact`/`paraphrase` split) via a
  new tested `aggregate()` primitive.
- **Sweep matrix:** `chunk_size ∈ {256, 512, 1024} × k ∈ {3, 5, 10}` (ADR-004 §2 cost
  tiering — expensive size axis on the outer loop, cheap k inner; 3 re-embeds, 9 evals).
  256 and 1024 built into throwaway home-volume indices; the live 512 `./.chroma` reused.
- **Coarse-to-fine pre-pass:** a detective-only @256 corpus sample eval'd *before* the full
  256 embed, to practice ADR-004 §2's "predict on a sample before you pay for the full
  re-embed."
- **Score-intuition dump:** the raw cosine similarity of the top-1 hit vs the first
  *relevant* hit for every query, at 256 and 512.

## What worked

- **The per-tier split is the real lens.** The overall mean hides everything; `exact` vs
  `paraphrase` is where the physics shows up (below).
- **The pre-pass earned its keep as a *direction* predictor.** The detective-only @256
  sample scored hit@5 = 0.143 — identical to the detective slice at 512. It correctly said
  *"256 will not be a win for detective,"* which the full sweep confirmed (256 ≤ 512
  overall). At 990 chunks the pre-pass saves no real time, but it made an honest prediction
  we could check — which is the point of the drill.
- **k behaves exactly as theory says.** Bigger k monotonically lifts hit-rate at every size
  (a bigger net catches more) while MRR barely moves — the extra hits land *deep*, they
  don't pull the first relevant result up. Cheap axis, locked first, as ADR-004 §2 orders.

## What didn't / surprises   (written generously — this is the expensive lesson)

**1. The core hypothesis was WRONG. Smaller is not better — 512 wins overall.**
The step-10 handoff predicted smaller chunks would raise the 0.278 baseline by cutting the
~30× dilution. They didn't. At k=5, overall hit-rate is **512 (0.333) > 256 (0.286) > 1024
(0.238)**. Chunk size is a **precision/recall trade, not a monotonic dial** you turn down for
free. The dilution story was real but incomplete: shrinking the chunk also shrinks *every
competitor's* signal and multiplies the number of confusable neighbors, so the true chunk
doesn't automatically rise.

**2. Exact and paraphrase queries want OPPOSITE chunk sizes.** This is the headline.
- **Exact (pinpoint) queries favor mid chunks:** exact hit@5 = **512 (0.625) ≥ 256 (0.500) ≫
  1024 (0.125)**.
- **Paraphrase (topical) queries favor LARGER chunks:** paraphrase hit = **1024 best**
  (0.308 @k5, and a decisive **0.538 @k10** vs 0.308 for 256/512). A bigger chunk carries
  more surrounding context, so a thematic query ("what advice does Polonius give about
  borrowing?") matches the broad passage even with no shared words.

  This is the classic chunking trade-off reproduced on a 990-chunk toy corpus: **small
  chunks = pinpoint precision; large chunks = topical recall.** There is no single best
  size — there's a best size *per query type*, which is the argument for hybrid retrieval
  and/or multi-resolution indexing later.

**3. The bge-512 ceiling makes 1024 a broken arm — and taught the sharpest lesson.**
bge-small's max sequence is **512 tokens**, so at `chunk_size=1024`, **433/444 chunks exceed
it and are tail-truncated at embed time.** The chunk *text* is stored whole (so the quote
still resolves, `|R|=1`), but the *vector* only encodes the first ~512 tokens. Consequences:
- **Resolution ≠ retrieval.** A quote in the back half of a 1024-token chunk is found by the
  golden resolver (text contains it) but is **invisible to the embedding** (truncated out),
  so it can never rank. That gap is exactly why exact recall at 1024 **craters to 0.125.**
- **1024 isn't "bigger chunks" — it's "512-token chunks covering half the corpus."** Only
  ~the first 512 tokens of each 1024-token window get embedded, so roughly **half the
  corpus's tokens are never vectorized.** Exact queries (need the specific line, maybe in the
  dropped half) collapse; paraphrase queries (need any on-topic passage, and topics recur)
  survive on the embedded halves and even benefit from the coarser granularity.
- Lesson locked: **never set chunk_size above the embedding model's max sequence.** The
  chunking-lab skill said so; now we've *seen* the failure mode instead of trusting the note.

**4. 256 is "rank-1 or nothing."** At 256, MRR *equals* hit-rate at k=3 and k=5 (0.286) —
because every relevant chunk it surfaces lands at **rank 1** (confirmed in the score dump:
all `relhit rank = 1` at 256). Smaller chunks are razor-precise *when* they hit, but surface
fewer answers; 512 trades that razor for slightly more coverage at deeper ranks (ranks 2, 5).

**5. Dense similarity scores can't be thresholded — the top-1 *wrong* hit outscores the
relevant one.** The intuition dump is blunt: at 512, mean cosine of **relevant** hits =
**0.646**, mean cosine of the **top-1 when it's wrong** = **0.670**. The wrong hits score
*higher*. (e.g. "struggle for existence" pulls a wrong top-1 at 0.762, while a correct hit
elsewhere sits at 0.746.) At 256 relevant edges ahead (0.712 vs 0.674) but the ranges overlap
completely (relevant 0.66–0.81, wrong 0.60–0.78). **No global cosine cutoff separates
relevant from irrelevant** — dense scores are similarity, not calibrated relevance. This is
the concrete, measured motivation for a **cross-encoder reranker** (re-scores the query–doc
pair jointly) rather than a naive score threshold.

## Numbers   (hit-rate@k unless noted; user=root, full corpus)

Pre-flight: `|R|=1` for all 21 quotes at 256/512/1024. Chunk counts: **2102 @256, 990 @512,
444 @1024** (433/444 over the bge-512 limit).

| size | k  | overall hit | overall MRR | overall nDCG | exact hit (n=8) | paraphrase hit (n=13) |
|-----:|---:|------------:|------------:|-------------:|----------------:|----------------------:|
| 256  | 3  | 0.286 | 0.286 | 0.286 | 0.500 | 0.154 |
| 256  | 5  | 0.286 | 0.286 | 0.286 | 0.500 | 0.154 |
| 256  | 10 | 0.381 | 0.300 | 0.318 | 0.500 | 0.308 |
| **512** | 3 | 0.286 | 0.214 | 0.233 | **0.625** | 0.077 |
| **512** | **5** | **0.333** | 0.224 | 0.251 | **0.625** | 0.154 |
| **512** | 10 | 0.429 | 0.240 | 0.285 | **0.625** | 0.308 |
| 1024 | 3  | 0.143 | 0.143 | 0.143 | 0.125 | 0.154 |
| 1024 | 5  | 0.238 | 0.167 | 0.184 | 0.125 | 0.308 |
| 1024 | 10 | 0.381 | 0.183 | 0.227 | 0.125 | **0.538** |

- **Best overall (k=5):** 512 @ 0.333. **Best exact:** 512 @ 0.625. **Best paraphrase:** 1024
  (0.308 @k5, 0.538 @k10).
- Score intuition (k=5): relevant-hit mean vs wrong-top-1 mean — **256:** 0.712 vs 0.674;
  **512:** 0.646 vs 0.670 (inverted → no clean threshold).
- Baseline moved 0.278 (18 rows) → 0.333 (21 rows) purely from adding 3 exact rows; the sweep
  compares all sizes on the same 21-row set, so it stays apples-to-apples.

## Open follow-ups

- **512 stays the Phase-1 default** — best overall and best exact, and the only size that
  respects the bge-512 ceiling. No change to the locked decision; now *earned* with data.
- **Hybrid / BM25** is the obvious next lever: exact-term queries that dense retrieval buries
  (e.g. "You know my methods" misses at every size) are exactly what a lexical index nails.
- **Reranking** is motivated directly by finding #5 (scores can't be thresholded). A
  cross-encoder over the top-k is the Phase-2 candidate.
- **Multi-resolution / query-routing:** since exact wants ~512 and paraphrase wants larger,
  a router or a dual-index could pick per query. Interesting, out of Phase-1 scope.
- **Overlap** was untouched (0 throughout). A boundary-straddle experiment is the natural
  sequel if a specific answer keeps getting split.
- The honest scale caveat: at 990 chunks the sample pre-pass saves no real compute — it's a
  *method* demonstration. At enterprise scale, where a re-embed is hours of GPU, that cheap
  directional read is the whole game (ADR-004 §2).

## Linked context

- `docs/decisions/ADR-004-eval-methodology.md` — source-anchored golden set (survives the
  re-chunk) + cost-tiered sweeps (§2, the procedure this experiment ran).
- `docs/spec-phase-1.md` — Part H (eval), Part I (poke experiments).
- `docs/explainers/evaluation.md` — the four metrics; `docs/explainers/chunking.md` — the size knob.
- `.agents/skills/chunking-lab/SKILL.md` — the A/B loop + the "≤ model max sequence" gotcha
  this experiment made concrete.
- `src/rag_exp/eval.py` — `run_eval` (per-tier means, `chunk_size`/`k`/`retriever` params);
  `src/rag_exp/index.py` — `build_index(chunk_size=…, store=…)` for the per-size re-embeds.
