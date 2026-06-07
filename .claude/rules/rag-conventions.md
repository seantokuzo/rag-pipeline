---
paths:
  - "src/rag_exp/embed.py"
  - "src/rag_exp/retrieve.py"
  - "src/rag_exp/chunk.py"
  - "src/rag_exp/ingest.py"
  - "src/rag_exp/store/**/*.py"
---

# RAG conventions & footguns

- **Embedding parity:** index and query use the SAME model, normalization, and prompt convention. `encode_document()` for chunks, `encode_query()` for queries (bge-small has an asymmetric query prefix). A mismatch silently tanks recall.
- **Cosine, not L2:** Chroma collections set `metadata={"hnsw:space": "cosine"}` (L2 is the default) — embeddings are normalized.
- **Metadata on every chunk:** stamp `{product_id, source}` at ingestion. An unlabeled chunk is un-securable.
- **Chunking:** recursive, 512 tokens, no overlap to start (token-accurate via tiktoken). Keep ≤ the model's max sequence (512 for bge-small).
