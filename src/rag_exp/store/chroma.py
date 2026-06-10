"""Stage 4 (impl) — Chroma adapter behind the `VectorStore` Protocol.

A thin wrapper over chromadb's in-process `PersistentClient`: one on-disk collection
in COSINE space. Three settings here each fail *silently* if wrong — all verified
against chromadb 1.5.9 (see docs/explainers/vector-store.md):

- **Cosine, not L2.** Chroma defaults to L2; our vectors are normalized, so direction
  (cosine) is the meaningful signal. We set it at creation via
  `configuration={"hnsw": {"space": ...}}` (the 1.0+ form; the legacy
  `metadata={"hnsw:space": ...}` still works but is deprecated). The space is locked at
  creation and cannot be changed later — set it wrong and every query is quietly off.
- **`upsert`, not `add`.** On a duplicate id, `add()` silently keeps the FIRST write;
  `upsert()` overwrites. Our stable ids exist precisely so re-indexing is idempotent.
- **`embedding_function=None`.** We hand Chroma vectors from our own `Embedder`; it must
  never embed anything itself (no surprise model download, no parity-breaking second
  embedder slipping in on the query side).

Chroma returns a cosine *distance* (0 = identical … 2 = opposite); we map it back to a
similarity *score* (`1 - distance`) so the rest of the pipeline speaks one unit.
"""

import logging
from pathlib import Path

import chromadb
from chromadb import QueryResult

from rag_exp.chunk import Chunk
from rag_exp.config import CHROMA_PATH, COLLECTION, SPACE
from rag_exp.store.base import Hit

logger = logging.getLogger(__name__)


class ChromaStore:
    """`VectorStore` over a persistent Chroma collection (cosine HNSW)."""

    def __init__(
        self,
        path: Path = CHROMA_PATH,
        collection: str = COLLECTION,
        space: str = SPACE,
    ) -> None:
        self._client = chromadb.PersistentClient(path=str(path))
        # configuration= is the chromadb 1.0+ form (legacy metadata={"hnsw:space":...} is
        # deprecated). Cosine is mandatory for normalized vectors and is locked at creation.
        # embedding_function=None: this collection never embeds — we supply vectors from our
        # own Embedder, and a default EF here could silently break query/index parity.
        self._col = self._client.get_or_create_collection(
            name=collection,
            configuration={"hnsw": {"space": space}},
            embedding_function=None,
        )
        logger.info(
            "opened chroma collection=%s path=%s space=%s rows=%d",
            collection,
            path,
            space,
            self._col.count(),
        )

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """Write chunks + vectors (idempotent on stable ids). The four lists are positional."""
        if len(chunks) != len(embeddings):
            # The 1:1 chunk↔vector contract: a mismatch would store the wrong vector for a
            # chunk, silently. Cheap to check once at index time; corrupting if we don't.
            raise ValueError(
                f"chunks/embeddings length mismatch: {len(chunks)} vs {len(embeddings)}"
            )
        if not chunks:
            logger.warning("upsert called with 0 chunks — nothing written")
            return
        self._col.upsert(
            ids=[c.id for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],  # FULL chunk text, untruncated
            metadatas=[{"product_id": c.product_id, "source": c.source} for c in chunks],
        )
        logger.info(
            "upserted %d chunks → collection=%s (rows=%d)",
            len(chunks),
            self._col.name,
            self._col.count(),
        )

    def query(self, embedding: list[float], k: int, where: dict | None = None) -> list[Hit]:
        """Top-`k` nearest chunks, optionally narrowed by the `where` pre-filter.

        `where` is passed straight into the query — a pre-filter, applied *inside* the
        search, never retrieve-then-drop. The store does not build or validate it; that is
        security.py's job (step 7). `where=None` searches the whole collection.
        """
        result = self._col.query(query_embeddings=[embedding], n_results=k, where=where)
        return _hits(result)


def _hits(result: QueryResult) -> list[Hit]:
    """Unzip Chroma's nested QueryResult (one inner list per query — we send one) into Hits."""
    ids = result["ids"][0]
    distances = result["distances"][0]
    documents = result["documents"][0]
    metadatas = result["metadatas"][0]
    return [
        Hit(
            id=id_,
            text=text,
            product_id=meta["product_id"],
            source=meta["source"],
            score=1.0 - distance,  # cosine distance (0=identical) → similarity (1=identical)
        )
        for id_, distance, text, meta in zip(ids, distances, documents, metadatas, strict=True)
    ]
