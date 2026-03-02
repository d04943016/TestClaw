from __future__ import annotations

from pathlib import Path

from myopenclaw.config import Settings
from myopenclaw.core.types import EvalReport
from myopenclaw.evals.harness import EvalHarness
from myopenclaw.memory.store import MemoryStore
from myopenclaw.skills.evolver import SkillEvolver
from myopenclaw.skills.registry import SkillRegistry


def _write_skill(skill_root: Path, name: str, body: str) -> None:
    folder = skill_root / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(body, encoding="utf-8")


def test_evolver_apply_candidate_on_pass(tmp_path):
    settings = Settings(project_root=tmp_path)

    _write_skill(
        settings.skills_dir,
        "plan",
        """---
name: plan
version: 0.1.0
description: planning skill
inputs: [objective]
outputs: [plan]
constraints: [scope]
---
# Plan\nBasic planning guidance.
""",
    )

    cases_path = tmp_path / "cases.yaml"
    cases_path.write_text(
        """cases:
  - id: plan-improve
    skill: plan
    task: create plan
    expected_keywords: [goal, constraints, steps, output, risks]
""",
        encoding="utf-8",
    )

    store = MemoryStore(settings.db_path)
    registry = SkillRegistry(settings.skills_dir)
    registry.load_skills()
    harness = EvalHarness(registry=registry, store=store, cases_path=cases_path)
    evolver = SkillEvolver(
        settings=settings,
        registry=registry,
        harness=harness,
        store=store,
        router=None,
    )

    patch = evolver.propose_mutation("plan", hypothesis="add structure")
    report = evolver.evaluate_candidate(patch)
    outcome = evolver.apply_or_rollback(patch, report)

    assert report.accepted is True
    assert outcome["applied"] is True

    updated_text = (settings.skills_dir / "plan" / "SKILL.md").read_text(encoding="utf-8")
    assert "version: 0.1.1" in updated_text

    store.close()


def test_evolver_reject_keeps_original(tmp_path):
    settings = Settings(project_root=tmp_path)

    _write_skill(
        settings.skills_dir,
        "plan",
        """---
name: plan
version: 0.1.0
description: planning skill
inputs: [objective]
outputs: [plan]
constraints: [scope]
---
# Plan\nBasic planning guidance.
""",
    )

    store = MemoryStore(settings.db_path)
    registry = SkillRegistry(settings.skills_dir)
    registry.load_skills()
    harness = EvalHarness(registry=registry, store=store)
    evolver = SkillEvolver(
        settings=settings,
        registry=registry,
        harness=harness,
        store=store,
        router=None,
    )

    patch = evolver.propose_mutation("plan", hypothesis="force reject")
    reject_report = EvalReport(
        avg_score=0.2,
        per_case_scores={"x": 0.2},
        regressions={"x": -0.3},
        safety_checks={"inside_skills_scope": True, "no_dangerous_commands": True},
        accepted=False,
        details={},
    )
    outcome = evolver.apply_or_rollback(patch, reject_report)

    assert outcome["applied"] is False
    current = (settings.skills_dir / "plan" / "SKILL.md").read_text(encoding="utf-8")
    assert "version: 0.1.0" in current

    store.close()
