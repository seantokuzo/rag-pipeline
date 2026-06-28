# RAG Access Control — Security & Threat Model

> The heart of this project. Authorization in RAG is a **server-side, pre-retrieval metadata filter** sourced from a trusted entitlements map, applied **inside** the vector query, and **structurally un-overridable** by the caller. Un-entitled content is never retrieved, so the (optional) synthesis step can never see it.

**Status:** Design of record. **Last Updated:** 2026-06-27 (locked empty-entitlement handling — §5 option (a): deny before the data layer + mock upsell).

---

## 1. Overview

The product simulates a multi-tenant RAG service where each "product" is licensed content (a Project Gutenberg collection). A user entitled to Product A must never receive chunks from Products B or C — not in results, not in scores, not anywhere downstream.

**The one rule (the invariant):**

> Every retrieval query carries an authorization filter that is (1) **built server-side** from a **trusted entitlements map**, (2) applied **inside the vector search** (pre-filter), and (3) **impossible for the caller to weaken or remove**. The set of retrievable chunks is the intersection of "similar to the query" and "the user is entitled to it" — computed *before* any results leave the store.

Everything in this doc exists to define, enforce, and verify that rule.

### Layered defense

| Layer | What it prevents | Where it lives |
|---|---|---|
| Metadata at ingestion | Unlabeled chunks that can't be filtered | `ingest.py` — stamp `product_id` on every chunk |
| Server-side filter construction | Client-controlled authorization | `security.py` — builds the filter from the trusted map |
| In-query pre-filtering | Data leaking to the app/synthesis layer | `retrieve.py` — filter passed *into* `store.query()` |
| Defensive assertion | A code path that forgets the filter | `retrieve.py` — refuse to query if no `product_id` constraint present |
| Cross-tenant test | Regressions | `tests/` — assert zero unauthorized `product_id` ever returned |

No single layer is trusted alone; the test is what proves the rest.

---

## 2. Threat Model

### Assets
The licensed text of each product. Leakage = a user obtaining chunks from a product they are not entitled to.

### Actors
- **Legitimate user** — entitled to a subset of products; should retrieve only those.
- **Curious / over-reaching user** — tries to retrieve everything, or another product's content, e.g. by crafting queries or (if the API allowed it) by supplying their own filter.
- **Malicious caller** — actively attempts to bypass authorization (inject filter params, omit the filter, manipulate `user_id`).

### Threats

| # | Threat | Vector | Impact | Mitigation |
|---|--------|--------|--------|------------|
| T1 | **No filter applied** | A query path that forgets to pass the entitlement filter | Full leak — every product returned | Filter built centrally in `retrieve.py`; defensive assertion refuses unfiltered queries |
| T2 | **Client-supplied filter** | Caller passes `product_id` / filter in the request | Caller grants themselves access | Filter is derived server-side from `user_id` → trusted map; request filters are AND-composed *under* it, never replace it |
| T3 | **Post-filtering** | Retrieve first, drop un-entitled results in app code | Data already left the store; authorized hits silently dropped (recall loss); leak risk if drop is buggy | Always pre-filter (filter *inside* the query) |
| T4 | **Unlabeled chunks** | Ingestion misses `product_id` on some chunks | Those chunks bypass every filter | Stamp metadata at ingestion; treat missing `product_id` as a hard error |
| T5 | **`user_id` spoofing** | Caller claims another user's identity | Inherits their entitlements | Out of scope for the lab (we trust the resolved identity), but documented: in production `user_id` comes from authenticated session, never request body |
| T6 | **Secret leakage** | API keys committed / logged (Phase 2 Azure) | Credential compromise | `.env` git-ignored; `pre-tool-security` hook blocks reads/writes of secret files; never log keys |
| T7 | **Prompt injection via retrieved text** | Untrusted corpus text instructs a future LLM step | Only relevant once we add generation | Documented now; treat retrieved content as data, never instructions, when synthesis lands |

### The leak we demonstrate (the lesson)
Run the **same** query two ways for a user entitled to only Product A:
- **(a) No filter** → top-k includes chunks from B and C. *This is the leak.*
- **(b) Server-side filter** → top-k contains only Product A. *This is the fix.*

Seeing (a) then (b), and being able to explain why (b) is the boundary, is the core learning outcome.

---

## 3. The invariant, property by property

**Server-side.** The filter is computed from `user_id` against the entitlements map that lives on the server. The client sends *who they are* (and, in the lab, we trust that), never *what they may see*. If authorization were a client input, it wouldn't be authorization.

**Pre-retrieval (in-query).** The filter is an argument to the vector search itself, so the store only ever *considers* entitled chunks. Contrast post-filtering, which retrieves a top-k across *all* content and then discards — that exposes un-entitled data to application code and can return fewer than k authorized results (a relevant authorized chunk gets crowded out by un-entitled neighbors that are later dropped).

**Un-overridable.** Any caller-supplied filtering is combined with the entitlement filter via boolean **AND**, so a caller can only ever *narrow* their results, never widen them:
```
effective_filter = AND(entitlement_filter, caller_filter_if_any)
```
There is no code path that lets a request replace or disable `entitlement_filter`.

---

## 4. Entitlements model

### The trusted map
A mock `{user_id: [product_id, ...]}` (in `security.py`; in production this is a DB / authz service). Example:
```python
ENTITLEMENTS = {
    "alice": ["detective"],
    "bob":   ["detective", "shakespeare"],
    "carol": ["science"],
    "root":  ["detective", "shakespeare", "science"],  # demo: the "everything" user
}
```

### Pool vs. silo (why we use pool)
- **Pool** (our model): one shared collection; isolation via the `product_id` metadata filter. Cost-efficient, simplest, exactly the pattern under test. Correct isolation depends entirely on the filter being right — hence the verification layer.
- **Silo**: a separate index/collection per tenant; physical isolation, stronger, costlier. The pattern you'd reach for with regulated or high-value tenants.

We deliberately build the **pool** model because the filter *is* the lesson. We note silo as the escalation path.

### Metadata at ingestion
Security starts at index time. Every chunk is stamped `{product_id, source, chunk_id}` and the vector carries it. A chunk without a `product_id` is un-securable and must fail ingestion loudly.

---

## 5. Filter construction (the mechanism)

`security.py` is the only place the entitlement filter is built:

```python
class NoEntitlementsError(Exception):
    """No licensed products for this user — carries a mock upsell message."""

# Mock production "you have no licenses" response (the friendly denial we render).
NO_LICENSE_MESSAGE = (
    "You have no active licenses. To purchase access, visit www.my-fake-ass-product.derp"
)

def entitlement_filter(user_id: str) -> dict:
    allowed = ENTITLEMENTS.get(user_id, [])
    if not allowed:
        # Fail closed BEFORE the data layer: no entitlements → deny, never an open filter.
        # We do NOT return {"$in": []} — chromadb 1.5.x rejects an empty $in, and raising
        # here short-circuits the embed + query entirely for an unentitled user (option a).
        raise NoEntitlementsError(NO_LICENSE_MESSAGE)
    return {"product_id": {"$in": allowed}}

def compose(entitlement: dict, caller_filter: dict | None) -> dict:
    if not caller_filter:
        return entitlement
    return {"$and": [entitlement, caller_filter]}   # caller can only narrow
```

`retrieve.py` enforces it and refuses to proceed without it (defense against T1):
```python
flt = compose(entitlement_filter(user_id), caller_filter)  # raises NoEntitlementsError if none
assert "product_id" in str(flt), "refusing to query without an entitlement constraint"
results = store.query(query_embedding, k=k, where=flt)   # filter INSIDE the query
# NoEntitlementsError propagates to the caller (demo/API), which renders NO_LICENSE_MESSAGE.
```

**Fail closed:** an unknown user or empty entitlement is **denied before the store** — `entitlement_filter` raises `NoEntitlementsError` (rendered as a mock "no licenses" upsell), never an open filter and never an empty `$in` (which chromadb 1.5.x rejects).

### Backend mapping (same invariant, two engines)
| Concern | Phase 1 — Chroma | Phase 2 — Azure AI Search |
|---|---|---|
| Filter syntax | `where={"product_id": {"$in": allowed}}` | OData `filter="search.in(product_id, '...')"` |
| Pre-filter guarantee | `where` constrains candidates within the search | `vectorFilterMode: preFilter` (use this, not `postFilter`) |

---

## 6. Verification (how we prove it)

1. **The demo** (`demo.py`) — the no-filter vs. filter comparison from §2, printed side by side with `product_id` and similarity scores so the leak is visible to the eye.
2. **The cross-tenant test** (`tests/`, pytest) — for each user, fire queries designed to surface *other* products' content and assert no result's `product_id` is outside that user's entitlements. This test is **mandatory** the moment `retrieve.py` + `security.py` exist; a passing suite without it is a false sense of safety.
3. **Negative path** — assert that an unknown/unentitled user is **denied before the store** (raises `NoEntitlementsError`, no query issued), and that a caller-supplied filter can narrow but not widen results.

### Known caveat to teach (not a Phase-1 blocker)
Very selective metadata filters combined with ANN graph traversal (HNSW) can create "recall holes" — the graph may not reach enough matching nodes. Negligible at learning-lab corpus size, but it's the right concept and a reason production systems sometimes prefer silos for highly selective tenants.

---

## 7. Other security concerns (right-sized)

- **Secrets** — Azure keys go in `.env` (git-ignored); never logged, never committed. The `pre-tool-security` hook blocks reads/writes of `*.env`, `*credentials*`, `*secrets*`, `*.key`, `*.pem`.
- **Retrieved content is untrusted** — if/when a generation step is added, retrieved text is data, not instructions (prompt-injection boundary). Out of scope until generation exists.
- **PII / data governance** — N/A for a public-domain corpus, but the principle (access metadata travels with the vector; minimum-necessary retrieval) is exactly what generalizes to real data.

---

## 8. Non-goals (this project)

- Authentication / `user_id` verification (we trust the resolved identity).
- Encryption at rest, network security, full RBAC/ABAC policy engines.
- A generative LLM synthesis step (retrieval returns chunks).
- Rate limiting, auditing infrastructure, multi-region.

---

## References
- Pre-filter vs post-filter and `vectorFilterMode` — Azure AI Search vector query docs (API 2026-04-01).
- Chroma metadata `where` filtering — chromadb 1.5.x docs.
- Multi-tenant RAG patterns (pool vs silo, metadata filtering, cross-tenant tests) — research brief 2026-06-06 (see `docs/decisions/ADR-002`).
