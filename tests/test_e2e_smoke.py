from __future__ import annotations

from myopenclaw.config import Settings
from myopenclaw.core.agent import OpenClawAgent


def _write_skill(path, name, body):
    target = path / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "SKILL.md").write_text(body, encoding="utf-8")


def test_chat_flow_triggers_memory_and_evolution_hook(tmp_path):
    settings = Settings(project_root=tmp_path)
    settings.short_term_window = 6
    settings.chunk_target_tokens = 40

    _write_skill(
        settings.skills_dir,
        "summarize",
        """---
name: summarize
version: 0.1.0
description: summarize things
inputs: [text]
outputs: [summary]
constraints: [factual]
---
# Summarize\nProvide summary with constraints and risks.
""",
    )
    _write_skill(
        settings.skills_dir,
        "plan",
        """---
name: plan
version: 0.1.0
description: create plans
inputs: [goal]
outputs: [steps]
constraints: [scope]
---
# Plan\nProvide steps, scope, and output.
""",
    )

    agent = OpenClawAgent(settings=settings)

    calls = {"count": 0}

    def fake_post_task_evolve(task_run_id: str):
        calls["count"] += 1
        return None

    agent.evolver.post_task_evolve = fake_post_task_evolve  # type: ignore[method-assign]

    response = ""
    for i in range(10):
        turn = agent.run_turn(
            session_id="smoke",
            user_input=f"Please plan step {i} with constraints and timeline.",
            token_budget=600,
        )
        response = turn.response

    assert response
    assert calls["count"] == 10

    compressed = agent.store.get_compressed_chunks(session_id="smoke", level=1)
    assert compressed

    agent.close()
