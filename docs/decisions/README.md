# Architecture Decision Records (ADRs)

> One ADR = one **locked** architectural decision, captured with the alternatives we weighed and why we chose what we did. The point: future-you (or a fresh session) understanding *why*, six months on, without re-deriving it.

---

## When to write one

Write an ADR for a **real, hard-to-reverse choice with trade-offs** — the kind you'd otherwise re-argue later:
- chunking strategy
- embedding model
- vector store
- retrieval approach (dense / hybrid / rerank)
- the access-control model

Heuristic: if swapping the decision later would mean meaningful rework, it earns an ADR.

## When NOT to

- **It's still in flux.** Decisions you're actively weighing live in `docs/STATE.md` (or `PLANNING.md` → Open Questions) until they *lock*. An ADR is the gravestone, not the debate.
- **It's reversible or trivial.** A config default you'll flip during a sweep is not an ADR.

> If unsure, lean toward **NOT** writing one. Premature ADRs are noise; missing ones become folklore. Write it when the decision stops moving.

## Solo-lab ceremony (relaxed)

The textbook rule is *append-only*: never edit an accepted ADR, only supersede it. Here it's just the two of us, so **editing an existing ADR is fine** — fix a typo, sharpen the context. But for an actual **reversal** (we changed our minds), prefer a **new ADR** that supersedes the old one: set `Status: Superseded by ADR-MMM` on the old, `Supersedes: ADR-XXX` on the new. The trail of *why we changed* is the valuable part — don't overwrite it.

## Current ADRs

| # | Title | Status |
|---|-------|--------|
| [001](ADR-001-phase1-local-stack.md) | Phase 1 local stack — Chroma + bge-small + uv | Accepted |
| [002](ADR-002-pooled-access-control.md) | Pooled access-control model — shared collection + metadata pre-filter | Accepted |
| [003](ADR-003-intel-mac-compat-caps.md) | Intel-Mac (x86_64) dependency compatibility caps | Accepted |
| [004](ADR-004-eval-methodology.md) | Evaluation methodology — source-anchored golden set + cost-tiered sweeps | Accepted |
| [005](ADR-005-ingest-loader-seam.md) | Ingestion loader seam for multi-format sources (Phase 1.5) | Proposed |

New ADR? Copy [`ADR-template.md`](ADR-template.md) and bump the number.
