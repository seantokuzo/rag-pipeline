# Phase 1.5 — Multi-format Ingestion Spec

> Implementation north star for the **ingest loader seam** — the project's second (and last) deliberate abstraction.

**Status:** Spec — step 1 not yet implemented. Binding for **Parts A–C**; **Parts D–F are deliberately thin** (`[probe-gated]`) because their library choices depend on x86_64-macOS wheel probes we have not run. They get filled in at their step, not now.
**Companions:** `docs/PLANNING.md` → Phase 1.5 (roadmap) · **ADR-005** (the seam decision this spec realizes) · `docs/SECURITY.md` (the invariant that must survive every modality) · ADR-003 (the wheel-wall precedent).

---

## 0. Executive summary

Prove **Design Principle #5** — *the pipeline doesn't care about source modality* — by routing new formats through a `Loader` seam at the front door, while `chunk → embed → store → retrieve` and the entitlement filter stay **byte-for-byte unchanged**. The proof is not a demo; it's the **cross-tenant leak test passing green over a non-text source**.

### Locked decisions
| # | Decision | Rationale |
|---|----------|-----------|
| 1 | An `ingest/` **package** with a `Loader` Protocol, mirroring `store/` | ADR-005; 4+ real loaders clear the "3+ implementations" bar |
| 2 | Dispatch **by file extension** | simplest thing that works; no content sniffing until a format forces it |
| 3 | **`load()` returns an iterable** of parts, not a single doc | §A.1 — the only signature that can ever carry page/row/timestamp provenance |
| 4 | Loaders return **`RawDoc`**, never `SourceDoc`; the dispatcher stamps `product_id` | §A.2 — a loader *structurally cannot* forge or drop the security tag |
| 5 | Step 1 is a **pure refactor** with a green-tests contract | prove the seam in isolation before any format lands on it |
| 6 | Scope = **ADR-005 "Option A"** | tabular + PDF built out; audio/video are spikes; production-scale → Phase 2 (Azure) |

### Non-goals (explicitly out)
A universal/"smart" loader (`unstructured`, LangChain loaders — ADR-005 rejected it: hides the mechanics we're here to learn). Production-scale ASR. Visual-tier video (keyframes / slide-OCR). Any change to `chunk`/`embed`/`store`/`retrieve`/`security` — **if a step needs to touch those, stop and re-spec.**

### Build order (each step ≈ one atomic commit)
1. **refactor `ingest.py` → `ingest/`** ← *binding, §Part C* · 2. tabular · 3. PDF text layer · 4. PDF scanned (OCR) · 5. audio spike · 6. video spike

---

## Part A — The loader seam (binding)

### A.0 Scope
Defines the contract every format implements and the two invariants that keep the security model and the chunk-id scheme intact. This part is binding for **all six steps**.

### A.1 Why `load()` returns an iterable

A `.txt` book is one document. A PDF is *N* pages, a spreadsheet is *N* rows, a transcript is *N* timestamped segments — and ADR-005 wants `page` / `sheet`+`row` / `timestamp` provenance on the resulting chunks. A single-return signature can only carry that by smuggling markers into the text or bolting on an offset map; the iterable carries it natively.

It also costs nothing today: **the text loader yields exactly one part per file**, so step 1 produces the same 990 chunks with the same ids. Choosing the single-return signature now would force a breaking Protocol change at step 2 or 3 — precisely what the "prove the seam first" refactor exists to avoid.

> **The signature permits fine granularity; it does not mandate it.** Whether a prose PDF is one part per *page* (clean page numbers, but chunks never span a page break — every page boundary becomes a mid-sentence cut) or one part per *file* (chunks flow naturally, page numbers need an offset map) is a **per-loader editorial call, made and documented at that loader's step** — and it is measurable on the eval harness (Principle #2: measure, don't assume).

### A.2 The contract

```python
# ingest/base.py
@dataclass(frozen=True, slots=True)
class RawDoc:
    """What a loader produces: extracted text + its own provenance. NO product_id."""
    text: str
    source: str          # unique locator within the product — see A.3

@dataclass(frozen=True, slots=True)
class SourceDoc:         # unchanged from Phase 1
    text: str
    product_id: str      # stamped by the dispatcher, never by a loader
    source: str

class Loader(Protocol):
    def load(self, path: Path) -> Iterable[RawDoc]: ...
```

**Invariant 1 — `product_id` is un-forgeable by a loader.** `RawDoc` has no `product_id` field, so a loader *cannot* set one, drop one, or get one wrong. The dispatcher derives it from the immediate parent folder (the trusted source, exactly as Phase 1 does) and stamps it in **one place**. This is the same philosophy as the entitlement filter: make the invariant structural, not a rule each new loader must remember to honor. It also strictly improves on ADR-005's phrasing ("every loader must stamp `product_id`") — now none of them can fail to.

**Invariant 2 — `(product_id, source)` must be globally unique per run.** See A.3. Violation is a **hard error**, never a warning.

### A.3 ⚠️ The chunk-id collision landmine

`chunk.py:56` builds ids as `f"{product_id}:{source}:{ordinal}"` where `ordinal` **restarts at 0 for every `SourceDoc`**. `ChromaStore.upsert()` is idempotent-on-id by design. Therefore:

> Two `SourceDoc`s sharing a `(product_id, source)` pair produce **colliding chunk ids**, and Chroma **silently overwrites** — no exception, no warning, rows just vanish from the index.

This never fired in Phase 1 (one file → one doc → `source` = the filename stem, unique by filesystem). The moment a loader yields multiple parts it is live. Mitigation, binding on every loader:

- A multi-part loader **must** emit a unique `source` per part — a fully-qualified locator, e.g. `sales-q1#sheet1#row12`, `report#p07`, `interview#t0031`.
- `load_products()` **must** assert that the **id prefix `f"{product_id}:{source}"`** is globally unique across the run, and raise `ValueError` naming the duplicate. Key on the *concatenation*, not a `(product_id, source)` tuple — distinct tuples can still concatenate to the same id (`("a", "x:y")` and `("a:x", "y")` both yield `a:x:y:0`), so only the prefix key is injective with the id scheme.
- Tests pin this: duplicate `source` within one file, across two files in one product, and a cross-product prefix collision must each raise; the same `source` under *different* products must be legal.

### A.4 Provenance metadata — `[open, resolve at step 2]`
ADR-005 left the shape open: **typed optional fields** on `RawDoc`/`Chunk` vs a **flexible `dict`**. Decide at step 2 (tabular — the first real need), not now. Constraint to carry in: **Chroma metadata values must be scalars** (`str`/`int`/`float`/`bool`), so a nested dict has to be flattened or serialized at the store boundary either way.

---

## Part B — What must not change (binding, all steps)

| Frozen | Why |
|---|---|
| `chunk.py`, `embed.py`, `store/**`, `retrieve.py`, `security.py` | their identity across modalities **is** the lesson |
| The chunk id scheme `product_id:source:ordinal` | the golden set resolves against it |
| `from rag_exp.ingest import SourceDoc` as an import path | `chunk.py:17` + `eval.py` depend on it; the package `__init__` re-exports so every call site is untouched |
| `product_id` derived from the parent folder, mandatory, hard-error if underivable | SECURITY.md; the un-securable-chunk rule |

**Acceptance gate for the phase:** a mixed-format product ingests end-to-end · the **cross-tenant leak test passes over a non-text source** · one write-up per format in `docs/history/` · extraction/serialization choices scored on the eval harness where applicable.

---

## Part C — Step 1: refactor `ingest.py` → `ingest/` (binding)

### C.0 Scope
Extract the existing `.txt` path behind the Protocol. **Zero behavior change.** No new format, no new dependency, no provenance fields yet.

### C.1 Target layout
```
src/rag_exp/ingest/
├── __init__.py    # re-exports SourceDoc, RawDoc, Loader, load_products (import paths unchanged)
├── base.py        # RawDoc + SourceDoc + Loader Protocol
├── text.py        # TextLoader — Gutenberg trim, yields exactly ONE RawDoc per file
└── registry.py    # EXTENSION → Loader map + load_products(): walk, dispatch, stamp, verify
```
`registry.py` owns everything security-relevant: the folder→`product_id` derivation, the stray-`.txt` hard error, the `(product_id, source)` uniqueness assert, and the ingest summary log. Per-format code stays dumb about all of it.

### C.2 Acceptance criteria
| # | Check | Expected |
|---|---|---|
| 1 | `chunk_documents(load_products())` | **990 chunks**, ids identical to the live index |
| 2 | `uv run pytest` | **20 GREEN** (8 leak + 12 metric) |
| 3 | `uv run python -m rag_exp.eval` @512/k=5 | **unchanged**: overall hit-rate `0.333` · MRR `0.224` · nDCG `0.251` · exact `0.625` · paraphrase `0.154` |
| 4 | Re-index required? | **No** — ids don't move, so `./.chroma` stays valid (⚠️ eval's `chunk_size` must stay 512 to match it) |
| 5 | `uv run ruff format . && uv run ruff check .` | clean |
| 6 | `@agent-access-control-reviewer` | **PASS — required.** This touches the metadata-stamping path (unlike step 11, which had zero security surface) |
| 7 | New test | duplicate-`source` two-part loader → `ValueError` (pins A.3) |

---

## Part D — Step 2: tabular `[probe-gated: library]`

CSV via stdlib `csv`; `.xlsx` via `openpyxl` (**probe x86_64-macOS wheels before pinning**). Decisions due **at this step**: the row→text serialization (row-as-sentence with header context is the working hypothesis — *measure it*), the granularity call (one `RawDoc` per row vs per sheet), and A.4's provenance shape. Metadata: `sheet`, `row`. `source` must be fully qualified per A.3.

## Part E — Steps 3–4: PDF, text layer then scanned `[probe-gated: library]`

`pypdf` vs `pymupdf` (**ADR-003 redux — `pymupdf` wheel probe first**); then a Tesseract OCR fork when no text layer is detected. Page-level provenance; the per-page-vs-per-file granularity call from A.1 gets **decided by measurement** here. Layout gotchas (columns, headers/footers, tables) and OCR quality → `docs/history/`. Azure twin: Document Intelligence.

## Part F — Steps 5–6: audio + video spikes `[probe-gated: library]`

`faster-whisper` (`tiny`/`base`) on a ~60s clip → transcript + segment timestamps (**`ctranslate2` wheel probe first — the likeliest wall**); then `ffmpeg` audio extract reusing the audio loader. Small and scrappy on purpose: feel ASR + timestamped chunks. `[start, end]` timestamps are the hook the roadmap's transcript "video product" needs. Azure twins: AI Speech / Video Indexer.

---

## Part G — Open questions

| # | Question | Due |
|---|---|---|
| 1 | **Corpus strategy:** do new-format files go in a **new product folder** or into the **existing three**? Chunk ids are per-`source`, so existing ids are safe either way — **but the pooled collection means new rows compete in every query, so the `0.333` baseline moves for reasons unrelated to extraction quality.** New product = comparable baseline; existing product = a more realistic mixed-format product, but re-baseline first and say so. | **before step 2** |
| 2 | Provenance shape: typed fields vs `dict` (A.4) | step 2 |
| 3 | Granularity per loader: per-page/row/segment vs per-file (A.1) | each loader's step |
| 4 | Which format carries the **non-text leak test** (acceptance gate)? Cheapest credible candidate: tabular — no wheel risk, lands at step 2 | step 2 |
| 5 | Per-format library pins | each step, post-probe |

## Part H — Gotchas carried in

- **Intel-Mac wheel wall (ADR-003)** — `pymupdf`, `ctranslate2`/`faster-whisper`, Tesseract bindings all need an **x86_64-macOS probe BEFORE pinning**. Probe with `rag-researcher` or a throwaway `uv` env; never hand-pin from memory.
- **Extraction quality is a NEW upstream error source.** After this phase a bad chunk can come from bad OCR/ASR, not just bad chunking. The eval harness is the guard — measure, don't assume.
- **Eval lockstep footgun (still live)** — `run_eval`'s `chunk_size` must match the size the index was built at, or every query scores ~0 and it looks like broken retrieval.
- **Never exceed `chunk_size=512`** (bge-small max sequence) — proven at step 11: the text is stored whole so a quote still *resolves*, but the vector is tail-truncated. Resolution ≠ retrieval.
</content>
</invoke>
