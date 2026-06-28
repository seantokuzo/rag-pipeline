---
paths:
  - "src/rag_exp/security.py"
  - "src/rag_exp/retrieve.py"
---

# ★ Access-control invariant (full detail: docs/SECURITY.md)

You are touching the security boundary. The entitlement filter MUST be:
- **server-side** — built in `security.py` from the trusted entitlements map, never from caller input;
- **pre-retrieval** — passed INTO the vector query (`where=` / `filter=`), never post-filtered;
- **un-overridable** — AND-composed with any caller filter so callers can only narrow, never widen;
- **fail-closed** — unknown / empty entitlements are denied *before the data layer*: `entitlement_filter` raises `NoEntitlementsError` (never an open filter; never an empty `$in: []`, which chromadb rejects).

`retrieve()` must refuse to query without a `product_id` constraint. After changing either file, spawn the `access-control-reviewer` subagent and confirm the cross-tenant leak test still passes.
