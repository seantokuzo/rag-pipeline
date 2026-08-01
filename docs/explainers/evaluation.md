# Evaluation — how it works

> Part of the [RAG explainer series](./README.md). Understanding-oriented: *how the concept works*, not the build steps. Step-agnostic (organized by process, not build order).

**Where it sits:** everything else in the pipeline *produces* retrieval — `ingest → chunk → embed → store →` [`retrieve`](./retrieval.md). Evaluation *judges* it. It's the only stage that doesn't make the product better by itself; it makes every **other** stage's change **measurable**. Without it, "I changed the chunk size and it feels better" is vibes. With it, it's a number that moved. (Contract: spec Part H; method: ADR-004; code: `src/rag_exp/eval.py` + `eval/golden.json`.)

## The one question eval answers

> **Did we fetch the right chunks?**

That's it. Not "was the answer good" (there's no LLM here — generation is Phase 2+), not "was it safe" (that's the [cross-tenant leak test](./access-control.md), a different question with a different answer shape). Just: for a question whose answer we *know* lives in a particular passage, did that passage come back — and did it come back **near the top**?

Everything below is machinery for turning that question into four numbers.

## Part 1 — The golden set: a hand-written answer key

You cannot measure retrieval without knowing, in advance, what the right answer is. So we hand-author one: a list of queries, each paired with the passage that *should* answer it. That's the **golden set** (`eval/golden.json`), and it's the part with no shortcut — a human reads the books and decides what "relevant" means. Authoring it *is* the learning.

One row:

```json
{
  "q": "how does Holmes describe Irene Adler?",
  "user": "root",
  "product_id": "detective",
  "source": "adventures-of-sherlock-holmes",
  "relevant_quote": "In his eyes she eclipses and predominates the whole of her sex"
}
```

Read it as a sentence: *"When user `root` asks `q`, a chunk is relevant if it contains `relevant_quote` — and we expect that text to live in `product_id`/`source`."*

### Why the answer key points at a **quote**, not a chunk id

This is the load-bearing design decision, and the obvious approach is the wrong one. The tempting version pins each query to the chunk that answers it:

```json
{"q": "...", "relevant_ids": ["detective:adventures-of-sherlock-holmes:12"]}   // ✗ WRONG
```

That reads fine — until you remember what a chunk id *is*. `product_id:source:ordinal` — the **12th slice at the current chunk size**. Change `chunk_size` from 512 to 256 and every document gets re-sliced: chunk `:12` is now a completely different piece of text, somewhere else in the book. The answer key still *looks* valid (the ids all resolve!) but every judgment now points at the wrong content, silently.

Which is fatal, because **the chunk-size sweep is the headline experiment this harness exists to run** (spec Part I). An answer key keyed to chunk ids cannot survive the very change it's meant to measure. You'd have to re-label 20 queries by hand for every configuration — tedious, and worse, your labeling drifts between passes, so the "improvement" you measure is partly you.

So the anchor is the **source text itself** — a verbatim quote from the book:

```python
" ".join(quote.split()) in " ".join(chunk.text.split())     # ✓ relevance, computed live
```

The quote is a property of *Hamlet*, not of a chunking config. Re-slice the corpus however you like; the quote still sits in exactly one (or a few) of the new chunks, and the harness **finds out at eval time which ones** by scanning. Author once, valid forever. That's ADR-004 §1.

> **The anchor rule:** relevance is anchored to **content**, which is stable. Chunk ids are anchored to **configuration**, which is exactly what we're changing.

Chunk ids don't disappear — they're still the store's primary key and still stable *within* a config (that's what keeps re-indexing idempotent). They're just the wrong thing to key an *experiment* to. Two different jobs.

### The whitespace normalization, and what it does *not* fix

`" ".join(s.split())` collapses every run of whitespace to a single space. That exists because Gutenberg text is **hard-wrapped at ~72 columns**, so a one-sentence quote almost always has a newline through the middle of it:

```
To Sherlock Holmes she is always _the_ woman. I have seldom heard him
mention her under any other name. In his eyes she eclipses and
predominates the whole of her sex.
```

A quote you'd write as `"In his eyes she eclipses and predominates the whole of her sex"` is stored as `"...eclipses and\npredominates the whole..."`. Normalizing both sides makes the line wrap invisible. It does **not** make anything *else* invisible:

- **Markup survives.** That first line is literally `she is always _the_ woman` — Gutenberg's underscores mark italics. A quote typed from memory as `"she is always THE woman"` matches **nothing**. (ADR-004's own illustrative example has this bug. It's illustrative in more ways than intended.)
- **Case survives.** The match is exact-substring, case-sensitive.
- **Punctuation survives.** Smart quotes, em-dashes, and `[Sidenote:]` markers are all real characters in the text.

Hence the authoring rule: **lift quotes out of the file, never out of your head** — and let the harness prove each one resolves. A row that matches zero chunks is a broken row, and the harness treats it as a **hard error**, not a zero score. A silent zero would read as "retrieval failed" when the truth is "your answer key is typo'd" — the exact silent-corpus-failure anti-pattern this project bans.

### The authoring rules that make quotes behave

- **Short and mid-passage.** The quote must fit *inside one chunk* even at the smallest size we'll ever sweep (256 tokens). A quote straddling a chunk boundary is in neither chunk, and reads as a miss that isn't real. A distinctive clause or sentence, taken from the middle of a paragraph, is the sweet spot.
- **Distinctive.** Distinctive enough that it appears in one place — `"the woman"` would match half the book.
- **`user: "root"`.** Quality is measured on the **full corpus**, so entitlements can't confound the number. If you evaluated `alice` (detective-only) on a Hamlet query, you'd score a 0 that is *correct behavior*, not a retrieval failure. Quality and safety are separate questions and mixing them corrupts both. (Safety is measured on the *restricted* users — that's the leak test.)
- **~5–10 per product.** Enough to average out a single unlucky query; small enough to hand-author honestly.

Note we still route through the guarded `Retriever.retrieve` path, not a bypass — `root`'s entitlement filter is `$in: [detective, shakespeare, science]`, which matches everything. So the number describes **the code that actually ships**, filter and all. A harness that measures a path nobody uses measures nothing.

## Part 2 — Resolution: quote → the relevant set, computed live

Because the answer key stores a quote, every eval run has an extra step no id-based harness needs. Before scoring anything, for each golden row:

> Scan **every chunk in the live corpus** and collect the ids of those containing the quote (whitespace-normalized). That set — call it **R** — is the relevant set *for this chunking configuration*.

That's the whole trick. `R` is **recomputed on every run**, against whatever chunking is live, from an answer key that never changed. Re-chunk at 256 and `R` is simply recomputed against the new slices — maybe a different id, maybe two ids instead of one. The judgment ("this passage answers this question") is untouched.

From there, the metric math is **exactly** what an id-based harness does — you have a ranked list and a relevant set. The quote→`R` resolution is the only extra layer.

Two consequences worth internalizing:

- **`|R|` is usually 1** at our settings (short quote, 512-token chunks, **zero overlap**) — the quote lands in exactly one slice. Turn overlap on and the same quote can appear in 2+ adjacent chunks, and `|R|` grows. This is why `recall@k` and `hit-rate@k` are the same number for us today (below).
- **`|R|` is knowable at all** only because we scan the whole corpus. You cannot compute recall from the retrieved results alone — recall's denominator is "how many relevant chunks *exist*," which by definition includes the ones you failed to retrieve.

## Part 3 — The four metrics

Setup for one query. `R` = the relevant set from Part 2. The retriever returns a **ranked** list of `k` hits, best first. For each position `i` (1-indexed):

```
rel(i) = 1 if hits[i].id ∈ R else 0
```

Everything below is a different way of squeezing that little 0/1 vector into one number. They differ in **what they care about**, and the useful ones disagree with each other.

### hit-rate@k — "did retrieval work *at all*?"

```
hit_rate@k = 1 if any rel(i) == 1 else 0
```

The coarsest possible question, and binary per query. Averaged over the set, it's **the fraction of questions where something useful showed up**. It cannot tell rank 1 from rank 5. That bluntness is the point: it's the smoke alarm. If mean hit-rate is 0.4, nothing else matters yet — retrieval is *broken*, and MRR's third decimal is a distraction.

### recall@k — "how much of the answer did we get?"

```
recall@k = |{i : rel(i) == 1}| / |R|
```

Coverage: of all the chunks that *should* have come back, what fraction did? Also rank-blind.

Two honest caveats:
- **When `|R| = 1`, recall@k is *identically* hit-rate@k** — 1/1 or 0/1. At our current settings (short quotes, no overlap) that's most rows, so the two columns will read the same. That's not a bug and not redundancy: they diverge the moment `|R| > 1` (overlap on, or a passage quoted twice), and the sweep will do exactly that. Keeping both means the report doesn't need re-plumbing when it happens.
- **`k` caps recall.** If `|R| = 8` and `k = 5`, perfect retrieval scores 0.625. Compare recall only across runs with the same `k` — a "gain" from raising `k` is often just a looser ceiling.

### MRR — "is the best answer near the *top*?"

```
RR = 1 / (rank of the first relevant hit),  or 0 if none in top-k
MRR = mean(RR) over the golden set
```

The first rank-**aware** metric. Rank 1 → 1.0, rank 2 → 0.5, rank 3 → 0.33, rank 5 → 0.2. The drop-off is steep on purpose: it models a reader who scans from the top and stops at the first thing that works, so position 1 is worth double position 2. It ignores everything after the first hit.

This is where "retrieval works" and "retrieval is *good*" separate. A system with hit-rate 1.0 and MRR 0.3 finds the answer **every time** and **buries it every time**. Rule of thumb: **MRR ≥ 0.6 feels snappy** (the answer is usually in the top 1–2).

### nDCG@k — "how good is the *whole ranking*?"

The most complete one, and the only one that needs unpacking. Three layers:

**1. Gain, discounted by position (DCG).** Every relevant hit earns credit, but credit shrinks the further down it sits — logarithmically, not linearly, because the difference between rank 1 and 2 matters far more than 9 vs 10:

```
DCG@k = Σ(i=1..k)  rel(i) / log2(i + 1)
```

Rank 1 pays `1/log2(2) = 1.0`; rank 2 pays `1/log2(3) = 0.63`; rank 5 pays `1/log2(6) = 0.39`.

**2. The ideal (IDCG).** DCG alone isn't comparable across queries — a query with 3 relevant chunks can out-earn one with 1 without being better ranked. So compute the score a *perfect* ranking would get: all relevant chunks packed into the top slots.

```
IDCG@k = Σ(i=1..min(|R|, k))  1 / log2(i + 1)
```

**3. Normalize.** Divide actual by ideal:

```
nDCG@k = DCG@k / IDCG@k        → 0.0 … 1.0, where 1.0 = perfect ranking
```

Now every query is on the same 0–1 scale and averaging is meaningful — that's the "n". With **binary** relevance and `|R| = 1` it collapses to a tidy `1 / log2(rank + 1)`: a gentler MRR (rank 2 = 0.63 rather than 0.5). Its real power — **graded** relevance ("this chunk is *perfect*, that one is *related*") — is unused here, because quote-containment is yes/no. That's ADR-004's accepted trade-off, and the documented upgrade path (span/offset anchoring) is what would unlock it.

### Worked example — why you keep all four

`|R| = 1`, `k = 5`, and the one relevant chunk comes back at **rank 3**:

| Metric | Value | What it's saying |
|---|---|---|
| hit-rate@5 | `1` | "Found it." |
| recall@5 | `1/1 = 1.0` | "Found all of it." |
| MRR | `1/3 = 0.33` | "…but you had to scan past two wrong ones." |
| nDCG@5 | `(1/log2(4)) / (1/log2(2)) = 0.5/1.0 = ` **`0.5`** | "The ranking is half as good as it could be." |

Two metrics say *perfect*, two say *mediocre* — and both are right. Recall answers "is it there," MRR/nDCG answer "is it **first**." A single number would have hidden half the story; this is why the report prints all four.

### And the mean over the set

Each metric is computed per query, then **averaged across the golden set**. Those four means are the harness's output — and the regression gate.

> Not on the list: **precision@k**. With `|R| = 1` and `k = 5`, a *perfect* system scores 0.2 — the metric mostly measures `k`, not quality. It earns its place when queries have many relevant docs.

### Slicing the mean: the `exact` / `paraphrase` tiers

A single mean over the whole set is a **blunt instrument** — it can sit flat while two halves of your corpus move in opposite directions and cancel out. So every golden row carries a **`tier`** tag describing the *style* of the question:

| tier | what it means | example |
|---|---|---|
| `exact` | the query shares verbatim lexical overlap with the quote | *"You see, but you do not observe"* |
| `paraphrase` | a natural-language question with little or no shared wording | *"what advice does Polonius give about borrowing money?"* |

`run_eval` groups the per-query rows by tier and reports `EvalReport.overall` **plus** `EvalReport.by_tier` — same four metrics, computed by one pure, unit-tested `aggregate()` (an empty tier yields zeros, not a crash). Rows with no `tier` key fall into `"untagged"`.

Why bother: **this split is where the physics shows up.** In the step-11 sweep the overall mean said "512 is best, mildly." The tier split said something far sharper — **`exact` and `paraphrase` queries want opposite chunk sizes** (exact peaked at 512, paraphrase at 1024), a conclusion the aggregate number completely hid. It also maps directly onto a design decision: `exact` misses are what a **lexical/BM25 index** fixes (hybrid retrieval), `paraphrase` misses are what a **better embedding model or bigger context** fixes. Different failures, different levers — you can't tell them apart from one number.

> The general lesson, well beyond this project: **report the mean, then immediately break it apart along whatever dimension you expect to behave differently.** The aggregate is the headline; the slice is the finding.

## Part 4 — Using it: the gate

The numbers are close to meaningless in absolute terms. "nDCG 0.72" — good? No idea. There's no external baseline, our corpus is 990 chunks of three books, and the golden set is one person's judgment.

They're **entirely** meaningful as a **delta**:

1. Run the harness → record the four means. That's the **baseline**.
2. Change one thing — chunk size, the embedding model, `k`, a reranker.
3. Re-run. **Compare.**

A drop = investigate *before* committing. A rise = you learned something real. This is the discipline that makes ADR-004's cost-tiered sweeps (spec Part I) possible at all: `chunk_size ∈ {256, 512, 1024} × k ∈ {3, 5, 10}` is only a meaningful experiment because the answer key survives every cell of that matrix and the metric math never moves.

**One variable per comparison**, and hold `k` fixed when comparing recall. Per-query output matters as much as the means: a mean that slips from 0.78 to 0.71 tells you *something* broke; the per-query column tells you *which question* broke, which is the only actionable form of the news.

**⚠️ The answer key is also a variable.** Step 11 added three rows to the golden set and the headline hit-rate "improved" 0.278 → 0.333 — **entirely from the new rows, before a single setting changed.** A baseline is only comparable against runs scored on the *same* golden set. When you grow the answer key, you've reset the baseline: re-score the incumbent config and record the new number. (Current baseline: **@512 / k=5 over the 21-row set — overall hit-rate 0.333 · MRR 0.224 · nDCG 0.251; exact 0.625 · paraphrase 0.154.**)

**And the harness has a footgun worth knowing.** `run_eval` re-chunks the corpus from source to resolve quotes → chunk ids, so its `chunk_size`/`chunk_overlap` **must match the size the index it's querying was built at.** Mismatch them and the re-chunked ids don't line up with the indexed ids — *every* query scores ~0. It looks exactly like catastrophically broken retrieval; it's a config typo. Build at 256 → score with `chunk_size=256`. Never mix.

## Quality is not safety

The most important boundary in this doc:

| | **Eval harness** (this) | **Cross-tenant leak test** (`tests/`) |
|---|---|---|
| Question | Did we fetch the *right* chunks? | Did we fetch a *forbidden* chunk? |
| User | `root` (full corpus) | the restricted users (`alice`, `bob`, `carol`, `mallory`) |
| Answer shape | four means in [0, 1] — a **gradient** | pass/fail — a **binary** |
| On a bad result | investigate, tune, iterate | **stop** — it's a breach |
| Home | `src/rag_exp/eval.py` (a script you run) | `pytest` (a gate that blocks) |

Retrieval quality is a **dial**; retrieval safety is a **switch**. An nDCG of 0.6 is a Tuesday. One leaked `product_id` is the whole project's failure condition. That's why safety is a *test* (mandatory, green or bust) and quality is a *harness* (a number you compare) — and why they never share a run. Both must hold. Neither substitutes for the other.

## What this harness deliberately isn't

- **No LLM judge, no generation scoring.** There's no generator in Phase 1. This measures the **retriever** — which is the right layer anyway: a RAG answer can't be better than the chunks handed to it, so retrieval quality caps everything downstream.
- **No framework** (ragas, TruLens, …). Four metrics, ~50 lines of arithmetic. Hand-rolling them *is* the lesson; a framework would hide exactly the math worth understanding.
- **No graded relevance.** Binary, by ADR-004's trade-off. The upgrade path (span anchoring → partial overlap → graded nDCG) is written down, not lost.
- **Not statistically significant.** ~20 queries over 3 books. It catches "we broke retrieval" and "512 clearly beats 256." It does not resolve a 0.01 difference — don't read the third decimal.

## Control flow, end to end

```
   eval/golden.json  ──►  for each row {q, user, product_id, source, relevant_quote}
                                │
   corpus (live chunks) ──► resolve: chunks whose text CONTAINS the quote  ──►  R (relevant ids)
                                │                    └─ R empty? HARD ERROR — the row is broken
                                ▼
   Retriever.retrieve(user="root", q, k)  ──►  ranked list[Hit]      ← the real, guarded path
                                ▼
   rel(i) = 1 if hits[i].id ∈ R else 0        (the 0/1 vector, in rank order)
                                ▼
   hit-rate@k · recall@k · MRR · nDCG@k       (per query)
                                ▼
   mean over the golden set  ──►  4 numbers  ──►  compare against the last run  ──► the gate
```

## TL;DR

Evaluation turns "retrieval feels better" into a number. A hand-authored **golden set** pairs each query with a **verbatim quote** from the source — never a chunk id, because ids are an artifact of the chunk size we're trying to *sweep*, and an id-keyed answer key silently rots the moment you re-chunk (ADR-004 §1). At run time the harness **resolves** each quote to whatever live chunks contain it (whitespace-normalized — which absorbs Gutenberg's line wraps but **not** its `_italics_` markup, so lift quotes from the file, never from memory), fires the query through the **real guarded `Retriever`** as `root` (full corpus, so entitlements don't confound quality), and scores the ranked hits four ways: **hit-rate** (did anything land?), **recall** (how much landed?), **MRR** (was the first hit near the top?), **nDCG** (how good is the ranking overall?). Rank-blind vs rank-aware — they disagree, and that disagreement is the signal. Mean them over the set; the absolute values mean little, the **delta between runs** is the whole point, and it's what makes the chunk-size sweep a real experiment. And keep it strictly apart from the [leak test](./access-control.md): quality is a **dial** you tune, safety is a **switch** that must never flip.
