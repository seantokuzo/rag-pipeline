"""Stage 3 — embed: turn chunk/query text into normalized bge-small vectors.

Pure compute: text in, 384-dim unit-length vectors out (spec Part C). The one
rule that matters is **parity** — index and query embed under the same model and
normalization. bge-small is *asymmetric*: a query carries an instruction prefix,
a passage does not. We get that for real by registering bge's documented query
instruction (`config.QUERY_PROMPT`) as the model's "query" prompt, then routing
chunks through `encode_document()` (bare) and queries through `encode_query()`
(prefixed). The HF model ships no prompts config, so this registration is what
makes the asymmetry actually fire — see docs/explainers/embedding.md.

This stage also hosts the truncation check deferred from chunking: bge silently
drops anything past its real `max_seq_length` (512 WordPiece tokens, special
tokens included), and tiktoken sizing only approximates that. `count_tokens()`
exposes the real bge length so the index step can verify nothing is clipped.
"""

import logging

from sentence_transformers import SentenceTransformer

from rag_exp.config import EMBED_DEVICE, MODEL, NORMALIZE, QUERY_PROMPT

logger = logging.getLogger(__name__)


class Embedder:
    """bge-small wrapper: embeds documents and queries under identical settings,
    applying bge's asymmetric query instruction to queries only (the parity rule).
    """

    def __init__(
        self,
        model_name: str = MODEL,
        *,
        device: str = EMBED_DEVICE,
        normalize: bool = NORMALIZE,
    ) -> None:
        # Register the query instruction as the "query" prompt → encode_query()
        # prepends it; we register no "document" prompt → encode_document() leaves
        # passages bare. That asymmetry is bge's intended retrieval setup.
        self._model = SentenceTransformer(
            model_name, device=device, prompts={"query": QUERY_PROMPT}
        )
        self._normalize = normalize
        logger.info(
            "loaded embedder model=%s device=%s normalize=%s max_seq_length=%d",
            model_name,
            device,
            normalize,
            self._model.max_seq_length,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed chunk texts (no prefix) for indexing — bge `encode_document()`."""
        vectors = self._model.encode_document(texts, normalize_embeddings=self._normalize)
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        """Embed one user query (query instruction prepended) — bge `encode_query()`."""
        vector = self._model.encode_query(text, normalize_embeddings=self._normalize)
        return vector.tolist()

    @property
    def max_seq_length(self) -> int:
        """bge's hard token limit; text beyond this is silently truncated at embed time."""
        return self._model.max_seq_length

    def count_tokens(self, texts: list[str]) -> list[int]:
        """Real bge (WordPiece) token length per text — special tokens in, truncation off.

        This is the true number `max_seq_length` (512) bounds, so it's what verifies
        no chunk is silently clipped (the check deferred from chunking). tiktoken sizing
        only approximates this, which is why the real check lives here, not in `chunk`.
        """
        encoded = self._model.tokenizer(list(texts), truncation=False)["input_ids"]
        return [len(ids) for ids in encoded]
