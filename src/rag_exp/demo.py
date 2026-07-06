"""Stage 8 — demo: the licensing-leak payoff, side by side (spec Part G).

Fires ONE query as detective-only "alice", two ways, and prints the results so the
difference is impossible to miss:

  (a) store.query(where=None)      no entitlement filter   -> shakespeare/science LEAK in
  (b) Retriever.retrieve("alice")  server-side pre-filter  -> detective only

The visible diff between (a) and (b) is the entire lesson of this project
(walkthrough: docs/explainers/access-control.md; threat model: docs/SECURITY.md).
For completeness it also shows (c) an *authorized* full-corpus user (root, licensed
for all three products) and (d) the fail-closed denial an unlicensed user hits
(NoEntitlementsError -> the mock upsell) — so the whole story (leak, fix, legitimate
breadth, denial) is on one screen.

Panel (a) is the ONE place we call store.query(where=None) on purpose: it bypasses
the filter deliberately, to demonstrate the very leak the filter prevents. Real code
never does this — retrieval always goes through Retriever.retrieve (the guarded path).

Run it:  uv run python -m rag_exp.demo
         uv run python -m rag_exp.demo "an evolutionary account of the origin of species"
Requires a built index first:  uv run python -m rag_exp.index
"""

import logging
import sys

from rag_exp.config import K
from rag_exp.embed import Embedder
from rag_exp.retrieve import Retriever
from rag_exp.security import ENTITLEMENTS, NoEntitlementsError
from rag_exp.store import ChromaStore, Hit

# A query in *science* vocabulary. Fired by detective-only "alice" it is the sharpest
# probe: unfiltered it pulls Darwin to the top (the leak); filtered, alice still sees
# only detective. This is the query the vacuity guard in the leak test proves DOES
# surface science unfiltered — so the demo is guaranteed to leak. Override on the CLI.
DEFAULT_QUERY = "evolution by natural selection and the origin of species"
DEMO_USER = "alice"

WIDTH = 96
SNIPPET = 50  # chars of chunk text shown per row (whitespace-collapsed)


def _snippet(text: str) -> str:
    """One-line, whitespace-collapsed preview of a chunk's text."""
    flat = " ".join(text.split())
    return flat if len(flat) <= SNIPPET else flat[: SNIPPET - 1] + "…"


def _trunc(s: str, n: int) -> str:
    """Clip `s` to `n` display chars with an ellipsis, so columns stay aligned."""
    return s if len(s) <= n else s[: n - 1] + "…"


def _panel(label: str, hits: list[Hit], entitled: set[str]) -> int:
    """Print one result panel; return how many hits fell outside `entitled` (leaks)."""
    print(label)
    print("-" * WIDTH)
    if not hits:
        print("  (no results)")
    for rank, h in enumerate(hits, start=1):
        flag = "  🚨 LEAK" if h.product_id not in entitled else ""
        print(
            f"  {rank}  {h.score:+.2f}  {_trunc(h.product_id, 11):<11}  "
            f"{_trunc(h.source, 26):<26}  {_snippet(h.text)}{flag}"
        )
    n_leaked = sum(1 for h in hits if h.product_id not in entitled)
    if n_leaked:
        stolen = sorted({h.product_id for h in hits if h.product_id not in entitled})
        print(f"  → 🚨 {n_leaked}/{len(hits)} hits LEAKED from unlicensed products: {stolen}")
    else:
        print(f"  → ✅ {len(hits)}/{len(hits)} hits licensed — nothing leaked.")
    return n_leaked


def run_demo(query: str) -> None:
    """Load the pipeline once, then print the (a)/(b)/(c)/(d) panels for `query`."""
    print("loading bge-small + Chroma (first run downloads the model)…\n")
    # One model load + one store connection, shared across every panel below.
    embedder = Embedder()
    store = ChromaStore()
    retriever = Retriever(embedder=embedder, store=store)

    entitled = set(ENTITLEMENTS[DEMO_USER])

    print("=" * WIDTH)
    print(f'  LEAK DEMO   user "{DEMO_USER}"   licensed for: {sorted(entitled)}')
    print(f'  query: "{query}"')
    print("=" * WIDTH)

    # (a) THE LEAK — deliberately unfiltered. Same query vector as (b); only the filter
    #     differs, so any difference below is the filter and nothing else.
    emb = embedder.embed_query(query)
    hits_a = store.query(emb, k=K, where=None)
    a_leaked = _panel(
        "\n(a) UNFILTERED   store.query(where=None)   ← no entitlement filter (the bug)",
        hits_a,
        entitled,
    )

    # (b) THE FIX — the real guarded path.
    hits_b = retriever.retrieve(DEMO_USER, query, k=K)
    b_leaked = _panel(
        f'\n(b) FILTERED   retrieve("{DEMO_USER}", query)   ← server-side pre-filter (the fix)',
        hits_b,
        entitled,
    )

    print("\n" + "=" * WIDTH)
    print(
        f"  RESULT:  (a) leaked {a_leaked}/{len(hits_a)} · (b) leaked {b_leaked}/{len(hits_b)}."
        "  The server-side pre-filter is the only difference — that is the lesson."
    )
    print("=" * WIDTH)

    # (c) legitimate breadth: root is licensed for everything, so full-corpus hits here
    #     are authorized, not a leak. Proves (b) isn't "hardcode detective" — it's authz.
    _panel(
        '\n(c) AUTHORIZED   retrieve("root", query)   ← root is licensed for all 3 products',
        retriever.retrieve("root", query, k=K),
        set(ENTITLEMENTS["root"]),
    )

    # (d) fail-closed: an unknown user is denied *before* the store — no query, no leak,
    #     just the mock upsell. Option (a) in action (docs/SECURITY.md §5/§6).
    print('\n(d) DENIED   retrieve("mallory", query)   ← unknown user, no licenses')
    print("-" * WIDTH)
    try:
        retriever.retrieve("mallory", query, k=K)
    except NoEntitlementsError as exc:
        print("  NoEntitlementsError raised before any embed/store call → the app renders:")
        print(f'      "{exc}"')
    else:
        print("  ⚠️  expected a denial but a query ran — fail-closed is broken!")


def main() -> None:
    """CLI entry — `uv run python -m rag_exp.demo ["custom query"]`."""
    logging.basicConfig(level=logging.WARNING)  # keep pipeline INFO chatter out of the panels
    query = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUERY
    run_demo(query)


if __name__ == "__main__":
    main()
