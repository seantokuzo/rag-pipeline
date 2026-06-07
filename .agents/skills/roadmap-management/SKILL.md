---
name: roadmap-management
description: Plan and manage phase-based roadmaps. Use when planning a new phase, reprioritizing work, or deciding what to build next.
---

# Roadmap Management

How we plan work in phases. The process is language-agnostic; the homes are this repo's docs.

## A phase = an observable capability

Frame every phase by one question: **"what can the user do after this phase that they couldn't before?"** If you can't answer it in a sentence, it's not a phase — it's a pile of tasks. (Phase 1's answer: *run an end-to-end RAG query behind a server-side entitlement filter, and watch the leak demo prove the boundary.*)

## The flow

1. **Decompose** the capability into **atomic tasks** — each one ≈ a single commit, independently reviewable. ("recursive splitter @ 512 tokens" is atomic; "do chunking" is not.)
2. **Map dependencies** — what must exist before each task can start (embed needs chunk; retrieve needs store + security).
3. **Group into waves** — a *wave* is a set of tasks with no unmet dependencies that could run in parallel. **Waves are a runtime parallelization concept — how you dispatch work in a session — NOT a label you store in the plan docs.** Don't write "Wave 2" into `PLANNING.md`; derive waves fresh from the dependency graph when you sit down to build.
4. **Estimate complexity, not time** — tag each task **S / M / L / XL** (effort + uncertainty combined). Time estimates lie; relative complexity is honest and surfaces the XLs that should be split before they're started.

## Prioritize: Now / Next / Later

- **Now** — in the active phase, dependencies met, building this session.
- **Next** — the following phase or on-deck tasks; queued, not started.
- **Later** — real but deferred (see *Open Questions* in `PLANNING.md`); revisit when evidence justifies it.

## Where it lives

- **`docs/PLANNING.md`** — the roadmap: phases, scope, build order, per-phase `status`.
- **`docs/STATE.md`** — live session context + the fresh-session handoff (what's actually in-progress right now).
- **Status enum** (use these exact words): `queued` · `in-progress` · `blocked` · `done` · `deferred` · `cancelled`.

Keep planning content to these homes — no `TODO.md` / `IDEAS.md` (see `.claude/rules/planning-doc-homes.md`).

## Phase-completion checklist

- [ ] The capability sentence is actually true — you can demo it.
- [ ] Acceptance criteria in `PLANNING.md` met.
- [ ] Quality gates green: `uv run ruff format . && uv run ruff check . && uv run pytest`.
- [ ] Learnings/surprises written to `docs/history/`; any locked trade-offs to `docs/decisions/`.
- [ ] `PLANNING.md`: phase `status: done`; the next phase flipped to `in-progress`.
- [ ] `docs/STATE.md` handoff updated so the next session resumes cold.
