# MyOpenClaw (Python MVP)

A simple OpenClaw-style local agent with:
- Claude-style `skills/<name>/SKILL.md`
- Hierarchical compressed memory (`L1/L2/L3`) + FAISS retrieval
- Autonomous skill evolution with evaluation gate + auto rollback
- Multi-provider LLM routing (OpenAI / Anthropic / Gemini via LiteLLM)

## Manual

- Detailed handbook (Traditional Chinese): `docs/USER_MANUAL_zh-TW.md`
- Agentic design guide + 5 scenarios: `docs/AGENTIC_SYSTEM_DESIGN_GUIDE_zh-TW.md`
- Copy-ready case templates (5 scenarios): `docs/CASE_TEMPLATES_zh-TW.md`
- Academic deep-research skillpack guide: `docs/ACADEMIC_DEEP_RESEARCH_SKILLPACK_zh-TW.md`
- Technical roadmap (evolution + memory): `docs/TECHNICAL_ROADMAP_zh-TW.md`
- Survey-agent playbook: `skills/research_pack/README_SURVEY_AGENT_zh-TW.md`

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env
```

Fill provider API keys in `.env`.

For hybrid semantic+keyword retrieval:
- Agent memory uses `AGENT_EMBEDDING_*`
- Research skillpack uses `SKILL_EMBEDDING_*`

Optional research preset for `/Users/weikai/Library/CloudStorage/Dropbox/paper`:
- Set `MYOPENCLAW_PROFILE=profiles/paper_deep_research.env` in `.env`
- Keep API keys in `.env` (profile file does not contain secrets)

## CLI

```bash
python -m myopenclaw providers list
python -m myopenclaw skills list
python -m myopenclaw skills show summarize
python -m myopenclaw chat --session demo
python -m myopenclaw memory compress --session demo
python -m myopenclaw trace tail --session demo --limit 5
python -m myopenclaw eval run
python -m myopenclaw evolve run --skill summarize
```

## Design Notes

### Skills
- Format: `skills/<name>/SKILL.md` with YAML frontmatter + markdown body.
- Optional dirs: `scripts/`, `references/`, `assets/`.
- Evolver is restricted to mutate only `skills/` content.

### Memory
- Short-term window keeps latest 30 messages.
- Older messages are compressed into `L1` summaries.
- Every 10 `L1` -> one `L2`; every 10 `L2` -> one `L3`.
- Retrieval order: recent raw context first, then vector-retrieved chunks, then high-level summaries.

### Evolution Gate
- Runs after each task.
- Candidate skill is generated in `.agent_state/skill_versions/...`.
- Regression rules:
  - average score improvement must be >= `+0.15`
  - no case delta may be below `-0.20`
  - safety checks must pass
- Accepted candidate is applied; otherwise rollback is automatic (no change to live skill).

## Tests

```bash
pytest -q
```

Example compatibility check (documented research scenarios):

```bash
PYTHONPATH=src python -m unittest tests.test_examples_compatibility -v
```
