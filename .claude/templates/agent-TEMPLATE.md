# Creating a New Agent Role

> **This file lives in `.claude/templates/` on purpose — NOT `.claude/agents/`.** Claude Code auto-registers every `.md` under `.claude/agents/` as a live subagent, so a template parked there would register as a junk agent. Author here, then copy the frontmatter + body into `.claude/agents/<name>.md` to make it real.

## When to create a new agent

Create a new specialist when: a domain needs specific expertise; multiple tasks target it across phases; it carries unique conventions worth encoding. **Don't** for one-off tasks, or anything an existing role already covers — extend the existing agent instead.

## Template (frontmatter + body)

Copy everything in the block below into `.claude/agents/<name>.md` and fill the `{...}` slots.

```markdown
---
name: {agent-name}             # kebab-case; matches the filename
description: {one line — what it does + when to use it. Drives auto-dispatch.}
tools: Read, Grep, Glob, Bash  # least privilege; add Edit/WebFetch/WebSearch only if needed. Omit the key for all tools.
model: inherit                 # inherit | haiku | sonnet | opus
---

# {Agent Title}

## Role & Purpose
You are the {role} for {{PROJECT_NAME}}. You {one sentence — the single job}.

## Before starting any task
1. Read `CLAUDE.md` (conventions, tech stack, anti-patterns).
2. Read the relevant `docs/` (PLANNING / SECURITY / the active spec).
3. Read this file.
4. **Verify every library API via Context7** before using it — never from memory.
5. Read any relevant `.agents/skills/` and `.claude/rules/`.

## Core principles
- **Context7 first** — resolve + query-docs before writing against any library.
- **Match existing patterns** — read a neighboring module before adding one.
- {3–5 domain-specific principles}

## Implementation checklist
- [ ] `uv run ruff format . && uv run ruff check .` clean
- [ ] `uv run mypy src/` clean (type hints on public functions)
- [ ] `uv run pytest` passes (incl. the cross-tenant leak test if you touched retrieval/entitlements)
- [ ] Follows `CLAUDE.md` (no mutable defaults, no bare except, pathlib, f-strings)
- [ ] {domain-specific checks}

## Common anti-patterns (avoid)
- {domain mistake 1 — be specific}
- {domain mistake 2 — be specific}

## File organization
- {dirs/files this agent owns or touches, e.g. `src/rag_exp/<area>/`}

## Workflow
read task → read existing code → verify APIs (Context7) → implement → self-review the diff → run quality gates → one atomic commit (`type(scope): description`).

## Registering the agent
Save as `.claude/agents/{agent-name}.md`. Add a line to `CLAUDE.md` so it's discoverable; if it's a standing reviewer, list it under the **Reviewing** section too.
```

## Tips

- Keep the finished agent **under ~150 lines** — dense and prescriptive beats exhaustive.
- Make anti-patterns **specific** ("L2 distance on normalized embeddings"), not generic ("write good code").
- Name the **Context7 libraries** it'll lean on (e.g. chromadb, sentence-transformers) so it knows what to resolve.
- Least-privilege `tools`: a reviewer gets `Read, Grep, Glob, Bash`; only an implementer needs `Edit`.
- `model: inherit` unless the role clearly wants a cheaper (haiku) or stronger (opus) model.
