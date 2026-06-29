"""Cross-tenant leak test — the mandatory security gate (SECURITY.md §6, spec H.3).

Proves the access-control invariant against the LIVE persisted index: no user ever
receives a chunk from a product they are not entitled to, an unknown user is denied
before the store, and a caller filter can narrow but never widen access.

This is an integration test — it builds a real `Retriever` (bge-small + the
persisted ./.chroma, 990 rows) once per module. If the index isn't built, run
`uv run python -m rag_exp.index` first.
"""

import pytest

from rag_exp.embed import Embedder
from rag_exp.retrieve import Retriever
from rag_exp.security import ENTITLEMENTS, NoEntitlementsError
from rag_exp.store import ChromaStore

# Queries written in each product's distinctive vocabulary, so that — unfiltered —
# they WOULD surface that product's chunks. Firing a science query as a
# detective-only user is exactly the cross-tenant probe the filter must defeat.
QUERIES = {
    "detective": "a baffling crime solved by sharp deduction and observation",
    "shakespeare": "to be or not to be, the prince's soliloquy on death",
    "science": "evolution by natural selection and the origin of species",
}
ALL_QUERIES = list(QUERIES.values())
NON_ROOT_USERS = ["alice", "bob", "carol"]


@pytest.fixture(scope="module")
def embedder() -> Embedder:
    """The real bge-small embedder, loaded once for the whole module."""
    return Embedder()


@pytest.fixture(scope="module")
def store() -> ChromaStore:
    """The persisted Chroma collection (990 rows, cosine)."""
    return ChromaStore()


@pytest.fixture(scope="module")
def retriever(embedder: Embedder, store: ChromaStore) -> Retriever:
    """Real retrieval pipeline, reusing the shared embedder + store (one model load)."""
    return Retriever(embedder=embedder, store=store)


@pytest.mark.parametrize("user_id", NON_ROOT_USERS)
def test_no_cross_tenant_leak(retriever: Retriever, user_id: str) -> None:
    """Every hit, for every query (incl. other products' vocabulary), is entitled."""
    allowed = set(ENTITLEMENTS[user_id])
    for query in ALL_QUERIES:
        hits = retriever.retrieve(user_id, query, k=10)
        leaked = [h for h in hits if h.product_id not in allowed]
        assert not leaked, (
            f"LEAK: user={user_id} entitled={allowed} got {[(h.product_id, h.id) for h in leaked]}"
        )


def test_leak_is_real_without_the_filter(embedder: Embedder, store: ChromaStore) -> None:
    """Vacuity guard: WITHOUT the filter the same probe DOES surface other products.

    Proves the no-leak test isn't passing trivially (e.g. because a query only ever
    matches one product). Alice is entitled to `detective` only; an unfiltered
    science query must surface non-detective chunks — the very leak the filter stops.
    """
    emb = embedder.embed_query(QUERIES["science"])
    unfiltered = store.query(emb, k=10, where=None)
    products = {h.product_id for h in unfiltered}
    assert "science" in products, f"expected science to surface unfiltered, got {products}"
    assert products - {"detective"}, "unfiltered query should reach beyond detective"


def test_unknown_user_denied_before_store(retriever: Retriever) -> None:
    """An unknown / unentitled user is denied (raises) — no query is ever issued."""
    with pytest.raises(NoEntitlementsError):
        retriever.retrieve("nobody", QUERIES["detective"])


def test_caller_filter_can_narrow(retriever: Retriever) -> None:
    """Bob (detective + shakespeare) can narrow to just shakespeare."""
    hits = retriever.retrieve(
        "bob", QUERIES["shakespeare"], k=10, caller_filter={"product_id": "shakespeare"}
    )
    assert hits, "expected some shakespeare hits for bob"
    assert all(h.product_id == "shakespeare" for h in hits)


def test_caller_filter_cannot_widen(retriever: Retriever) -> None:
    """Alice (detective only) asking for science gets nothing — AND can't widen."""
    hits = retriever.retrieve(
        "alice", QUERIES["science"], k=10, caller_filter={"product_id": "science"}
    )
    # detective ∩ science = ∅ → the AND matches nothing; alice cannot reach science.
    assert all(h.product_id in ENTITLEMENTS["alice"] for h in hits)
    assert not any(h.product_id == "science" for h in hits)


def test_caller_filter_cannot_widen_via_or(retriever: Retriever) -> None:
    """A caller can't smuggle a wider scope through `$or` — AND-nesting still gates.

    Alice (detective only) passes `science OR detective`; the entitlement filter is
    AND-ed *over* the whole caller clause, so every returned row is still detective
    and science never leaks. Guards against a future `compose` refactor that breaks
    the outer AND (caught by CI, not just a live probe).
    """
    hits = retriever.retrieve(
        "alice",
        QUERIES["science"],
        k=10,
        caller_filter={"$or": [{"product_id": "science"}, {"product_id": "detective"}]},
    )
    assert all(h.product_id in ENTITLEMENTS["alice"] for h in hits)
    assert not any(h.product_id == "science" for h in hits)
