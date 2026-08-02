"""Ingest dispatch — walk the product tree, route each file to its loader, stamp security.

Everything security-relevant lives here, in ONE place, so per-format loaders can stay
dumb about it:

* `product_id` is derived from the immediate parent folder (the trusted source) and
  stamped onto every `SourceDoc` here — a loader has no `product_id` field to set.
* A supported file we can't attribute to a product is a **hard error** (an unlabelled
  chunk is un-securable — spec Part A, T4).
* the chunk-id prefix `product_id:source` is asserted globally unique, so chunk ids can
  never collide and silently overwrite in the store (spec-phase-1.5 A.3).

Dispatch is by lowercased file extension. Files with no registered loader are skipped
and reported in a summary line — never dropped silently.
"""

import logging
from pathlib import Path

from rag_exp.config import PRODUCTS_ROOT
from rag_exp.ingest.base import Loader, SourceDoc
from rag_exp.ingest.text import TextLoader

logger = logging.getLogger(__name__)

# Extension → loader. Phase 1.5 grows this: .csv/.xlsx (step 2), .pdf (steps 3–4),
# audio/video (steps 5–6). Keys are lowercase, with the leading dot.
LOADERS: dict[str, Loader] = {".txt": TextLoader()}


def load_products(
    root: Path = PRODUCTS_ROOT,
    loaders: dict[str, Loader] | None = None,
) -> list[SourceDoc]:
    """Load every supported file under `root/<product_id>/` into `SourceDoc` records.

    `product_id` is the immediate parent folder name. A supported file placed directly
    in `root` (no product folder, so `product_id` can't be derived) is a hard error.
    `loaders` is injectable for tests; it defaults to the module-level `LOADERS`.
    """
    loaders = LOADERS if loaders is None else loaders

    if not root.is_dir():
        raise FileNotFoundError(f"products root not found: {root}")

    stray = sorted(p for p in root.glob("*") if p.is_file() and p.suffix.lower() in loaders)
    if stray:
        names = ", ".join(p.name for p in stray)
        raise ValueError(
            f"cannot derive product_id for files directly under {root}: {names} "
            "(every source must live in a products/<product_id>/ subfolder)"
        )

    docs: list[SourceDoc] = []
    seen: dict[str, Path] = {}
    skipped: dict[str, int] = {}

    for path in sorted(root.glob("*/*")):
        if not path.is_file():
            if path.is_dir():
                logger.warning(
                    "%s: nested folders are not walked — nothing under it will be ingested",
                    path,
                )
            continue

        suffix = path.suffix.lower()
        loader = loaders.get(suffix)
        if loader is None:
            skipped[suffix or "<no extension>"] = skipped.get(suffix or "<no extension>", 0) + 1
            continue

        product_id = path.parent.name
        parts = list(loader.load(path))
        if not parts:
            logger.warning("%s: loader returned no parts — nothing indexed for this file", path)
            continue

        for part in parts:
            # Key on the literal id PREFIX, not a (product_id, source) tuple: chunk ids are
            # the concatenation `product_id:source:ordinal`, so distinct tuples can still
            # collide — ("a", "x:y") and ("a:x", "y") both yield "a:x:y:0". Keying on the
            # prefix makes this check injective with the id scheme by construction.
            key = f"{product_id}:{part.source}"
            if key in seen:
                raise ValueError(
                    f"duplicate chunk-id prefix {key!r}: produced by both {seen[key]} "
                    f"and {path}. Chunk ids are product_id:source:ordinal, so these would "
                    "collide and silently overwrite in the store — a multi-part loader "
                    "must fully qualify `source` (e.g. 'report#p07')."
                )
            seen[key] = path
            docs.append(SourceDoc(text=part.text, product_id=product_id, source=part.source))

        logger.info(
            "loaded %-40s product=%-12s parts=%-3d chars=%d",
            path.name,
            product_id,
            len(parts),
            sum(len(p.text) for p in parts),
        )

    if skipped:
        logger.info("skipped %d unsupported files: %s", sum(skipped.values()), skipped)

    if not docs:
        logger.warning("no supported product files found under %s", root)
        return docs

    counts: dict[str, int] = {}
    for d in docs:
        counts[d.product_id] = counts.get(d.product_id, 0) + 1
    logger.info("ingested %d docs across %d products: %s", len(docs), len(counts), counts)
    return docs
