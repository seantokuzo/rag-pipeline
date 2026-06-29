"""Stage 7 — retrieve: the guarded query path (security + embed + store).

`Retriever.retrieve(user_id, query, ...)` is the ONLY entry point the demo / a
real API should use to search the corpus. It enforces the access-control
invariant end to end (full model: docs/SECURITY.md; walkthrough:
docs/explainers/access-control.md):

    flt = compose(entitlement_filter(user_id), caller_filter)  # server-side, AND-composed
    assert "product_id" in str(flt)         # T1: never query unfiltered
    emb = embedder.embed_query(query)        # query-side embedding parity
    return store.query(emb, k=k, where=flt)  # filter INSIDE the search (pre-filter)

Why a class and not the bare `retrieve()` of spec Part F: retrieval holds a
loaded embedding model and an open store connection that must persist across many
cheap calls (re-loading bge per query would be absurd). The class owns those
collaborators once; both are injectable so the cross-tenant test and the ADR-004
sweeps can pass fakes / alternate stores. The `retrieve` method keeps the spec's
signature.

`entitlement_filter` raises `NoEntitlementsError` for an unknown/unentitled user;
we let it propagate so the caller can render the mock upsell — and because it
raises *before* the embed/store calls, an unentitled request never touches the
corpus.
"""

import logging

from rag_exp.config import K
from rag_exp.embed import Embedder
from rag_exp.security import compose, entitlement_filter
from rag_exp.store import ChromaStore, Hit, VectorStore

logger = logging.getLogger(__name__)


class Retriever:
    """Guarded retrieval over the corpus — the single entry point for queries.

    Holds an `Embedder` and a `VectorStore`, constructed once and injectable. Every
    query is narrowed by the server-side entitlement filter built from `user_id`;
    there is no method that queries the store without it.
    """

    def __init__(self, embedder: Embedder | None = None, store: VectorStore | None = None) -> None:
        # Defaults wire the real pipeline (bge-small + the persisted ./.chroma); tests
        # and sweeps inject their own. Built once so the model + connection persist.
        self._embedder = embedder if embedder is not None else Embedder()
        self._store = store if store is not None else ChromaStore()

    def retrieve(
        self,
        user_id: str,
        query: str,
        k: int = K,
        caller_filter: dict | None = None,
    ) -> list[Hit]:
        """Return the top-`k` entitled chunks for `query`, for `user_id`.

        Builds the entitlement filter server-side from `user_id`, AND-composes any
        `caller_filter` *under* it (so the caller can only narrow), and applies it
        INSIDE the vector search (pre-filter, never retrieve-then-drop). Raises
        `NoEntitlementsError` (propagated from `entitlement_filter`) for an
        unknown/unentitled user — before any embedding or store access.
        """
        # 1) Authorization filter — server-side, un-overridable. Raises if no entitlements.
        flt = compose(entitlement_filter(user_id), caller_filter)
        # 2) T1 defense: refuse to run a query lacking a product_id constraint. This can
        #    only fail if the filter contract above is broken — fail loud rather than
        #    silently fall through to an unfiltered (full-corpus) search.
        assert "product_id" in str(flt), "refusing to query without an entitlement constraint"
        # 3) Query-side embedding (parity with the index side is handled in Embedder).
        emb = self._embedder.embed_query(query)
        # 4) Pre-filter: the filter goes INSIDE the search, never retrieve-then-drop.
        hits = self._store.query(emb, k=k, where=flt)
        logger.info("retrieve user=%s k=%d -> %d hits", user_id, k, len(hits))
        return hits
