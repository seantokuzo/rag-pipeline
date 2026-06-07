---
name: find-skills
description: Discover and install agent skills from the community ecosystem (npx skills / skills.sh). Use when looking for a specialized capability or asking "how do I do X".
---

# Find Skills

Reach for a community-built skill before hand-rolling a capability. The ecosystem is browsable at **https://skills.sh** and installable through the `npx skills` CLI.

## The `npx skills` flow

```bash
npx skills find <query>            # search the registry
npx skills add <owner/repo@skill>  # install a skill into this project
npx skills check                   # list installed skills + flag available updates
npx skills update                  # pull latest versions
```

## RAG-flavored searches

```bash
npx skills find rag
npx skills find embeddings
npx skills find reranking
npx skills find eval
npx skills find "vector db"
```

Skim the results, **read the skill's source before adding it** (it runs in your repo), then `add owner/repo@skill`.

## This repo

Project-specific skills live under (skills.sh layout) `.agents/skills/<name>/SKILL.md` (see `chunking-lab`, `rag-eval-harness`) — that's where ours go. Use `npx skills` to *pull in* community capabilities; author repo-specific ones natively.
