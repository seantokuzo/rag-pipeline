# ADR-002: Pooled access-control model

**Status:** Accepted
**Date:** 2026-06-06
**Supersedes:** none
**Superseded by:** none

## Context

The core lesson of this lab is to **demonstrate a licensing-based content leak, then stop it** with a server-side, pre-retrieval filter (see `docs/SECURITY.md`). To have a leak worth stopping, we need a multi-tenant isolation model: three "products" (licensed Gutenberg collections), users entitled to a subset, and a retrieval path that must never return un-entitled content.

The isolation model decides *what the lesson even is*, so it's an explicit, locked decision.

## Decision

We will use the **POOLED model**: **one shared Chroma collection** for all products, with tenant isolation enforced by a **server-side `product_id` metadata pre-filter** — built from the trusted entitlements map and applied *inside* the vector query (per `docs/SECURITY.md` §3–§5). Not per-tenant indexes.

We choose pooled because **the filter is the lesson**: the set of retrievable chunks is the intersection of "similar to the query" *and* "the user is entitled to it," computed before any result leaves the store.

## Alternatives considered

- **SILO — a separate index/collection per product.** Stronger *physical* isolation: un-entitled data sits in a different index the query never touches. But it has more moving parts, costs more, and — critically — **it hides the filter lesson.** If isolation comes free from physical separation, there's no metadata filter to get right and nothing to demonstrate. Rejected as the teaching model; kept as the documented escalation path for regulated / high-value tenants.
- **POST-filtering — retrieve top-k across everything, then drop un-entitled hits in app code.** Rejected outright: un-entitled data has already **left the store** into the application layer (the very leak we're preventing), and dropping after the fact silently loses authorized hits (an entitled chunk gets crowded out of top-k by un-entitled neighbors, which are then discarded → fewer than k results, recall loss). It's an anti-pattern, not a real alternative.

## Consequences

### Positive
- Simplest possible setup — one collection, one filter.
- **The filter *is* the lesson.** Pooled isolation lives or dies by the metadata pre-filter being correct, so the project's centerpiece is exactly the thing under study.
- Maps 1:1 onto the production pooled multi-tenant RAG pattern, and ports cleanly to Phase 2 (the same invariant as an Azure `filter` + `vectorFilterMode: preFilter`).

### Negative
- **Correctness depends entirely on the filter.** One missed filter path = full leak. This makes the **cross-tenant leak test mandatory** (SECURITY.md §6) — a pooled model without that test is unproven, not safe.
- **ANN recall-hole caveat at scale:** very selective metadata filters combined with HNSW graph traversal can fail to reach enough matching nodes. Negligible at learning-lab corpus size, but it's a real reason production sometimes prefers silos for highly selective tenants.

### Neutral
- **Silo remains the escalation path.** If a future tenant needs physical isolation, we'd move *that* tenant to its own index without changing the pooled model for everyone else.

## Links
- `docs/SECURITY.md` — threat model, the invariant, pool-vs-silo (§4), verification (§6), recall-hole caveat.
- `docs/spec-phase-1.md` — Part E/F (security + retrieval); locked decisions #5–#6.
- ADR-001 — the local stack this model runs on.
