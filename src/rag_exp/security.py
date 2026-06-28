"""Stage 6 — security: the access-control boundary (the heart of this project).

This module is the **single source of authorization**. It owns the trusted
entitlements map (`user_id -> [product_id]`) and is the *only* place the
per-request entitlement filter is built. Retrieval (stage 7, `retrieve.py`)
consumes that filter, refuses to query without it, and passes it *inside* the
vector search. Get this module right and a tenant can never see another tenant's
content; get it wrong and the whole pooled collection leaks.

The invariant this module enforces (full threat model: docs/SECURITY.md;
plain-English walkthrough: docs/explainers/access-control.md):

- **Server-side.** The filter is derived from `user_id` against the trusted map
  that lives here on the server. The caller sends *who they are*, never *what
  they may see*. Authorization as a caller input isn't authorization — accepting
  a filter from the request is the cardinal sin (threat T2).
- **Pre-retrieval.** The filter is handed to `store.query(where=...)`, so the
  search only ever *considers* entitled chunks — never retrieve-then-drop.
- **Un-overridable.** A caller-supplied filter is AND-composed *under* the
  entitlement filter (`compose`), so a caller can only ever *narrow* their
  results, never widen them. No code path replaces the entitlement term.
- **Fail-closed, before the data layer.** An unknown or unentitled user is
  *denied here* — `entitlement_filter` raises `NoEntitlementsError` before any
  embed or store call — never an open filter, and never an empty `{"$in": []}`
  (which chromadb 1.5.x rejects). See docs/SECURITY.md §5/§6 (option (a)).
"""

# ── The trusted entitlements map (server-side authz data) ─────────────────────
# Which products each user has licensed. In production this is a DB / authz-service
# lookup keyed on the *authenticated* identity; here it's a literal so the lesson
# stays in view. This is the ONLY source of truth for "who may see what" — it lives
# server-side and is never influenced by the caller. The product_ids match the
# corpus folder names, i.e. the `product_id` stamped on every chunk at ingestion.
ENTITLEMENTS: dict[str, list[str]] = {
    "alice": ["detective"],
    "bob": ["detective", "shakespeare"],
    "carol": ["science"],
    "root": ["detective", "shakespeare", "science"],  # the demo "everything" user
}

# Mock production "you have no licenses" response — the friendly denial we render
# instead of leaking the fact that content exists. Carried by NoEntitlementsError.
NO_LICENSE_MESSAGE: str = (
    "You have no active licenses. To purchase access, visit www.my-fake-ass-product.derp"
)


class NoEntitlementsError(Exception):
    """Raised when a user has no licensed products — carries the mock upsell text.

    Deliberately raised *before* the data layer (no embed, no store query) so an
    unentitled request is denied without ever touching the corpus. The caller
    (demo / API) catches it and renders `NO_LICENSE_MESSAGE` — a paywall, not a
    stack trace. This is the locked "option (a)" fail-closed behaviour.
    """


def entitlement_filter(user_id: str) -> dict:
    """Build the server-side metadata pre-filter for `user_id`.

    Returns a Chroma `where` clause restricting retrieval to the user's licensed
    products: `{"product_id": {"$in": [...]}}`. This dict *is* the authorization
    boundary — built here from the trusted map, never accepted from the caller.

    Fails **closed**: an unknown user (absent from the map) or one with an empty
    entitlement list raises `NoEntitlementsError` *before* any embed/store work,
    rather than returning an open filter or an empty `{"$in": []}` (which chromadb
    1.5.x rejects outright). See docs/SECURITY.md §5/§6 (option (a)).
    """
    allowed = ENTITLEMENTS.get(user_id, [])
    if not allowed:
        # Unknown or unentitled -> deny here, before the data layer. Never widen
        # to the full corpus; never emit an empty $in. (Threat T2 / fail-closed.)
        raise NoEntitlementsError(NO_LICENSE_MESSAGE)
    # Copy the list so the returned filter holds no live reference to the
    # entitlements map: downstream code mutating it (e.g. appending a product_id)
    # would otherwise rewrite authz state for every later request — a silent
    # privilege escalation. A security module shouldn't leak handles to its truth.
    return {"product_id": {"$in": list(allowed)}}


def compose(entitlement: dict, caller_filter: dict | None) -> dict:
    """AND-combine the entitlement filter with an optional caller-supplied filter.

    The entitlement filter is non-negotiable; a caller filter can only *narrow*
    within it (e.g. "just the `source` I'm reading"), never widen or replace it.
    Boolean AND guarantees that — the result set is the intersection, so asking
    for a product you're not entitled to simply yields nothing, never that product.
    """
    if not caller_filter:
        return entitlement
    return {"$and": [entitlement, caller_filter]}
