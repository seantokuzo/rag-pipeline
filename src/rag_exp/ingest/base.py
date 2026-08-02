"""Stage 1 — the ingest loader seam: the contract every source format implements.

`RawDoc` (what a loader produces), `SourceDoc` (what the pipeline carries), and the
`Loader` Protocol. This mirrors `store/base.py` — the project's other deliberate
abstraction (ADR-005, spec-phase-1.5 Part A). Variation between formats is quarantined
at the front door so `chunk → embed → store → retrieve` never notices the modality.

`RawDoc` deliberately has **no `product_id` field**. A loader therefore *cannot* forge,
drop, or mistype the security tag: `registry.py` derives it from the trusted parent
folder and stamps it in exactly one place. Same philosophy as the entitlement filter —
make the invariant structural rather than a rule each new loader must remember.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RawDoc:
    """One extracted part of a source file — text plus its locator, pre-security-tag.

    `source` must be unique within its product. Chunk ids are `product_id:source:ordinal`
    with `ordinal` restarting per doc, and the store is idempotent-on-id, so two parts
    sharing a `source` produce colliding ids and **silently overwrite** each other. A
    multi-part loader must fully qualify it (`report#p07`, `sales-q1#sheet1#row12`);
    `load_products` asserts it. See spec-phase-1.5 A.3.
    """

    text: str
    source: str


@dataclass(frozen=True, slots=True)
class SourceDoc:
    """One ingested document, pre-chunking — a `RawDoc` stamped with its product."""

    text: str
    product_id: str
    source: str


class Loader(Protocol):
    """Extract one file into one or more `RawDoc` parts."""

    def load(self, path: Path) -> Iterable[RawDoc]:
        """Yield each part of `path`.

        One part for prose; one per page/row/segment where provenance demands it. That
        granularity is each loader's own documented call — the seam permits fine-grained
        parts, it does not mandate them (spec-phase-1.5 A.1).
        """
        ...
