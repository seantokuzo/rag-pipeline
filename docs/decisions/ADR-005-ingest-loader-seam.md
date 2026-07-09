# ADR-005: Ingestion loader seam for multi-format sources

**Status:** Proposed
**Date:** 2026-07-05
**Supersedes:** none
**Superseded by:** none

## Context

Phase 1 ingests one modality: `products/<product>/*.txt` → `ingest.py:load_products()` → `SourceDoc{text, product_id, source}`. That single hard-coded path was right for the leak lesson, but it leaves a stated goal unproven. **Design Principle #5** (PLANNING.md) asserts the pipeline "doesn't care about source modality" — a claim currently backed by zero non-text sources.

Phase 1.5 (queued, between Phase 1 and Phase 2) sets out to *prove* it by ingesting Excel/CSV, PDF (text + scanned/OCR), and — as small spikes — audio and video. The forces:

1. **Where does modality-specific code live?** A PDF needs page extraction and an OCR fork; an `.xlsx` needs a row→text serialization decision; audio needs ASR + timestamps. None of that belongs in `chunk`/`embed`/`store`/`retrieve` — those must stay byte-for-byte identical (that identity *is* the lesson). So the variation has to be quarantined at the *front door*.

2. **Is a second abstraction justified?** PLANNING.md Principle #3 says "the only abstraction we build is the vector-store seam." Adding a loader abstraction amends that principle, so it must clear the same bar the store seam did: **3+ real implementations sharing one contract, never speculation.** Phase 1.5 has at least four concrete loaders (text, tabular, pdf, audio); video is largely "extract the audio track, reuse audio." It clears the bar — a real seam, not a premature one.

3. **The security invariant must not notice.** Every chunk, whatever its source, is `product_id`-stamped at ingest and entitlement-filtered at query. Multi-format is, in effect, the strongest test of the access-control model: the cross-tenant leak test should pass unchanged over a transcribed-audio chunk.

4. **Metadata provenance grows.** `{product_id, source}` is enough for prose; a PDF chunk wants `page`, a spreadsheet row wants `sheet`/`row`, an audio/video chunk wants a `[start,end]` `timestamp` — which is exactly the hook the roadmap's transcript "video product" needs for deep-links/citations.

## Decision

**We will introduce a second deliberate abstraction — an ingestion loader seam — in Phase 1.5, and route every source modality through it into the unchanged downstream pipeline.**

- An `ingest/` package (mirroring `store/`) with a `Loader` **Protocol** — one method, `load(path) -> SourceDoc` (or an iterable of them) — and one concrete loader per format: `text.py`, `tabular.py`, `pdf.py`, `audio.py` (video reuses `audio` after an `ffmpeg` audio-track extract). Selection is by file extension.
- The current `.txt` path is extracted **behind the Protocol first, with no behavior change** (the leak test + eval must stay green), before any new format is added — the refactor proves the seam in isolation.
- `SourceDoc`/`Chunk` metadata grows to carry optional provenance (`page` | `sheet`/`row` | `timestamp`) alongside `{product_id, source}`. `product_id` stays mandatory and un-negotiable — an unlabelled chunk is un-securable regardless of source.
- **Scope is "Option A":** tabular + PDF (text + OCR) are built out and evaluated locally; audio and video are *small spikes* (`faster-whisper tiny` on a ~60s clip; `ffmpeg` audio extract) to feel ASR + timestamped chunks. **Production-scale audio/video is deferred to Phase 2**, on Azure AI Speech / Video Indexer, where it is genuinely production-grade — this phase is the on-ramp, not the destination.

**Deliberately left open until build time** (kept out of this ADR per the README's "gravestone, not debate" rule — tracked in PLANNING.md → Open Questions): the exact `Loader` signature (single vs iterable return), whether metadata becomes typed-field growth vs a flexible `dict`, the row→sentence serialization for tables, and per-format library pins — the last gated on an **x86_64-macOS wheel probe** (`pymupdf`, `ctranslate2`/`faster-whisper`, Tesseract bindings), the same wheel-wall that produced ADR-003.

## Alternatives considered

- **Dispatch-by-extension inside a fatter `ingest.py` (no package, no Protocol).** Rejected: four+ format branches with private helpers in one module is the "god module" anti-pattern, and it offers no clean injection point for per-format tests. The seam costs little and pays in isolation + testability. (Three similar lines beat a bad abstraction — but four real loaders sharing a contract *is* the good abstraction.)
- **Defer multi-format entirely to Phase 2 (let Azure Document Intelligence / Speech / Video Indexer do it).** Rejected as the *primary* path: the learning goal is to understand what those services *do* by hand-rolling a scrappy version first (the lab's whole pedagogy). Partially adopted, though — audio/video *production-scale* genuinely is deferred to Azure (Option A), because CPU Whisper on an Intel Mac is too slow to be the main path and Azure is where they are real.
- **One universal "smart" loader (e.g. `unstructured` / LangChain document loaders).** Rejected for Phase 1.5: a heavy dependency that hides the very mechanics we are here to learn (and drags its own x86_64-macOS wheel risk). Hand-rolled per-format loaders keep the extraction visible. Revisit for Phase 2 if a batteries-included loader earns its keep.
- **Grow metadata as a free-form `dict` now.** Deferred, not rejected: typed provenance fields are clearer while there are few of them; a flexible dict is the documented upgrade if the field set sprawls. Resolve at build time.

## Consequences

### Positive
- Design Principle #5 stops being an assertion and becomes a passing test: the cross-tenant leak test green over a transcribed-audio chunk *proves* modality-blind access control.
- Variation is quarantined at the front door; `chunk`/`embed`/`store`/`retrieve` and the security invariant are untouched — the store seam and the loader seam are the only two places phase/modality changes land.
- Timestamped audio/video metadata is exactly the substrate the roadmap's transcript "video product" (and citation deep-links) needs.
- Each hand-rolled loader is a concept-primer for its Azure twin — the phase is a deliberate on-ramp to Phase 2.

### Negative
- A second abstraction is real surface area and amends the "only one seam" principle — justified only because 4+ concrete loaders exist; it must not metastasize into speculative "any source" plugin machinery.
- OCR and ASR introduce *extraction quality* as a new error source upstream of retrieval — good to learn, but it means a bad chunk can now come from a bad transcription, not just bad chunking. (The eval harness is the guard: measure it.)
- Intel-Mac wheel risk on `pymupdf`/`ctranslate2`/Tesseract could force tool substitutions or push a format toward the Azure-only column.

### Neutral
- Adds no code until Phase 1.5 (this ADR is Proposed; realized after build-order step 11). `ingest.py`, `chunk.py`, the store, and security are unchanged today.
- The metadata-schema growth touches `Chunk`/`Hit` and the store's per-row metadata write, but Chroma already accepts arbitrary scalar metadata, so it is additive.

## Links
- `docs/PLANNING.md` — Phase 1.5 section (goal, loader seam, build order, Azure twins, Intel-Mac caveat); Design Principles #3 (amended — two seams) + #5 (realized); Open Questions (the deferred specifics).
- ADR-002 — pooled access control: the invariant this seam must preserve across modalities.
- ADR-003 — Intel-Mac (x86_64) wheel caps: the precedent for probing `pymupdf`/`faster-whisper`/Tesseract wheels before pinning.
- ADR-004 — eval methodology: the harness that measures extraction/serialization quality (quote-containment relevance works over OCR/transcript text too).
- `docs/SECURITY.md` — the cross-tenant invariant that must pass over non-text sources.
- `src/rag_exp/store/base.py` — the sibling seam (`VectorStore` Protocol) this one mirrors.
