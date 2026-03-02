from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class LLMResponse:
    content: str
    model: str
    provider: str
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class SkillSpec:
    name: str
    version: str
    description: str
    inputs: list[str]
    outputs: list[str]
    constraints: list[str]
    body_md_path: Path
    assets_paths: list[Path] = field(default_factory=list)
    scripts_paths: list[Path] = field(default_factory=list)


@dataclass(slots=True)
class SkillRunResult:
    skill_name: str
    output: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RetrievedContext:
    segments: list[str]
    total_tokens: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EvalReport:
    avg_score: float
    per_case_scores: dict[str, float]
    regressions: dict[str, float]
    safety_checks: dict[str, bool]
    accepted: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SkillPatch:
    skill_name: str
    source_path: Path
    candidate_path: Path
    hypothesis: str
    diff_path: Path
    snapshot_id: str


@dataclass(slots=True)
class EvolutionDecision:
    should_evolve: bool
    target_skill: str
    hypothesis: str


@dataclass(slots=True)
class TaskRun:
    task_run_id: str
    session_id: str
    task_input: str
    response: str
    used_skill: str
    quality_score: float
