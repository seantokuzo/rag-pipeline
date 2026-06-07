# History — Retrospectives & Experiment Log

> The learning record of the lab. Durable write-ups of **what worked, what didn't, and what surprised us** — per phase and per experiment. RAG is empirical; this is where the evidence lives so future-you doesn't re-run the same sweep to re-learn the same thing.

---

## What goes here

- **Phase closes** — when a phase wraps, a retrospective: what shipped, what worked, what bit us, open follow-ups.
- **Experiments** — any "poke" with a result worth keeping: chunk-size sweeps, exact-vs-paraphrase query tests, eval-metric comparisons. This is where **`chunking-lab`** and **`rag-eval-harness`** runs get written up — the numbers *and* what they mean.

If you learned something, it goes here. Especially the surprises — those are the expensive lessons, and the whole reason this lab exists.

## Filenames

| Kind | Pattern | Example |
|---|---|---|
| Phase close | `P-<n>-<slug>.md` | `P-1-local-pipeline.md` |
| Experiment | `EXP-<slug>.md` | `EXP-chunk-size-sweep.md` |

## Writing one

Copy [`PHASE-template.md`](PHASE-template.md) — it works for both a phase and an experiment. Write the "what didn't / surprises" section **generously**; that's the part future-you actually comes back for.
