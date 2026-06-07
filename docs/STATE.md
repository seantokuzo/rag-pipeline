# Session State

> Current state of the project. Updated every session. **Read this first when resuming.**

**Last Updated:** 2026-06-06 — **Phase 1 (Session 2) — step 1 (environment + corpus) DONE.** `uv` env provisioned (CPython 3.12.13) with **Intel-Mac x86_64 compatibility caps** (ADR-003: torch 2.2.2 / numpy 1.26.4 / transformers 4.57.6 / onnxruntime 1.23.2; sentence-transformers held at 5.5.1). The 3-product Gutenberg corpus is downloaded + validated. No pipeline code yet — **step 2 (config + ingest) is next.** _Prior:_ Phase 0 scaffolding complete (Session 1).

**Repo:** https://github.com/seantokuzo/rag-pipeline — work on branch `phase-1/env-and-corpus` (Session 2); `main` has Phase 0 scaffolding.

---

## Current Phase

**Phase 0 — Scaffolding: done.** **Phase 1 — Local pipeline: in-progress** — step 1 of 11 (environment + corpus) done; **step 2 (config + ingest) next.**

### ⏭️ Fresh-session handoff — resume here

**What's done:** Phase 0 scaffolding (Session 1) + Phase 1 step 1 (Session 2 — env provisioned, deps installed with Intel-Mac caps per ADR-003, corpus downloaded + validated). Nothing to finish in step 1.

**▶ ACTIVE — Phase 1, the local pipeline. The spec is `docs/spec-phase-1.md` — read it; it's the binding build order.** Build order (each ≈ one commit): ~~1) corpus prep~~ ✅ · **2) config+ingest ◀ next** · 3) chunk · 4) embed · 5) store/chroma · 6) index · 7) security · 8) retrieve · 9) **leak demo** · 10) eval + cross-tenant test · 11) poke experiments.

**▷ NEXT STEP — config + ingest (Phase 1, step 2), the first real Python:**
1. **`config`** — the Appendix defaults from the spec (`COLLECTION="corpus"`, `MODEL="BAAI/bge-small-en-v1.5"`, `CHUNK_SIZE=512`, `CHUNK_OVERLAP=0`, `K=5`, `SPACE="cosine"`, `CHROMA_PATH="./.chroma"`, `PRODUCTS_ROOT="./products"`).
2. **`ingest`** — `load_products(root: Path) -> list[SourceDoc]` walks `products/*/*.txt`, derives `product_id` from the folder name, reads UTF-8, **trims Gutenberg boilerplate** (START/END markers sit at line 27 / the END line in all 3 books), and hard-errors on a folder whose `product_id` can't be derived (spec T4). `SourceDoc = {text, product_id, source}`.
3. Then step 3 (chunk) per the spec.

**Env is READY** — `uv run …` works; do NOT re-run install or corpus download. ⚠️ The first embed run (step 4) still downloads the `bge-small` model (~130 MB).

**Remember the working style:** this is a learning collaboration — explain Python/RAG choices, move one step at a time, present options at decision points, don't autonomously build the whole phase. **Env gotcha:** complex `&&`/loop bash chains have silently died mid-run on this box — prefer simple single-statement commands.

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
- **Embedding parity** — same model/normalization/prompt both sides; `encode_document()` for chunks, `encode_query()` for queries (bge-small has an asymmetric query prefix).
- **Metadata on every chunk** — stamp `{product_id, source}` at ingestion; an unlabeled chunk is un-securable (hard error).
- **Chunk size ≤ 512 tokens** (bge-small max sequence) or text is silently truncated at embed time.
- **Mandatory cross-tenant leak test** the moment `security.py` + `retrieve.py` exist — a green suite without it is false safety.
- **Trim Gutenberg boilerplate** (`*** START/END OF THE PROJECT GUTENBERG EBOOK ***`) at ingest — markers are at line 27 / the END line in all 3 books.
- **`.env` never committed** (git-ignored; the `pre-tool-security` hook blocks secret-file edits). `.env.example` is the template.
- **Stable chunk ids** (`product_id:source:ordinal`) — the eval golden set depends on them surviving re-indexing.
- **Intel-Mac (x86_64) dep caps** (ADR-003) — **don't bump** `torch`/`numpy`/`transformers`/`onnxruntime` past the caps locally; they're the last x86_64-macOS wheels. `encode_query`/`encode_document` (ST 5.5.1) intact.

### Do NOT
- Skip the cross-tenant leak test.
- Accept a `product_id`/filter from the caller into the query without AND-ing it under the server-side entitlement filter.
- Post-filter for entitlements.
- Guess dependency versions — let `uv` resolve.
- Build Phase 2 (Azure) or a generation/LLM step yet — both are out of scope for Phase 1.
- Re-run env install / corpus download — step 1 is done.

---

## What Exists Today
- **Governance:** `CLAUDE.md` (master), `docs/PLANNING.md`, `docs/SECURITY.md`, `docs/spec-phase-1.md`, `docs/SESSION-GUIDE.md`.
- **Knowledge capture:** `docs/decisions/` (ADR system + ADR-001, ADR-002, **ADR-003**), `docs/history/` (retrospective log + template).
- **Claude Code:** `.claude/settings.json` (wires 3 hooks), `.claude/hooks/` (pre-tool-security, post-edit-format→ruff, post-response-notify→Stop, with ntfy mobile option), `.claude/rules/` (planning-doc-homes, access-control, rag-conventions), `.claude/agents/` (access-control-reviewer, rag-researcher), `.agents/skills/` (rag-eval-harness, chunking-lab, find-skills, roadmap-management), `.claude/templates/agent-TEMPLATE.md`.
- **Python:** `pyproject.toml` (uv, src layout, pinned deps, **`[tool.uv]` Intel-Mac caps**), `.python-version`, `.gitignore`, `.env.example`, `README.md`, `src/rag_exp/__init__.py`, `tests/__init__.py`. **`uv.lock` committed; `.venv` provisioned (Python 3.12.13).**
- **Corpus:** `products/{detective,shakespeare,science}/` — READMEs **+ validated Gutenberg `.txt`** (Adventures of Sherlock Holmes / Hamlet / On the Origin of Species), committed (public-domain, frozen for stable chunk ids).
- **Not yet built:** any `src/rag_exp/` pipeline modules (step 2+).

## Decisions Made
- ADR-001 — Phase-1 local stack. ADR-002 — pooled access-control model. **ADR-003 — Intel-Mac (x86_64) dependency compatibility caps.** (See `docs/decisions/`.)
- Split layout: subagents native in `.claude/agents/` (spawnable); skills in `.agents/skills/` for skills.sh compat (see Locked decisions #4).
- Lightweight local-first review over GitHub Actions tiers (see Locked decisions #3).

## Deferred Items
- Phase 2 (Azure AI Search + Azure OpenAI), hybrid search, reranking, LLM synthesis, the transcript "video" product — all post-Phase-1.
- **Marker-scope the Intel-Mac caps** (ADR-003) to `x86_64-darwin` only, so a future Linux/CI/arm env resolves to a modern stack — adopt when a real Linux target exists (Phase 2 devcontainer / CI).
- Housekeeping: temp dirs `/tmp/rag-research/` + `/tmp/uv-probe/` can be deleted (the `pre-tool-security` hook blocks `rm -rf`, so remove them manually).

---

### Session log
- **2026-06-06 — Session 1 (Phase 0):** Mined `seantokuzo-mcp` + `get-sean-done`; researched 2026 RAG best practices; scaffolded the full RAG/Python workspace + planning/spec docs. Decisions: ADR-001, ADR-002, local-first review, split `.claude/` + `.agents/skills/` layout. Skills moved to `.agents/skills/` for skills.sh compat; `git init` + pushed to github.com/seantokuzo/rag-pipeline (`main`).
- **2026-06-06 — Session 2 (Phase 1, step 1 — env + corpus):** `uv sync` hit an Intel-Mac (x86_64) wheel wall — onnxruntime (via chromadb) + torch (via sentence-transformers) dropped x86_64-macOS wheels, plus numpy-2 / transformers-5 runtime traps. A probe subagent verified the fix end-to-end → **ADR-003** `[tool.uv]` caps (torch 2.2.2 / numpy 1.26.4 / transformers 4.57.6 / onnxruntime 1.23.2; ST held 5.5.1). Downloaded + validated the 3-product Gutenberg corpus (boilerplate at line 27). Env smoke-tested (`uv pip check` clean, numpy→torch bridge OK). Branch `phase-1/env-and-corpus`.
