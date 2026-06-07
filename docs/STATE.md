# Session State

> Current state of the project. Updated every session. **Read this first when resuming.**

**Last Updated:** 2026-06-06 — **Phase 0 (Session 1) — scaffolding COMPLETE.** The full Claude Code workspace + planning/spec docs are in place (CLAUDE.md, docs/, `.claude/` agents+skills+hooks+rules, Python skeleton, corpus folders). No pipeline code yet by design. Next session starts Phase 1 (the local pipeline). _Prior:_ — (project start).

**Repo:** https://github.com/seantokuzo/rag-pipeline — `main` (scaffolding pushed 2026-06-06).

---

## Current Phase

**Phase 0 — Scaffolding: done.** **Phase 1 — Local pipeline: queued, ready to start.**

### ⏭️ Fresh-session handoff — when the user says "next"

**What's done (Phase 0):** Workflow scaffolding adapted from the proven `seantokuzo-mcp` setup, re-pointed to Python/RAG. All Session-1 deliverables exist and cross-link. Nothing to finish here.

**▶ ACTIVE NEXT — Phase 1, the local pipeline. The spec is `docs/spec-phase-1.md` — read it; it's the binding build order.** Build order (each ≈ one commit): 1) corpus prep · 2) config+ingest · 3) chunk · 4) embed · 5) store/chroma · 6) index · 7) security · 8) retrieve · 9) **leak demo** · 10) eval + cross-tenant test · 11) poke experiments.

**▷ FIRST STEP — environment + corpus (Phase 1, step 1):**
1. **Install tooling** (this box currently has system Python 3.10 and **no `uv`**): install `uv` (e.g. `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`), then `uv sync` — it provisions Python 3.12 (per `.python-version`) and the deps. ⚠️ First sync pulls `torch` (large) and the first embed run downloads the `bge-small` model.
2. **Corpus prep:** download the three products' public-domain Project Gutenberg `.txt` into `products/detective/`, `products/shakespeare/`, `products/science/` (see each folder's README for which books). This is a *data* step, not pipeline code.
3. Then proceed to step 2 (config + ingest) per the spec, teaching as we go.

**Remember the working style:** this is a learning collaboration — explain Python/RAG choices, move one step at a time, present options at decision points, don't autonomously build the whole phase.

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

### Gotchas carried forward
- **Cosine, not L2** — set `metadata={"hnsw:space":"cosine"}` on the Chroma collection (L2 is the default).
- **Embedding parity** — same model/normalization/prompt both sides; `encode_document()` for chunks, `encode_query()` for queries (bge-small has an asymmetric query prefix).
- **Metadata on every chunk** — stamp `{product_id, source}` at ingestion; an unlabeled chunk is un-securable (hard error).
- **Chunk size ≤ 512 tokens** (bge-small max sequence) or text is silently truncated at embed time.
- **Mandatory cross-tenant leak test** the moment `security.py` + `retrieve.py` exist — a green suite without it is false safety.
- **Trim Gutenberg boilerplate** (`*** START/END OF THE PROJECT GUTENBERG EBOOK ***`) at ingest.
- **`.env` never committed** (git-ignored; the `pre-tool-security` hook blocks secret-file edits). `.env.example` is the template.
- **Stable chunk ids** (`product_id:source:ordinal`) — the eval golden set depends on them surviving re-indexing.

### Do NOT
- Skip the cross-tenant leak test.
- Accept a `product_id`/filter from the caller into the query without AND-ing it under the server-side entitlement filter.
- Post-filter for entitlements.
- Guess dependency versions — let `uv` resolve.
- Build Phase 2 (Azure) or a generation/LLM step yet — both are out of scope for Phase 1.

---

## What Exists Today
- **Governance:** `CLAUDE.md` (master), `docs/PLANNING.md`, `docs/SECURITY.md`, `docs/spec-phase-1.md`, `docs/SESSION-GUIDE.md`.
- **Knowledge capture:** `docs/decisions/` (ADR system + ADR-001, ADR-002), `docs/history/` (retrospective log + template).
- **Claude Code:** `.claude/settings.json` (wires 3 hooks), `.claude/hooks/` (pre-tool-security, post-edit-format→ruff, post-response-notify→Stop, with ntfy mobile option), `.claude/rules/` (planning-doc-homes, access-control, rag-conventions), `.claude/agents/` (access-control-reviewer, rag-researcher), `.agents/skills/` (rag-eval-harness, chunking-lab, find-skills, roadmap-management), `.claude/templates/agent-TEMPLATE.md`.
- **Python:** `pyproject.toml` (uv, src layout, pinned deps), `.python-version`, `.gitignore`, `.env.example`, `README.md`, `src/rag_exp/__init__.py`, `tests/__init__.py`.
- **Corpus:** `products/{detective,shakespeare,science}/` with READMEs (no `.txt` yet — Phase 1 step 1).
- **Not yet built:** any `src/rag_exp/` pipeline modules, the corpus `.txt`, the venv (`uv sync` not run).

## Decisions Made
- ADR-001 — Phase-1 local stack. ADR-002 — pooled access-control model. (See `docs/decisions/`.)
- Split layout: subagents native in `.claude/agents/` (spawnable); skills in `.agents/skills/` for skills.sh compat (see Locked decisions #4).
- Lightweight local-first review over GitHub Actions tiers (see Locked decisions #3).

## Deferred Items
- Phase 2 (Azure AI Search + Azure OpenAI), hybrid search, reranking, LLM synthesis, the transcript "video" product — all post-Phase-1.
- _(resolved 2026-06-06: skills → `.agents/skills/` for skills.sh; subagents stay native in `.claude/agents/`)_
- Housekeeping: temp research clones at `/tmp/rag-research/` can be deleted.

---

### Session log
- **2026-06-06 — Session 1 (Phase 0):** Mined `seantokuzo-mcp` + `get-sean-done`; researched 2026 RAG best practices; scaffolded the full RAG/Python workspace + planning/spec docs. Decisions: ADR-001, ADR-002, local-first review, split `.claude/` + `.agents/skills/` layout. Skills moved to `.agents/skills/` for skills.sh compat; `git init` + pushed to github.com/seantokuzo/rag-pipeline (`main`).
