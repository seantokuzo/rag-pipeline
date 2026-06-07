# Session State

> Current state of the project. Updated every session. **Read this first when resuming.**

**Last Updated:** 2026-06-07 — **Phase 1 (Session 2) — steps 1–2 DONE** (environment + corpus; `config` + `ingest`). Env provisioned (CPython 3.12.13, Intel-Mac caps per ADR-003, sentence-transformers 5.5.1). 3-product Gutenberg corpus downloaded + validated. `src/rag_exp/config.py` + `ingest.py` written, ruff-clean, smoke-tested (3 `SourceDoc`s, boilerplate trimmed). **Step 3 (chunk) is next.** _Prior:_ Phase 0 scaffolding complete (Session 1).

**Repo:** https://github.com/seantokuzo/rag-pipeline — work on branch `phase-1/env-and-corpus` (Session 2, pushed); `main` has Phase 0 scaffolding.

---

## Current Phase

**Phase 0 — Scaffolding: done.** **Phase 1 — Local pipeline: in-progress** — steps 1–2 of 11 done (env + corpus; config + ingest); **step 3 (chunk) next.**

### ⏭️ Fresh-session handoff — resume here

**What's done:** Phase 0 scaffolding (Session 1) + Phase 1 steps 1–2 (Session 2 — env + Intel-Mac caps per ADR-003; corpus downloaded/validated; `config.py` + `ingest.py` written, ruff-clean, smoke-tested). All committed + pushed to `phase-1/env-and-corpus`. Nothing to finish in steps 1–2.

**▶ ACTIVE — Phase 1, the local pipeline. The spec is `docs/spec-phase-1.md` — read it; it's the binding build order.** Build order (each ≈ one commit): ~~1) corpus prep~~ ✅ · ~~2) config+ingest~~ ✅ · **3) chunk ◀ next** · 4) embed · 5) store/chroma · 6) index · 7) security · 8) retrieve · 9) **leak demo** · 10) eval + cross-tenant test · 11) poke experiments.

**▷ NEXT STEP — chunk (Phase 1, step 3). Read `docs/spec-phase-1.md` Part B + the `chunking-lab` skill (`.agents/skills/chunking-lab/`) FIRST (skill protocol).**
1. **`chunk` module** — split each `SourceDoc` into `Chunk` records via `RecursiveCharacterTextSplitter.from_tiktoken_encoder(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)` (langchain-text-splitters + tiktoken; token-accurate, so 512 = tokens not chars).
2. **`Chunk` dataclass** = `{id, text, product_id, source}`; **stable id** = `f"{product_id}:{source}:{ordinal}"` (the eval golden set depends on these surviving re-indexing).
3. Inherit `product_id`/`source` from the parent `SourceDoc` onto every chunk. Then step 4 (embed).

**Inputs ready:** `from rag_exp.ingest import load_products` → 3 `SourceDoc`s (detective / science / shakespeare); `from rag_exp.config import CHUNK_SIZE, CHUNK_OVERLAP`.

**Env is READY** — `uv run …` works; do NOT re-run install or corpus download. ⚠️ The first embed run (step 4) downloads the `bge-small` model (~130 MB).

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
- **Embedding parity** — same model/normalization/prompt both sides; `encode_document()` for chunks, `encode_query()` for queries (bge-small has an asymmetric query prefix).
- **Metadata on every chunk** — stamp `{product_id, source}` at ingestion; an unlabeled chunk is un-securable (hard error).
- **Chunk size ≤ 512 tokens** (bge-small max sequence) or text is silently truncated at embed time.
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
- **Python:** `pyproject.toml` (uv, src layout, pinned deps, `[tool.uv]` Intel-Mac caps), `.python-version`, `.gitignore`, `.env.example`, `README.md`, `src/rag_exp/{__init__,config,ingest}.py`, `tests/__init__.py`. `uv.lock` committed; `.venv` provisioned (Python 3.12.13).
- **Corpus:** `products/{detective,shakespeare,science}/` — READMEs + validated Gutenberg `.txt` (Adventures of Sherlock Holmes / Hamlet / On the Origin of Species), committed (public-domain, frozen for stable chunk ids).
- **Pipeline so far:** `config.py` (spec Appendix defaults, project-root paths) + `ingest.py` (`load_products` → frozen `SourceDoc{text,product_id,source}`, Gutenberg trim, product_id hard-error). Smoke-tested: 3 docs.
- **Not yet built:** `src/rag_exp/` modules for chunk / embed / store / index / security / retrieve (step 3+); no tests yet (the cross-tenant leak test lands with security + retrieve).

## Decisions Made
- ADR-001 — Phase-1 local stack. ADR-002 — pooled access-control model. ADR-003 — Intel-Mac (x86_64) dependency compatibility caps. (See `docs/decisions/`.)
- Split layout: subagents native in `.claude/agents/` (spawnable); skills in `.agents/skills/` for skills.sh compat (see Locked decisions #4).
- Lightweight local-first review over GitHub Actions tiers (see Locked decisions #3).
- **Science corpus front-matter left as-is** (Session 2) — see Gotchas.

## Deferred Items
- Phase 2 (Azure AI Search + Azure OpenAI), hybrid search, reranking, LLM synthesis, the transcript "video" product — all post-Phase-1.
- **Marker-scope the Intel-Mac caps** (ADR-003) to `x86_64-darwin` only, so a future Linux/CI/arm env resolves to a modern stack — adopt when a real Linux target exists (Phase 2 devcontainer / CI).
- Housekeeping: temp dirs `/tmp/rag-research/` + `/tmp/uv-probe/` can be deleted (the `pre-tool-security` hook blocks `rm -rf`, so remove them manually).

---

### Session log
- **2026-06-06 — Session 1 (Phase 0):** Mined `seantokuzo-mcp` + `get-sean-done`; researched 2026 RAG best practices; scaffolded the full RAG/Python workspace + planning/spec docs. Decisions: ADR-001, ADR-002, local-first review, split `.claude/` + `.agents/skills/` layout. Skills moved to `.agents/skills/` for skills.sh compat; `git init` + pushed to github.com/seantokuzo/rag-pipeline (`main`).
- **2026-06-06/07 — Session 2 (Phase 1, steps 1–2):** Step 1 — `uv sync` hit an Intel-Mac (x86_64) wheel wall (onnxruntime via chromadb + torch via sentence-transformers dropped x86_64-macOS wheels; numpy-2 / transformers-5 runtime traps); a probe subagent verified the fix end-to-end → **ADR-003** `[tool.uv]` caps (torch 2.2.2 / numpy 1.26.4 / transformers 4.57.6 / onnxruntime 1.23.2; ST held 5.5.1). Downloaded + validated the 3-product Gutenberg corpus (boilerplate at line 27). Step 2 — wrote `config.py` (spec Appendix defaults, project-root paths) + `ingest.py` (`load_products` → frozen `SourceDoc`, Gutenberg trim, product_id hard-error); ruff-clean, smoke-tested (3 docs). Decided to **leave** the 9-line Gutenberg "several editions" note in the science corpus (benign). Committed + pushed to `phase-1/env-and-corpus`. Handoff → step 3 (chunk).
