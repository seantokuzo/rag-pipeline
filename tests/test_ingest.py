"""Ingest loader-seam tests — the invariants that keep chunk ids and the security tag sound.

The Phase-1 `.txt` behavior is already pinned end-to-end by the leak + eval suites (same
990 chunks, same ids). What is *new* at the seam — and what these cover — is the
dispatcher's job: stamping `product_id` from the trusted folder, refusing files it can't
attribute to a product, skipping unsupported files loudly rather than silently, and
catching the `(product_id, source)` collision that would otherwise overwrite rows in the
store with no error at all (spec-phase-1.5 A.3).
"""

from dataclasses import dataclass
from pathlib import Path

import pytest

from rag_exp.ingest import RawDoc, TextLoader, load_products


class _MultiPartLoader:
    """Fake loader yielding one `RawDoc` per configured source — stands in for a PDF/CSV."""

    def __init__(self, sources: list[str]) -> None:
        self._sources = sources

    def load(self, path: Path) -> list[RawDoc]:
        return [RawDoc(text=f"text of {s}", source=s) for s in self._sources]


class _PerProductLoader:
    """Fake loader whose emitted `source` depends on which product folder the file sits in."""

    def __init__(self, source_by_product: dict[str, str]) -> None:
        self._source_by_product = source_by_product

    def load(self, path: Path) -> list[RawDoc]:
        return [RawDoc(text="x", source=self._source_by_product[path.parent.name])]


@dataclass(frozen=True, slots=True)
class _ForgedDoc:
    """A loader-supplied record that carries its own `product_id` — must be ignored."""

    text: str
    source: str
    product_id: str


class _ForgingLoader:
    """A loader that tries to dictate its own `product_id`.

    `Loader` is a `typing.Protocol` — structural, with **no runtime enforcement** — so
    nothing stops a loader from returning a record type of its own that carries a
    `product_id`. Returning `RawDoc` (which has no such field) proves only that the
    dispatcher stamps *something*; it takes a loader that actively tries to forge the tag
    to prove the dispatcher's stamp *wins*. That is the seam's central claim.
    """

    def load(self, path: Path) -> list[_ForgedDoc]:
        return [_ForgedDoc(text="smuggled text", source="doc", product_id="shakespeare")]


def _product_file(root: Path, product: str, name: str) -> None:
    """Create `root/<product>/<name>` (content is irrelevant — fake loaders ignore it)."""
    folder = root / product
    folder.mkdir(exist_ok=True)
    (folder / name).write_text("unused", encoding="utf-8")


def test_multi_part_loader_gets_every_part_stamped_from_the_folder(tmp_path: Path) -> None:
    """A loader supplies text + source; the dispatcher — and only it — supplies product_id."""
    _product_file(tmp_path, "detective", "doc.fake")

    docs = load_products(tmp_path, loaders={".fake": _MultiPartLoader(["doc#p1", "doc#p2"])})

    assert [d.source for d in docs] == ["doc#p1", "doc#p2"]
    assert {d.product_id for d in docs} == {"detective"}


def test_loader_cannot_forge_product_id(tmp_path: Path) -> None:
    """The seam's central claim: the trusted folder decides product_id, never the loader."""
    _product_file(tmp_path, "detective", "doc.fake")

    docs = load_products(tmp_path, loaders={".fake": _ForgingLoader()})

    # The loader's text IS used — only its attempt to set the security tag is ignored.
    assert [d.text for d in docs] == ["smuggled text"]
    assert {d.product_id for d in docs} == {"detective"}


def test_colliding_id_prefix_across_products_is_a_hard_error(tmp_path: Path) -> None:
    """Uniqueness keys on the id PREFIX, not the (product_id, source) tuple.

    `("detective", "x:y")` and `("detective:x", "y")` are distinct tuples but concatenate
    to the same chunk id `detective:x:y:0` — a tuple-keyed check would wave them through.
    """
    _product_file(tmp_path, "detective", "a.fake")
    _product_file(tmp_path, "detective:x", "b.fake")

    loader = _PerProductLoader({"detective": "x:y", "detective:x": "y"})

    with pytest.raises(ValueError, match="duplicate chunk-id prefix"):
        load_products(tmp_path, loaders={".fake": loader})


def test_duplicate_source_within_one_file_is_a_hard_error(tmp_path: Path) -> None:
    """Two parts sharing a source would collide on chunk id and silently overwrite."""
    _product_file(tmp_path, "detective", "doc.fake")

    with pytest.raises(ValueError, match="duplicate"):
        load_products(tmp_path, loaders={".fake": _MultiPartLoader(["doc#p1", "doc#p1"])})


def test_duplicate_source_across_two_files_is_a_hard_error(tmp_path: Path) -> None:
    """Uniqueness is asserted per product, not per file — two files can collide too."""
    _product_file(tmp_path, "detective", "a.fake")
    _product_file(tmp_path, "detective", "b.fake")

    with pytest.raises(ValueError, match="duplicate"):
        load_products(tmp_path, loaders={".fake": _MultiPartLoader(["shared"])})


def test_same_source_in_different_products_is_fine(tmp_path: Path) -> None:
    """Chunk ids are namespaced by product_id, so the pair is what must be unique."""
    _product_file(tmp_path, "detective", "doc.fake")
    _product_file(tmp_path, "science", "doc.fake")

    docs = load_products(tmp_path, loaders={".fake": _MultiPartLoader(["shared"])})

    assert {(d.product_id, d.source) for d in docs} == {
        ("detective", "shared"),
        ("science", "shared"),
    }


def test_supported_file_at_the_root_is_a_hard_error(tmp_path: Path) -> None:
    """No parent product folder means no derivable product_id — an un-securable doc."""
    (tmp_path / "loose.fake").write_text("unused", encoding="utf-8")

    with pytest.raises(ValueError, match="cannot derive product_id"):
        load_products(tmp_path, loaders={".fake": _MultiPartLoader(["loose"])})


def test_unsupported_extension_is_skipped_not_an_error(tmp_path: Path) -> None:
    """The real corpus keeps a README.md in every product folder — those must not blow up."""
    _product_file(tmp_path, "detective", "doc.fake")
    _product_file(tmp_path, "detective", "README.md")

    docs = load_products(tmp_path, loaders={".fake": _MultiPartLoader(["doc"])})

    assert [d.source for d in docs] == ["doc"]


def test_text_loader_returns_one_part_and_trims_gutenberg(tmp_path: Path) -> None:
    """One part per file is what keeps the refactor byte-identical to Phase 1 (A.1)."""
    book = tmp_path / "book.txt"
    book.write_text(
        "front matter\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK TEST ***\n"
        "the real text\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK TEST ***\n"
        "license blurb\n",
        encoding="utf-8",
    )

    parts = TextLoader().load(book)

    assert len(parts) == 1
    assert parts[0].text == "the real text"
    assert parts[0].source == "book"
