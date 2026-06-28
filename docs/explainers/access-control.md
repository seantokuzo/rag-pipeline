# Access control & filtering — how it works

> Part of the [RAG explainer series](./README.md). Understanding-oriented: *how the concept works*, not the build steps. Step-agnostic (organized by process, not build order).

**Where it sits:** `ingest → chunk → embed → store / index → `**`[query] retrieve`**. Indexing left us a Chroma collection where every row carries its `product_id` next to its vector. This explainer is about the **query side**: how a `user_id` becomes a filter that makes the search return *only* the rows that user is licensed to see. It is the **heart of this project** — the one lesson everything else is scaffolding for. (Threat model & invariant: [`../SECURITY.md`](../SECURITY.md); spec contract: `docs/spec-phase-1.md` Part E.)

## The problem, in one sentence

We put **all** products in **one** collection (the "pool" model — [SECURITY.md §4](../SECURITY.md)). So a naïve nearest-neighbour search ranks across *everyone's* content — Sherlock, Shakespeare, and Darwin all in the same candidate pool. If Alice is only licensed for `detective`, *something* has to stop Shakespeare and science chunks from coming back to her. That something is the **entitlement filter**.

## The invariant (memorize this)

> Every retrieval query carries an authorization filter that is **(1) built server-side** from a **trusted map**, **(2) applied inside the vector search** (pre-filter), and **(3) impossible for the caller to weaken**. The retrievable set is the *intersection* of "similar to the query" and "the user is entitled to it" — computed **before** any results leave the store.

Four properties fall out of that, and `security.py` exists to guarantee them:

| Property | What it means | What breaks without it |
|---|---|---|
| **Server-side** | Filter derived from `user_id` against a map *on the server* | Caller grants themselves access (the cardinal sin) |
| **Pre-retrieval** | Filter passed *into* the query (`where=`) | Forbidden content reaches the app layer; authorized hits silently dropped |
| **Un-overridable** | Caller filters AND-ed *under* the entitlement filter | Caller widens their own access |
| **Fail-closed** | No entitlements → deny, never "match everything" | A bug opens the gates instead of closing them |

## 1. The trusted map — *server-side*

Authorization data lives here, in `security.py`, never in the request:

```python
ENTITLEMENTS: dict[str, list[str]] = {
    "alice": ["detective"],
    "bob":   ["detective", "shakespeare"],
    "carol": ["science"],
    "root":  ["detective", "shakespeare", "science"],  # the demo "everything" user
}
```

In production this is a DB / authz-service lookup — but the shape is the point: the server maps **who you are** → **what you may see**. The client sends *who they are* (a `user_id`); it never sends *what it may see*. **If authorization were a client input, it wouldn't be authorization.** (We don't verify the `user_id` itself — authentication is a [non-goal](../SECURITY.md); we trust the resolved identity and focus on what you do *with* it.)

## 2. Building the filter — `entitlement_filter()`

```python
def entitlement_filter(user_id: str) -> dict:
    allowed = ENTITLEMENTS.get(user_id, [])
    if not allowed:
        raise NoEntitlementsError(NO_LICENSE_MESSAGE)   # fail closed — see §4
    return {"product_id": {"$in": list(allowed)}}
```

For Alice this returns `{"product_id": {"$in": ["detective"]}}` — a Chroma `where` clause meaning *"only rows whose `product_id` is in this list."* That dict **is** the security boundary. Two deliberate details:

- **`$in` a list**, not `== a string`, because a user can be licensed for several products (Bob has two). One uniform shape covers one-or-many.
- **`list(allowed)` copies** the map's list into the filter. The returned dict must not hold a *live reference* to the entitlements map — otherwise downstream code that mutated it (`flt["product_id"]["$in"].append("science")`) would silently rewrite authz state for **every later request** in the process. A security module shouldn't hand out live handles to its source of truth.

## 3. Narrowing, never widening — `compose()`

A caller *may* pass their own filter (e.g. "only the book I'm currently reading"). We honour it **without ever letting it become an escalation**. Boolean **AND** does exactly that:

```python
def compose(entitlement: dict, caller_filter: dict | None) -> dict:
    if not caller_filter:
        return entitlement
    return {"$and": [entitlement, caller_filter]}   # caller can only narrow
```

The result set is the **intersection**, so a caller filter can only ever *shrink* it:

- Bob asks for `{"source": "hamlet"}` → `(detective ∪ shakespeare)` **AND** `source=hamlet` → just his Hamlet chunks. ✅ narrowed.
- Alice (detective only) asks for `{"product_id": "science"}` → `in [detective]` **AND** `== science` → **empty**. She gets *nothing*, never science. ✅ cannot widen.

There is **no code path** that lets a request *replace* or *disable* the entitlement filter — it is always the outer term of the AND. That is what "structurally un-overridable" means: not "we check that the caller didn't cheat," but "the shape of the code makes cheating impossible."

## 4. ★ Fail-closed — *before the data layer* (the locked decision)

What about a user with **no** licenses, or an **unknown** user? `ENTITLEMENTS.get(user_id, [])` returns `[]` for both, and we **deny right there**:

```python
if not allowed:
    raise NoEntitlementsError(NO_LICENSE_MESSAGE)
```

Why *raise*, and why *here*?

- **Fail closed, not open.** The dangerous failure mode is a bug that turns "no entitlements" into "match everything." Raising makes the safe outcome (no results) the *only* outcome.
- **Before the data layer.** The raise happens in `entitlement_filter`, *before* we embed the query or touch the store. An unentitled request never spends a cycle on the corpus — there is literally no query to leak from.
- **Not `{"$in": []}`.** The "natural" fail-closed filter — an empty `$in` — is a trap two ways: (a) chromadb 1.5.x **rejects an empty `$in`** with a `ValueError`, so it would crash rather than cleanly match nothing; and (b) even if it worked, you'd be doing query-time work for a user you already know gets nothing. (Caught by the `access-control-reviewer` at step 5 and locked as **option (a)** — see [SECURITY.md §5/§6](../SECURITY.md).)
- **Friendly denial.** The exception carries `NO_LICENSE_MESSAGE` — a mock upsell ("you have no active licenses; purchase at …"). The caller (the demo, or a real API) catches `NoEntitlementsError` and renders it. This mocks the production gate: a paywall, not a stack trace.

So "fail-closed" here is stronger than the textbook version: we don't return a filter that matches nothing — we **decline to run the query at all**.

## 5. Where it gets *enforced* — `retrieve.py` (step 8)

`security.py` *builds* the filter; `retrieve.py` *uses* it and refuses to run without it:

```python
flt = compose(entitlement_filter(user_id), caller_filter)  # raises if no entitlements
assert "product_id" in str(flt), "refusing to query without an entitlement constraint"
emb = embedder.embed_query(query)
return store.query(emb, k=k, where=flt)   # filter INSIDE the query (pre-filter)
```

Two defenses live here:

- **The assertion** is the backstop for threat **T1** ("a code path forgot the filter"): if `flt` somehow lacked a `product_id` constraint, we crash rather than run an unfiltered (full-corpus) query.
- **`where=flt` inside `store.query`** makes it a **pre-filter** — the nearest-neighbour search only ever *considers* entitled rows. Never retrieve-then-drop (post-filter), which leaks to the app layer and can silently return fewer than `k` real hits. (See the `where` section of [vector-store](./vector-store.md).)

## The cardinal sin (what this all prevents)

> **Never accept an authorization filter from the caller.**

If the API let the request say `where={"product_id": {"$in": ["science"]}}`, the caller would simply *grant themselves* science. That is threat **T2**. Our shape makes it impossible: the only filter the store ever sees is `compose(entitlement_filter(user_id), caller_filter)` — the entitlement term is always present, always server-built, always the outer AND. A caller filter is *input to a narrowing*, never the authorization itself.

## The leak we demonstrate (the payoff — step 9)

Same query, same user (Alice, `detective` only), two ways:

- **(a) `store.query(emb, k, where=None)`** → top-k includes `shakespeare` / `science`. **This is the leak.**
- **(b) `retrieve("alice", query)`** → top-k is `detective` only. **This is the fix.**

Seeing (a) then (b) — and being able to explain *why* (b) is the boundary — is the entire learning outcome.

## Same invariant, two engines (Phase 2 preview)

The mechanism is engine-specific; the **invariant is not**:

| Concern | Phase 1 — Chroma | Phase 2 — Azure AI Search |
|---|---|---|
| Filter syntax | `where={"product_id": {"$in": allowed}}` | OData `filter="search.in(product_id, '…')"` |
| Pre-filter guarantee | `where` constrains candidates in the search | `vectorFilterMode: preFilter` (not `postFilter`) |

`security.py` is written so Phase 2 swaps the *filter dialect*, not the *policy*: `entitlement_filter` / `compose` keep their shape; only the emitted clause changes.

## Control flow, end to end

```
            request: { user_id, query, caller_filter? }
                          │
   user_id ─► entitlement_filter(user_id)
                          │  ENTITLEMENTS.get → []?  ─► raise NoEntitlementsError ─► render upsell (deny, no query)
                          ▼
              {product_id: {$in: allowed}}             ← server-side, the boundary
                          │
              compose(…, caller_filter)                ← AND: caller can only narrow
                          ▼
   query ─► embed_query ─► store.query(emb, k, where=flt)   ← pre-filter, inside the search
                          ▼
              list[Hit]  — only entitled rows, top-k by cosine
```

## TL;DR

`security.py` is the **single source of authorization**. It owns a server-side `ENTITLEMENTS` map and turns a `user_id` into a Chroma `where` filter (`{product_id: {$in: allowed}}`) that retrieval applies **inside** the vector search (pre-filter, never post-filter). A caller may pass their own filter, but it is **AND-ed under** the entitlement filter, so callers can only ever **narrow**, never widen — and there is no code path to replace the entitlement term (the cardinal sin: client-supplied auth). A user with no/unknown entitlements is **denied before the data layer** — `entitlement_filter` raises `NoEntitlementsError` (rendered as a mock upsell), never an open filter and never an empty `$in` (which Chroma rejects). The proof lands later: the `retrieve.py` assertion (T1 backstop), the leak demo (a-vs-b), and the mandatory cross-tenant test.
