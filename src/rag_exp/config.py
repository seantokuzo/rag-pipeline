"""Central configuration — Phase 1 defaults (spec Appendix).

Plain module-level constants: the simplest thing that works, and it matches the
spec. No secrets/env here (Phase 2's Azure work will add a settings object that
reads `.env`). Paths are anchored to the project root, not the current working
directory, so `uv run ...` behaves the same from any folder.
"""

from pathlib import Path

# repo root: this file is <root>/src/rag_exp/config.py, so parents[2] is <root>.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

# ── Corpus / store locations ──
PRODUCTS_ROOT: Path = PROJECT_ROOT / "products"
CHROMA_PATH: Path = PROJECT_ROOT / ".chroma"

# ── Vector store ──
COLLECTION: str = "corpus"
SPACE: str = "cosine"  # Chroma defaults to L2; cosine is mandatory for normalized vectors

# ── Embeddings ──
MODEL: str = "BAAI/bge-small-en-v1.5"
EMBED_DEVICE: str = "cpu"  # small model; no GPU needed
# Unit-length vectors — pairs with SPACE="cosine" above; flip one and cosine lies.
NORMALIZE: bool = True
# bge is asymmetric: prepend the instruction to QUERIES ONLY (passages stay bare). The HF model
# ships no sentence-transformers prompts config, so embed.py registers it on the model itself.
# String verified against BAAI's bge-*-en-v1.5 model card. See docs/explainers/embedding.md.
QUERY_PROMPT: str = "Represent this sentence for searching relevant passages: "

# ── Chunking ──
CHUNK_SIZE: int = 512  # tokens (tiktoken-accurate); <= bge-small's max sequence
CHUNK_OVERLAP: int = 0

# ── Retrieval ──
K: int = 5
