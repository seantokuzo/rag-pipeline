"""Stage 1 — ingest: the loader seam (ADR-005, spec-phase-1.5).

`RawDoc`/`SourceDoc`/`Loader` (base.py), the `.txt` loader (text.py), and the extension
dispatch + `product_id` stamping (registry.py). Re-exported here so existing call sites
(`from rag_exp.ingest import SourceDoc, load_products`) keep working unchanged.
"""

from rag_exp.ingest.base import Loader, RawDoc, SourceDoc
from rag_exp.ingest.registry import LOADERS, load_products
from rag_exp.ingest.text import TextLoader

__all__ = ["LOADERS", "Loader", "RawDoc", "SourceDoc", "TextLoader", "load_products"]
