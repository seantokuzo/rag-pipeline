# RAG explainers

Plain-English **"how does this actually work"** docs — one per concept/process in the pipeline. Understanding-oriented and **step-agnostic**: organized by *what it is* (chunking, embedding, retrieval…), not by build-order step, so they stay relevant as the project moves.

They complement — don't duplicate — the other docs:

| Doc type | Question it answers | Home |
|---|---|---|
| **Explainer** (here) | *How does this concept work?* | `docs/explainers/` |
| Spec | *What are we building, exactly?* | `docs/spec-*.md` |
| ADR | *Why did we choose X?* | `docs/decisions/` |
| Threat model | *How could it leak — what stops it?* | `docs/SECURITY.md` |
| State | *Where are we right now?* | `docs/STATE.md` |
| Retrospective | *What did we learn doing it?* | `docs/history/` |

## The process

Before each handoff, the human asks **"how does the next step work?"** → Claude **explains in-session** *and* **writes/updates the matching explainer here**, at the same time. Tracked in git (not gitignored), so they're readable straight from GitHub.

## Index

- [chunking](./chunking.md) — slicing documents into embeddable, security-tagged pieces.
- [embedding](./embedding.md) — turning chunks into 384-d vectors; the query/document parity rule.
- [vector-store & indexing](./vector-store.md) — making vectors searchable; cosine space + the `where` pre-filter seam.
- [access control & filtering](./access-control.md) — turning a `user_id` into the server-side entitlement pre-filter; the security boundary.
- [retrieval](./retrieval.md) — the read path: query embedding parity, pre-filtered nearest-k, and the `Hit` score.
- [evaluation](./evaluation.md) — judging retrieval: the source-anchored golden set and the four metrics (hit-rate / recall / MRR / nDCG).
