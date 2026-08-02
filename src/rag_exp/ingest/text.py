"""Plain-text loader (`.txt`) — the Phase-1 ingest path, now behind the `Loader` Protocol.

One file → exactly **one** `RawDoc`: a book is one document, and prose chunks should flow
across the whole text rather than stop at an arbitrary boundary. That one-part-per-file
choice is what keeps this refactor byte-identical to Phase 1 — same 990 chunks, same ids.

Trims Project Gutenberg boilerplate; `source` is the filename stem (unique per folder by
the filesystem, so the A.3 collision rule is satisfied for free).
"""

import logging
from pathlib import Path

from rag_exp.ingest.base import RawDoc

logger = logging.getLogger(__name__)

# Gutenberg wraps each book in these sentinels; the real text sits between them.
_GUTENBERG_START = "*** START OF THE PROJECT GUTENBERG"
_GUTENBERG_END = "*** END OF THE PROJECT GUTENBERG"


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


class TextLoader:
    """Load a UTF-8 `.txt` file as a single document."""

    def load(self, path: Path) -> list[RawDoc]:
        """Read `path`, trim Gutenberg boilerplate, return it as one part."""
        raw = path.read_text(encoding="utf-8")
        text = _strip_gutenberg_boilerplate(raw, path.name)
        if not text:
            raise ValueError(f"{path} is empty after trimming boilerplate")
        return [RawDoc(text=text, source=path.stem)]
