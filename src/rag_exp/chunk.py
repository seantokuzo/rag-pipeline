"""Stage 2 — chunk: split each `SourceDoc` into `Chunk` records.

Recursive, token-accurate splitting (tiktoken) at `chunk_size` tokens with
`chunk_overlap`. Every `Chunk` inherits `product_id`/`source` from its parent doc
and gets a stable id (`product_id:source:ordinal`) that the eval golden set
depends on surviving re-indexing. This is a pure text transformation — no ML, no
I/O (spec Part B). Sizing/overlap/strategy are parameters so `chunking-lab` can
sweep them.
"""

import logging
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag_exp.config import CHUNK_OVERLAP, CHUNK_SIZE
from rag_exp.ingest import SourceDoc

logger = logging.getLogger(__name__)

# tiktoken encoding used purely as a token *counter* for sizing. cl100k_base is a
# modern default; it approximates bge-small's WordPiece count closely enough (the
# real 512-token truncation check happens at embed time). See the chunking explainer.
_ENCODING = "cl100k_base"


@dataclass(frozen=True, slots=True)
class Chunk:
    """One ~`chunk_size`-token slice of a doc — security-tagged, stably identified."""

    id: str  # f"{product_id}:{source}:{ordinal}" — stable, unique
    text: str
    product_id: str
    source: str


def chunk_document(
    doc: SourceDoc,
    *,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    """Split one `SourceDoc` into ordered `Chunk`s, each inheriting its metadata.

    Pieces break on the largest natural boundary (paragraph → line → sentence →
    word) that keeps them under `chunk_size` tiktoken tokens. `from_tiktoken_encoder`
    makes that a hard cap — an oversized piece is recursively re-split.
    """
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=_ENCODING,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks = [
        Chunk(
            id=f"{doc.product_id}:{doc.source}:{ordinal}",
            text=piece,
            product_id=doc.product_id,
            source=doc.source,
        )
        for ordinal, piece in enumerate(splitter.split_text(doc.text))
    ]
    logger.info("chunked %-40s product=%-12s chunks=%d", doc.source, doc.product_id, len(chunks))
    return chunks


def chunk_documents(
    docs: list[SourceDoc],
    *,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    """Chunk every `SourceDoc` and flatten to the single list the pipeline carries."""
    chunks = [
        chunk
        for doc in docs
        for chunk in chunk_document(doc, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    ]
    logger.info("chunked %d docs into %d chunks", len(docs), len(chunks))
    return chunks
