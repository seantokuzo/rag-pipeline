# ADR-003: Intel-Mac (x86_64-macOS) dependency compatibility caps

**Status:** Accepted
**Date:** 2026-06-06
**Supersedes:** none
**Superseded by:** none

## Context

The development box is an **Intel Mac** (`x86_64-macOS`, macOS 26, CPython 3.12.13 provisioned by uv 0.11.8). ADR-001 pinned the Phase-1 local stack (chromadb 1.5.9, sentence-transformers 5.5.1, etc.), but `uv sync` **failed to install**.

Root cause: `uv` builds a *universal lock* — it picks the latest version of every transitive dependency, then installs the current platform's wheel. The modern ML stack has **dropped x86_64-macOS wheels**, so two transitive deps had no installable artifact, and two more were latent runtime breakages that dependency resolution cannot see:

| Package | Pulled in by | Problem on Intel Mac | Last good version |
|---|---|---|---|
| **onnxruntime** | chromadb (hard dep, `>=1.14.1`) | no cp312 x86_64-macOS wheel after 1.23.2 | **1.23.2** |
| **torch** | sentence-transformers (`>=1.11.0`) | no cp312 x86_64-macOS wheel after 2.2.2 | **2.2.2** |
| **numpy** | torch | torch 2.2.2 is built against numpy 1.x; numpy 2.x → `import torch` raises "Numpy is not available" | **<2** (→ 1.26.4) |
| **transformers** | sentence-transformers | transformers 5.x hard-requires torch≥2.4 at runtime → ST import crash | **<5** (→ 4.57.6) |

A probe subagent reproduced the failure and verified the fix **end-to-end on a box identical to this one** (HIGH confidence): full `uv sync`, `uv pip check` clean, bge-small `encode_query`/`encode_document` (384-dim, normalized, asymmetric prefixes working), Chroma cosine + `$in` pre-filter returning only entitled products, pytest 9.0.3 + ruff 0.15.16.

We do **not** use chromadb's ONNX default embedder (we embed with sentence-transformers), so onnxruntime is never imported — its cap is pure install-time compatibility.

## Decision

We will add a `[tool.uv]` block to `pyproject.toml` with four **global** `constraint-dependencies`:

```toml
[tool.uv]
constraint-dependencies = [
    "onnxruntime<=1.23.2",
    "torch<=2.2.2",
    "numpy<2",
    "transformers<5",
]
```

These are **constraints, not overrides** (nothing in the graph demands versions above them, so it's a non-conflicting narrowing). **No `[project].dependencies` change** — the ADR-001 stack stands; sentence-transformers stays 5.5.1, preserving the `encode_query`/`encode_document` API. This ADR **extends ADR-001** for the Intel-Mac platform; it does not supersede it.

## Alternatives considered

- **Marker-scope the caps to Intel Mac only** (`"...; sys_platform=='darwin' and platform_machine=='x86_64'"`) so a future Linux/CI/Apple-Silicon env resolves to the unmodified modern stack. Deferred, not rejected: the probe could not verify the non-mac resolution branch on this box, and it's premature for an environment that doesn't exist yet (Phase 1 is local-only; review is local-first with no Linux CI per ADR-001/locked-decision-3). **This is the documented upgrade path** — adopt it the moment a real Linux target exists (Phase 2 devcontainer / CI), with that env available to verify.
- **Linux devcontainer now** (unmodified modern stack, matches Phase 2's Linux target). Rejected for now: a Docker detour from the learning goal, and unnecessary since the caps make Phase 1 work today. Remains the escalation path if we want a modern local stack before the pins drift further.
- **Downgrade chromadb / sentence-transformers to shed onnxruntime/torch.** Rejected: onnxruntime is a *hard* top-level dep of chromadb (not an extra, can't be dropped), and dropping ST below 5.0 loses `encode_query`/`encode_document` — the exact API the embedding-parity lesson relies on.

## Consequences

### Positive
- `uv sync` installs cleanly on the Intel Mac; **Phase 1 is unblocked**, proven end-to-end.
- The ADR-001 stack and the security/retrieval invariants are untouched — caps are transitive and install-time only.
- Resolved versions are the newest still-compatible: onnxruntime 1.23.2, torch 2.2.2, numpy 1.26.4, transformers 4.57.6, with ST held at 5.5.1.

### Negative
- Freezes the local ML substack to **2024-era versions** (torch 2.2.2 / numpy 1.x / transformers 4.x) — effectively EOL for new wheels. No functional impact on Phase 1 (CPU embeddings of a small public-domain corpus).
- Caps are **global**: a future Linux / Apple-Silicon / CI env would also be held back until they are marker-scoped (tracked as the alternative above).

### Neutral
- **Phase 2 targets Azure** (Linux runtime + Azure OpenAI `text-embedding-3-small`), which sidesteps local torch/onnxruntime entirely — so the relevance of these caps largely ends with Phase 1.
- A Linux devcontainer remains the clean escalation path for a modern local stack.

## Links
- ADR-001 — the Phase-1 local stack these caps extend.
- `pyproject.toml` — the `[tool.uv] constraint-dependencies` block (with inline rationale).
- `docs/spec-phase-1.md` — Phase 1 environment setup (build-order step 1).
