# Academic Deep Research Skill Pack

This pack provides a research-focused capability layer for MyOpenClaw without changing `src/`.

Survey-oriented usage handbook:
- `skills/research_pack/README_SURVEY_AGENT_zh-TW.md`

## Dedicated Path

- Pack source: `skills/research_pack/`
- Runtime-facing skill entries: top-level symlinks under `skills/`

## Skills Included

1. `research_deep_research_orchestrator`
2. `research_rag`
3. `research_graphrag`
4. `research_progressive_reader`
5. `research_evidence_structurer`
6. `research_hypothesis_generator`
7. `research_gap_finder`
8. `research_study_designer`

## Paper Root

By default scripts read from:

`/Users/weikai/Library/CloudStorage/Dropbox/paper`

You can override with:

```bash
export PAPER_ROOT=/your/other/paper/root
```

For the built-in paper preset, set in `.env`:

```dotenv
MYOPENCLAW_PROFILE=profiles/paper_deep_research.env
```

## Embedding Key Separation

Research skill retrieval uses a dedicated embedding key:

- `SKILL_EMBEDDING_API_KEY`
- `SKILL_EMBEDDING_MODEL`
- `SKILL_EMBEDDING_BASE_URL`
- `SKILL_MEMORY_SEMANTIC_WEIGHT`

Agent memory retrieval uses a separate key path:

- `AGENT_EMBEDDING_API_KEY`
- `AGENT_EMBEDDING_MODEL`
- `AGENT_EMBEDDING_BASE_URL`
- `AGENT_MEMORY_SEMANTIC_WEIGHT`

## Retrieval Tuning Knobs

Skill-side hybrid retrieval:

- `SKILL_FILE_SCAN_LIMIT`
- `SKILL_RETRIEVAL_TOP_K`
- `SKILL_PRESELECT_MULTIPLIER`
- `SKILL_PRESELECT_MIN`
- `SKILL_PRESELECT_MAX`
- `SKILL_SEMANTIC_PREVIEW_COUNT`

Agent memory-side hybrid retrieval:

- `AGENT_MEMORY_TOP_K`
- `MEMORY_SHORT_TERM_WINDOW`
- `MEMORY_CHUNK_TARGET_TOKENS`
- `MEMORY_ROLLUP_BATCH_SIZE`

## Artifacts

All scripts write auditable outputs to:

`.agent_state/research_outputs/<skill>/<timestamp_slug>/`

Each run generates both JSON (machine-readable) and Markdown (human-auditable) outputs.
