"""Stage 1 — ingest: load each product's `.txt` into `SourceDoc` records.

Walks `PRODUCTS_ROOT/<product_id>/*.txt`, derives `product_id` from the folder
name, reads UTF-8, and trims Project Gutenberg boilerplate. Every `SourceDoc`
must carry a non-empty `product_id` — an unlabeled doc is un-securable, so a
`.txt` we can't attribute to a product is a hard error (spec Part A, T4).
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from rag_exp.config import PRODUCTS_ROOT

logger = logging.getLogger(__name__)

# Gutenberg wraps each book in these sentinels; the real text sits between them.
_GUTENBERG_START = "*** START OF THE PROJECT GUTENBERG"
_GUTENBERG_END = "*** END OF THE PROJECT GUTENBERG"


@dataclass(frozen=True, slots=True)
class SourceDoc:
    """One ingested document, pre-chunking (`source` = the filename stem)."""

    text: str
    product_id: str
    source: str


def _strip_gutenberg_boilerplate(text: str, source: str) -> str:
    """Return the text between the Gutenberg START/END markers.

    If either marker is missing we keep the full text but warn — a silent corpus
    failure is worse than a noisy one. (All three Phase-1 books have both.)
    """
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith(_GUTENBERG_START)), None)
    end = next((i for i, ln in enumerate(lines) if ln.startswith(_GUTENBERG_END)), None)

    if start is None or end is None:
        logger.warning(
            "%s: Gutenberg markers missing (start=%s, end=%s) — keeping full text",
            source,
            start,
            end,
        )
        return text.strip()

    return "\n".join(lines[start + 1 : end]).strip()


def load_products(root: Path = PRODUCTS_ROOT) -> list[SourceDoc]:
    """Load every product `.txt` under `root` into `SourceDoc` records.

    `product_id` is the immediate parent folder name. A `.txt` placed directly in
    `root` (no product folder, so `product_id` can't be derived) is a hard error.
    """
    if not root.is_dir():
        raise FileNotFoundError(f"products root not found: {root}")

    stray = sorted(root.glob("*.txt"))
    if stray:
        names = ", ".join(p.name for p in stray)
        raise ValueError(
            f"cannot derive product_id for .txt directly under {root}: {names} "
            "(every book must live in a products/<product_id>/ subfolder)"
        )

    docs: list[SourceDoc] = []
    for path in sorted(root.glob("*/*.txt")):
        product_id = path.parent.name
        raw = path.read_text(encoding="utf-8")
        text = _strip_gutenberg_boilerplate(raw, path.name)
        if not text:
            raise ValueError(f"{path} is empty after trimming boilerplate")
        docs.append(SourceDoc(text=text, product_id=product_id, source=path.stem))
        logger.info("loaded %-40s product=%-12s chars=%d", path.name, product_id, len(text))

    if not docs:
        logger.warning("no product .txt found under %s", root)
        return docs

    counts: dict[str, int] = {}
    for d in docs:
        counts[d.product_id] = counts.get(d.product_id, 0) + 1
    logger.info("ingested %d docs across %d products: %s", len(docs), len(counts), counts)
    return docs
