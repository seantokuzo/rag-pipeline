"""Stage 4 — the vector-store seam: the one deliberate abstraction.

Defines the `VectorStore` Protocol (the contract every store backend implements)
and the `Hit` record a query returns. Phase 1 implements it with Chroma
(`chroma.py`); Phase 2 adds Azure AI Search behind the SAME Protocol — the pipeline
stages and the access-control invariant don't move when the store does. This is the
*only* abstraction the project builds on purpose; everywhere else, premature
abstraction is an anti-pattern. See docs/explainers/vector-store.md.

The `where` argument is a server-side entitlement pre-filter: it is built in
`security.py` from a trusted map and passed straight through to the query. The store
is mechanism, not policy — it never invents a filter and never accepts one from an
end user. (Enforcement that a filter is actually *present* lives in retrieve.py.)
"""

from dataclasses import dataclass
from typing import Protocol

from rag_exp.chunk import Chunk


@dataclass(frozen=True, slots=True)
class Hit:
    """One retrieved chunk and how closely it matched — what `query` returns.

    `score` is **cosine similarity** in [-1, 1] (bigger = closer; 1.0 = identical
    direction), derived as `1 - cosine_distance` in the store. We expose similarity,
    not raw distance, so "higher is better" holds everywhere downstream and the number
    reads in the same units as the embedding step's cosine readouts.
    """

    id: str
    text: str
    product_id: str
    source: str
    score: float


class VectorStore(Protocol):
    """Write vectors in, query nearest-with-optional-filter out — the store contract."""

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """Write (or overwrite) chunks and their embeddings, positionally aligned.

        `chunks[i]` and `embeddings[i]` must describe the same chunk. Idempotent on the
        chunk's stable id: re-indexing overwrites in place rather than duplicating.
        """
        ...

    def query(self, embedding: list[float], k: int, where: dict | None = None) -> list[Hit]:
        """Return the top-`k` nearest chunks, narrowed by `where` (a metadata pre-filter).

        `where=None` searches the whole collection (the leak-demo "before"); a real
        request always arrives with the entitlement filter already AND-ed in upstream.
        """
        ...
