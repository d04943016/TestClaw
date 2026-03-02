from __future__ import annotations

import pytest

from myopenclaw.config import Settings
from myopenclaw.skills.executor import SkillExecutor
from myopenclaw.skills.registry import SkillRegistry
from myopenclaw.skills.sandbox import SandboxViolationError, SkillSandbox


SKILL_TEXT = """---
name: summarize
version: 0.1.0
description: test summarize
inputs: [raw]
outputs: [summary]
constraints: [factual]
---
# Summarize

Make a concise summary.
"""


def test_registry_parses_claude_style_skill(tmp_path):
    skill_dir = tmp_path / "skills" / "summarize"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(SKILL_TEXT, encoding="utf-8")

    settings = Settings(project_root=tmp_path)
    registry = SkillRegistry(settings.skills_dir)
    skills = registry.load_skills()

    assert len(skills) == 1
    skill = registry.get_skill("summarize")
    assert skill is not None
    assert skill.version == "0.1.0"
    assert skill.description == "test summarize"


def test_sandbox_blocks_path_escape(tmp_path):
    skill_dir = tmp_path / "skills" / "summarize"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(SKILL_TEXT, encoding="utf-8")

    sandbox = SkillSandbox(tmp_path / "skills")

    with pytest.raises(SandboxViolationError):
        sandbox.safe_write_file("summarize", "../escape.txt", "bad")


def test_executor_runs_without_provider(tmp_path):
    skill_dir = tmp_path / "skills" / "summarize"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(SKILL_TEXT, encoding="utf-8")

    settings = Settings(project_root=tmp_path)
    registry = SkillRegistry(settings.skills_dir)
    registry.load_skills()

    executor = SkillExecutor(
        registry=registry,
        sandbox=SkillSandbox(settings.skills_dir),
        router=None,
    )

    result = executor.execute(
        skill_name="summarize",
        task_context="Summarize this design.",
        memory_context=["[recent:user] hello"],
    )
    assert "Summarize this design" in result.output
