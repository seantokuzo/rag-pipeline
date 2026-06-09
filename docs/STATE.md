# Session State

> Current state of the project. Updated every session. **Read this first when resuming.**

**Last Updated:** 2026-06-09 — **Phase 1 (Session 4) — step 4 (embed) DONE.** `src/rag_exp/embed.py` written: `Embedder` over bge-small (CPU, `normalize_embeddings=True`) with `embed_documents()→encode_document()` (bare passages) and `embed_query()→encode_query()` (query instruction prepended). **Key finding:** bge-small ships **no** sentence-transformers prompts config, so `encode_query()` adds nothing by default — we **register** bge's documented query instruction ourselves (`config.QUERY_PROMPT`, "Option A"); verified the asymmetry fires (doc-vs-query cosine **0.9424**, not 1.0). Ran the deferred **bge 512-token truncation check** on all 990 chunks: max 520, **2 chunks over 512** (`detective:…:107`, `:146`) → **accepted** (Option 1, learning-lab call): full text is stored, only those 2 vectors drop ~6 tail tokens. Vectors (990, 384), unit-norm 1.000000 & deterministic. ruff-clean; `embedding.md` corrected. **Step 5 (store/chroma) is next.** _Prior:_ step 3 chunk (Session 3), steps 1–2 env+corpus+config+ingest (Session 2), Phase 0 (Session 1).

**Repo:** https://github.com/seantokuzo/rag-pipeline — work on branch `phase-1/env-and-corpus` (Session 2, pushed); `main` has Phase 0 scaffolding.

---

## Current Phase

**Phase 0 — Scaffolding: done.** **Phase 1 — Local pipeline: in-progress** — steps 1–4 of 11 done (env + corpus; config + ingest; chunk; embed); **step 5 (store/chroma) next.**

### ⏭️ Fresh-session handoff — resume here

**What's done:** Phase 0 scaffolding (Session 1) + Phase 1 steps 1–2 (Session 2 — env/ADR-003 caps, corpus, `config.py` + `ingest.py`) + step 3 (Session 3 — `chunk.py` → **990 chunks**) + step 4 (Session 4 — `embed.py`: `Embedder` over bge-small with the registered query prompt; asymmetry verified; 512-token check run, 2 over-cap chunks accepted). Steps 1–2 pushed; steps 3–4 committed locally on `phase-1/env-and-corpus`. Nothing to finish in steps 1–4.

**▶ ACTIVE — Phase 1, the local pipeline. The spec is `docs/spec-phase-1.md` — read it; it's the binding build order.** Build order (each ≈ one commit): ~~1) corpus prep~~ ✅ · ~~2) config+ingest~~ ✅ · ~~3) chunk~~ ✅ · ~~4) embed~~ ✅ · **5) store/chroma ◀ next** · 6) index · 7) security · 8) retrieve · 9) **leak demo** · 10) eval + cross-tenant test · 11) poke experiments.

**▷ NEXT STEP — store/chroma (Phase 1, step 5). Read `docs/spec-phase-1.md` Part D + `docs/explainers/vector-store.md` FIRST.**
1. **`store/` package — the one real abstraction:** `store/base.py` defines a `VectorStore` Protocol (`upsert(chunks, embeddings)` / `query(embedding, k, where) -> list[Hit]`; `Hit = {id, text, product_id, source, score}`), `store/chroma.py` implements it. Phase 2 adds `azure.py` behind the same Protocol — pipeline + security invariant stay put.
2. **Chroma specifics:** `chromadb.PersistentClient(path=str(CHROMA_PATH))` → `get_or_create_collection(COLLECTION, metadata={"hnsw:space": SPACE})` — ⚠️ **cosine, not L2** (Chroma defaults to L2). `col.add(ids, embeddings, documents, metadatas=[{"product_id","source"}])` — **stamp product_id/source on every row** (un-securable otherwise). `col.query(query_embeddings=[emb], n_results=k, where=...)` — `where` is the entitlement pre-filter (step 7 builds it server-side; the store just passes it through, never invents it).
3. **Don't** post-filter, don't accept a caller filter here, don't let L2 sneak in. Map Chroma's cosine *distance* → a `score` in `Hit` (smaller distance = closer; pick distance vs `1 − distance` and document the choice).

**Inputs ready:** `from rag_exp.embed import Embedder` → `embed_documents(texts) -> list[list[float]]` (384-dim, unit-norm, 1:1 with chunks); `from rag_exp.chunk import chunk_documents` + `from rag_exp.ingest import load_products` → **990 `Chunk`s**; `from rag_exp.config import CHROMA_PATH, COLLECTION, SPACE, K`.

**Env is READY** — `uv run …` works; do NOT re-run install or corpus download. The bge-small model is **cached** from step 4 (no re-download).

**Remember the working style:** this is a learning collaboration — explain Python/RAG choices, move one step at a time, present options at decision points, don't autonomously build the whole phase. **Explainer ritual:** before a handoff the human may ask "how does the next step work" — explain in-session *and* write/update `docs/explainers/<concept>.md` (see that folder's README). **Env gotcha:** complex `&&`/loop bash chains have silently died mid-run on this box — prefer simple single-statement commands (git multi-statement scripts are fine).

### Source of truth (obey these, in order)
- `docs/spec-phase-1.md` — **the** binding build spec for what we're doing now.
- `docs/SECURITY.md` — the access-control invariant any retrieval/security code must satisfy.
- `CLAUDE.md` — conventions, tech stack, quality gates, anti-patterns, local review priorities.
- `docs/PLANNING.md` — architecture + the two-phase roadmap.
- `docs/SESSION-GUIDE.md` — how to drive these sessions (operator playbook + kickoff prompts).

### Locked decisions (supersede any older prose)
1. **Stack** (ADR-001): Chroma `PersistentClient` + sentence-transformers `bge-small-en-v1.5` (CPU, normalized, **cosine**) + uv/ruff/pytest + langchain-text-splitters/tiktoken. _Don't re-litigate._
2. **Access control** (ADR-002): **pooled** model — one collection, server-side `product_id` **pre-filter**. The filter is the lesson.
3. **Review** is **local-first** — `/code-review` skill + `@agent-access-control-reviewer`. No GitHub Actions tiers (deliberate departure from the global PR-review loop). Revisit only if we push to GitHub.
4. **Layout:** subagents in native `.claude/agents/` (directly spawnable via `@agent-`); **skills in `.agents/skills/`** for skills.sh / `npx skills` compatibility — Claude Code won't auto-discover them there, so read them with the Read tool (per the global skill-loading protocol).
5. **Chunking**: recursive, **512 tokens, no overlap** to start.
6. **Intel-Mac caps** (ADR-003): local env pins torch≤2.2.2 / numpy<2 / transformers<5 / onnxruntime≤1.23.2 (the last x86_64-macOS-installable set); ST stays 5.5.1.

### Gotchas carried forward
- **Cosine, not L2** — set `metadata={"hnsw:space":"cosine"}` on the Chroma collection (L2 is the default).
- **Embedding parity** — same model/normalization/prompt both sides; `encode_document()` for chunks, `encode_query()` for queries. ⚠️ **bge-small ships no prompts config**, so `encode_query()` adds nothing by default — `Embedder` registers `config.QUERY_PROMPT` ("Represent this sentence for searching relevant passages: ") so the asymmetric prefix actually fires (verified: doc-vs-query cosine 0.9424). **Don't remove the registration** or the asymmetry silently dies.
- **Metadata on every chunk** — stamp `{product_id, source}` at ingestion; an unlabeled chunk is un-securable (hard error).
- **Chunk size ≤ 512 tokens** (bge-small max sequence) or text is silently truncated at embed time. **Verified at step 4:** tiktoken sizing leaks vs bge's WordPiece count — **2/990 chunks** are 513–520 bge tokens (`detective:…:107`, `:146`) and **accepted** (full text stored; only those 2 vectors drop ~6 tail tokens). `Embedder.count_tokens()` is the real check; airtight fix (if eval ever needs it) = size with bge's own tokenizer.
- **Mandatory cross-tenant leak test** the moment `security.py` + `retrieve.py` exist — a green suite without it is false safety.
- **Trim Gutenberg boilerplate** (`*** START/END OF THE PROJECT GUTENBERG EBOOK ***`) at ingest — markers are at line 27 / the END line in all 3 books. (Done in `ingest.py`.)
- **Science front-matter — LEAVE IT (locked, Session 2).** `products/science/...` keeps a ~9-line Gutenberg "several editions" catalog note at the very top (lands in science's chunk 0). Decided to leave it: benign, never retrieved by content queries, and stripping would be a book-specific hack. **Do NOT strip it later** — re-trimming shifts chunk ids and breaks the golden set. (Title pages / TOCs are kept across all 3 books for consistency.)
- **`.env` never committed** (git-ignored; the `pre-tool-security` hook blocks secret-file edits). `.env.example` is the template.
- **Stable chunk ids** (`product_id:source:ordinal`) — the eval golden set depends on them surviving re-indexing.
- **Intel-Mac (x86_64) dep caps** (ADR-003) — **don't bump** `torch`/`numpy`/`transformers`/`onnxruntime` past the caps locally; they're the last x86_64-macOS wheels. `encode_query`/`encode_document` (ST 5.5.1) intact.

### Do NOT
- Skip the cross-tenant leak test.
- Accept a `product_id`/filter from the caller into the query without AND-ing it under the server-side entitlement filter.
- Post-filter for entitlements.
- Guess dependency versions — let `uv` resolve.
- Build Phase 2 (Azure) or a generation/LLM step yet — both are out of scope for Phase 1.
- Re-run env install / corpus download — steps 1–2 are done.
- Strip the science front-matter note (see Gotchas — locked as leave-it).

---

## What Exists Today
- **Governance:** `CLAUDE.md` (master), `docs/PLANNING.md`, `docs/SECURITY.md`, `docs/spec-phase-1.md`, `docs/SESSION-GUIDE.md`.
- **Knowledge capture:** `docs/decisions/` (ADR system + ADR-001, ADR-002, ADR-003), `docs/history/` (retrospective log + template).
- **Claude Code:** `.claude/settings.json` (wires 3 hooks), `.claude/hooks/` (pre-tool-security, post-edit-format→ruff, post-response-notify→Stop, with ntfy mobile option), `.claude/rules/` (planning-doc-homes, access-control, rag-conventions), `.claude/agents/` (access-control-reviewer, rag-researcher), `.agents/skills/` (rag-eval-harness, chunking-lab, find-skills, roadmap-management), `.claude/templates/agent-TEMPLATE.md`.
- **Python:** `pyproject.toml` (uv, src layout, pinned deps, `[tool.uv]` Intel-Mac caps), `.python-version`, `.gitignore`, `.env.example`, `README.md`, `src/rag_exp/{__init__,config,ingest,chunk}.py`, `tests/__init__.py`. `uv.lock` committed; `.venv` provisioned (Python 3.12.13).
- **Corpus:** `products/{detective,shakespeare,science}/` — READMEs + validated Gutenberg `.txt` (Adventures of Sherlock Holmes / Hamlet / On the Origin of Species), committed (public-domain, frozen for stable chunk ids).
- **Pipeline so far:** `config.py` (spec Appendix defaults, project-root paths; now incl. `EMBED_DEVICE`/`NORMALIZE`/`QUERY_PROMPT`) + `ingest.py` (`load_products` → frozen `SourceDoc{text,product_id,source}`, Gutenberg trim, product_id hard-error) + `chunk.py` (`chunk_documents`/`chunk_document` → frozen `Chunk{id,text,product_id,source}` via recursive tiktoken splitter; stable ids, inherited metadata; size/overlap as sweepable kwargs) + `embed.py` (`Embedder` over bge-small CPU; `embed_documents`/`embed_query` parity via registered query prompt; `count_tokens`/`max_seq_length` for the truncation check). Smoke-tested: 3 docs → 990 chunks → (990, 384) unit-norm vectors.
- **Not yet built:** `src/rag_exp/` modules for store / index / security / retrieve (step 5+); no tests yet (the cross-tenant leak test lands with security + retrieve).

## Decisions Made
- ADR-001 — Phase-1 local stack. ADR-002 — pooled access-control model. ADR-003 — Intel-Mac (x86_64) dependency compatibility caps. ADR-004 — eval methodology (source-anchored golden set + cost-tiered sweeps). (See `docs/decisions/`.)
- Split layout: subagents native in `.claude/agents/` (spawnable); skills in `.agents/skills/` for skills.sh compat (see Locked decisions #4).
- Lightweight local-first review over GitHub Actions tiers (see Locked decisions #3).
- **Science corpus front-matter left as-is** (Session 2) — see Gotchas.
- **bge query prompt registered, not assumed-automatic** (Session 4, "Option A") — bge-small ships no ST prompts config, so we register `QUERY_PROMPT` ourselves so the asymmetric query prefix fires; verified by doc-vs-query cosine 0.9424. See Gotchas + `embedding.md`.
- **2 over-512-token chunks accepted, not re-chunked** (Session 4, "Option 1") — learning-lab call; see Gotchas.

## Deferred Items
- Phase 2 (Azure AI Search + Azure OpenAI), hybrid search, reranking, LLM synthesis, the transcript "video" product — all post-Phase-1.
- **Marker-scope the Intel-Mac caps** (ADR-003) to `x86_64-darwin` only, so a future Linux/CI/arm env resolves to a modern stack — adopt when a real Linux target exists (Phase 2 devcontainer / CI).
- Housekeeping: temp dirs `/tmp/rag-research/` + `/tmp/uv-probe/` can be deleted (the `pre-tool-security` hook blocks `rm -rf`, so remove them manually).

---

### Session log
- **2026-06-06 — Session 1 (Phase 0):** Mined `seantokuzo-mcp` + `get-sean-done`; researched 2026 RAG best practices; scaffolded the full RAG/Python workspace + planning/spec docs. Decisions: ADR-001, ADR-002, local-first review, split `.claude/` + `.agents/skills/` layout. Skills moved to `.agents/skills/` for skills.sh compat; `git init` + pushed to github.com/seantokuzo/rag-pipeline (`main`).
- **2026-06-06/07 — Session 2 (Phase 1, steps 1–2):** Step 1 — `uv sync` hit an Intel-Mac (x86_64) wheel wall (onnxruntime via chromadb + torch via sentence-transformers dropped x86_64-macOS wheels; numpy-2 / transformers-5 runtime traps); a probe subagent verified the fix end-to-end → **ADR-003** `[tool.uv]` caps (torch 2.2.2 / numpy 1.26.4 / transformers 4.57.6 / onnxruntime 1.23.2; ST held 5.5.1). Downloaded + validated the 3-product Gutenberg corpus (boilerplate at line 27). Step 2 — wrote `config.py` (spec Appendix defaults, project-root paths) + `ingest.py` (`load_products` → frozen `SourceDoc`, Gutenberg trim, product_id hard-error); ruff-clean, smoke-tested (3 docs). Decided to **leave** the 9-line Gutenberg "several editions" note in the science corpus (benign). Committed + pushed to `phase-1/env-and-corpus`. Handoff → step 3 (chunk).
- **2026-06-07 — Session 3 (Phase 1, step 3 — chunk):** Wrote `chunk.py` — `RecursiveCharacterTextSplitter.from_tiktoken_encoder` (cl100k_base, hard 512-token cap), frozen `Chunk{id,text,product_id,source}`, stable ids `product_id:source:ordinal`, metadata inherited from `SourceDoc`; size/overlap are keyword params so `chunking-lab` can sweep them. Smoke-tested: **990 chunks** (317/563/110), token len 6–510 (mean 396), 0 over cap, ids unique & all stamped. Updated explainers (chunking real-counts + tuning-knobs section; new `embedding.md`); registered embed in the explainer index. Fixed a stray pre-existing E501 in `tests/__init__.py`. Then (prompted by an enterprise-scale question) locked **ADR-004** — eval golden set anchored to **source text/quotes** not chunk ids (survives sweeps), plus a **cost-tiered sweep** methodology (cheap query-time axes first; corpus-sample pre-pass before re-embeds; document-don't-build the embedding cache); realigned spec H.1/Part I/J.2, the chunking-lab + rag-eval-harness skills, and the chunking explainer to match. Handoff → step 4 (embed).
- **2026-06-09 — Session 4 (Phase 1, step 4 — embed):** Wrote `embed.py` — `Embedder` over sentence-transformers bge-small (CPU, `normalize_embeddings=True`); `embed_documents()→encode_document()` (bare passages), `embed_query()→encode_query()` (query instruction prepended). Before writing, **verified the spec's "automatic" claim was false for this model**: `encode_query()` only prefixes if `"query"` is in the model's prompts, and bge-small's `config_sentence_transformers.json` ships no `prompts` key (no `Router` module either) — so out of the box it adds nothing. Chose **Option A**: register `config.QUERY_PROMPT` ("Represent this sentence for searching relevant passages: ", from BAAI's card) on the model. Smoke test (990 chunks): vectors (990, 384), unit-norm 1.000000, deterministic; **asymmetry verified** — doc-vs-query cosine **0.9424**. Ran the deferred **bge 512-token truncation check**: max 520, **2 chunks over** (`detective:…:107`, `:146`) → **accepted** (Option 1: full text stored, only those vectors lose ~6 tail tokens; airtight fix = bge-tokenizer sizing, deferred unless eval needs it). ruff-clean; corrected `embedding.md` (registered-prompt mechanism + truncation result). Handoff → step 5 (store/chroma).
