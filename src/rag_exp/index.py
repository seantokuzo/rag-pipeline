"""Stage 5 — index: the one-time write that fills the Chroma collection.

Orchestration, not new logic — it runs the whole offline pipeline end to end
(load_products -> chunk_documents -> Embedder.embed_documents -> ChromaStore.upsert)
over the full corpus, so every query afterward is a cheap read against a built index
(write-once / read-many). Re-running is idempotent: stable chunk ids + Chroma `upsert`
overwrite in place instead of duplicating, and the corpus is frozen, so the same chunks
come back every run.

This is also where the 512-token truncation check deferred from chunking surfaces
(spec B.3 / Part C): bge silently clips any text past its max sequence length, so before
writing we log which chunks (if any) exceed it -- visibility at the moment the affected
vectors are built, not a gate (the 2 over-cap chunks were accepted in step 4).

Run it:  uv run python -m rag_exp.index
"""

import logging
import time

from rag_exp.chunk import Chunk, chunk_documents
from rag_exp.config import CHUNK_OVERLAP, CHUNK_SIZE
from rag_exp.embed import Embedder
from rag_exp.ingest import load_products
from rag_exp.store import ChromaStore, VectorStore

logger = logging.getLogger(__name__)


def build_index(
    *,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    embedder: Embedder | None = None,
    store: VectorStore | None = None,
) -> int:
    """Build (or refresh) the vector index over the full corpus; return chunks written.

    Pipeline: load -> chunk -> embed -> upsert. `embedder`/`store` are injectable for tests
    and the chunk-size sweeps (ADR-004); both default to the Phase-1 bge + Chroma setup.
    Idempotent on stable chunk ids, so re-running is safe (overwrites in place, not additive).
    """
    started = time.perf_counter()

    docs = load_products()
    chunks = chunk_documents(docs, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if not chunks:
        logger.warning("no chunks produced — nothing to index")
        return 0

    embedder = embedder or Embedder()
    _log_truncation_check(embedder, chunks)
    embeddings = embedder.embed_documents([c.text for c in chunks])

    store = store or ChromaStore()
    store.upsert(chunks, embeddings)

    logger.info("index built: %d chunks in %.1fs", len(chunks), time.perf_counter() - started)
    return len(chunks)


def _log_truncation_check(embedder: Embedder, chunks: list[Chunk]) -> None:
    """Log which chunks exceed bge's max sequence length (their vectors get tail-clipped).

    Non-fatal and informational: bge truncates past `max_seq_length` silently at embed time,
    clipping only the *vector* (the full text is still stored). We surface the affected ids
    here so the clipping is visible at index time. See docs/explainers/embedding.md.
    """
    limit = embedder.max_seq_length
    lengths = embedder.count_tokens([c.text for c in chunks])
    over = [(c.id, n) for c, n in zip(chunks, lengths, strict=True) if n > limit]
    if not over:
        logger.info("token check: all %d chunks ≤ %d bge tokens", len(chunks), limit)
        return
    detail = ", ".join(f"{cid} ({n})" for cid, n in over)
    logger.warning(
        "token check: %d/%d chunks over %d bge tokens — vectors tail-truncated, text kept: %s",
        len(over),
        len(chunks),
        limit,
        detail,
    )


def main() -> None:
    """CLI entry — `uv run python -m rag_exp.index`. Configures INFO logging, then builds."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    build_index()


if __name__ == "__main__":
    main()
