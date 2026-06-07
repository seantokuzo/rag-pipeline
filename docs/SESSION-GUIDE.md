# Session Guide — How to Drive These Sessions

> The human-operator playbook. You are the pilot; Claude is the engine. This doc is how you fly it. Pairs with `docs/STATE.md` (where any session resumes) and `CLAUDE.md` (the rules Claude follows).

---

## Your Role

You are the **planner, spec-maker, and QA** — not the typist.

- **You do NOT write code.** Claude does. Your job is direction, decisions, and judging the result.
- **You do NOT need to remember everything between sessions.** The docs do that. `docs/STATE.md` holds live context + the Fresh-session handoff; `PLANNING.md` holds the roadmap; ADRs hold the locked decisions; `docs/history/` holds the learnings. If it matters, it's written down — and if it isn't, *that's* the bug to fix.
- **What only you can do:** set direction, choose between the options Claude presents, and QA the output (does the leak demo actually leak? is the cross-tenant test real, or green-but-empty?).

The whole system is built so a fresh session with zero memory resumes cleanly from the docs alone. Trust that — don't hoard context in your head.

---

## Session Lifecycle

### Starting a session
1. Open with the fresh-session kickoff prompt (below). Claude reads `CLAUDE.md` + `docs/STATE.md` and reports where things stand.
2. Skim its summary of the handoff. Correct it if it misread state.
3. Point it at the next build step (usually the next item in `spec-phase-1.md` → Build order).

### During a session
- **One step ≈ one commit.** Keep work atomic — easier to review, cheaper to revert.
- **Make decisions when asked.** Claude surfaces options at forks; pick one (or ask for its recommendation).
- **QA as you go.** When a stage lands, ask "show me it working" before moving on.

### When to start a fresh session
Context rot degrades quality. Start fresh when you see **context-exhaustion signals**:
- Claude forgets a decision you made earlier in the session.
- It repeats searches it already ran, or re-reads files it just read.
- Answers get vaguer, hedge more, or drift from the spec.

When you see these: have Claude **update `docs/STATE.md` and commit**, then open a new session with the kickoff prompt. A clean context beats a clever-but-confused one every time.

---

## The Planning-Partner Workflow

**Phase planning.** Phases live in `PLANNING.md`. Before a phase starts, its spec (`spec-phase-*.md`) is the contract — binding unless a line is marked `[uncertain]`. If a phase has no spec yet, write one *with* Claude before building.

**Mid-phase decisions = options, not edicts.** When a real fork appears (chunk size? add overlap? rerank now or later?), Claude presents **2–4 options with trade-offs and a recommendation**. You pick. If the choice is architectural and hard to reverse, it graduates to an **ADR** (see `docs/decisions/`).

**Scope management.** The spec's Non-goals are a fence, not a suggestion. When a shiny tangent shows up:
- In scope → do it now.
- Out of scope but worth doing → log it in `STATE.md` / `PLANNING.md` Open Questions, keep moving.
- Never silently expand the step you're on. Atomic beats sprawling.

---

## Review Flow (local-first)

No GitHub Actions, no review tiers — this project reviews **locally**, two ways:

1. **`/code-review`** — run on the working diff for general correctness + cleanup. Use after any non-trivial change.
2. **`@agent-access-control-reviewer`** — spawn it after **any** change to `security.py`, `retrieve.py`, ingestion metadata, or the vector-store query path. It's the security gate: verifies the entitlement invariant and that the cross-tenant test covers the change. (Defined in `.claude/agents/access-control-reviewer.md`.)

Rule of thumb: **touched the filter or the retrieval path → run the access-control reviewer, no exceptions.** Everything else → `/code-review`.

---

## Useful Prompts (copy-paste)

**Fresh session (always start here):**
```
Read CLAUDE.md and docs/STATE.md, then continue from the Fresh-session handoff.
```

**Continue mid-phase:**
```
We're mid Phase 1. Read docs/STATE.md for where we left off, then pick up the next build step. Show me the plan before you code.
```

**Execute a specific build step:**
```
Read docs/spec-phase-1.md. Implement build step <N> (<name>) — just that step, as one atomic commit. Follow the spec's contract and the access-control invariant in SECURITY.md.
```

**Force a decision before any code:**
```
Give me 2–4 options for <X> with trade-offs and your recommendation. Don't build yet.
```

(On mobile / Termius: these are plain text on purpose — paste and go, no interactive pickers to fight.)

---

## Troubleshooting

- **"Where were we?"** → `docs/STATE.md`, the Fresh-session handoff block. If it's stale, *that's* the real bug — fix the handoff, not your memory.
- **Claude wants to re-litigate a locked decision** → point it at the relevant ADR or `PLANNING.md`. Locked means locked unless there's new evidence.
- **Claude guesses a package version** → stop it; versions come from `uv add`, never memory (CLAUDE.md rule).
- **Quality degrading mid-session** → it's context rot. Update STATE.md, commit, fresh session.
- **A stage "works" but you're unsure** → demand the proof: the leak-demo output, the passing cross-tenant test, the eval numbers.

---

## Tips

- **End every session by updating `docs/STATE.md`.** Non-negotiable — it's how the next session starts clean.
- **Commit per step.** Small commits = cheap reverts + readable history.
- **Ask "why" freely.** This is a learning lab; "explain that Python idiom / RAG choice" is always a valid request.
- **Let the eval harness referee.** Don't add hybrid / rerank / fancier chunking on faith — make the numbers justify it (that's what `docs/history/` is for).
- **On mobile:** keep prompts short and explicit; ask for plain-text option lists, not menus.
