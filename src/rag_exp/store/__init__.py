"""The vector-store seam (the one deliberate abstraction).

`VectorStore` Protocol + the `Hit` record (base.py) and the Chroma implementation
(chroma.py). Phase 2 adds `azure.py` behind the same Protocol — the pipeline and the
security invariant stay put. See docs/explainers/vector-store.md.
"""

from rag_exp.store.base import Hit, VectorStore
from rag_exp.store.chroma import ChromaStore

__all__ = ["ChromaStore", "Hit", "VectorStore"]
