from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from myopenclaw.core.types import EvalReport
from myopenclaw.evals.scorer import ResponseScorer
from myopenclaw.memory.store import MemoryStore
from myopenclaw.skills.registry import SkillRegistry


def _parse_bracket_list(value: str) -> list[str]:
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return [value.strip().strip('"\'')]
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [item.strip().strip('"\'') for item in inner.split(",") if item.strip()]


def _parse_simple_cases_yaml(text: str) -> list[dict[str, Any]]:
    # Minimal parser for the local cases schema.
    cases: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    list_key: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "cases:":
            continue

        if stripped.startswith("- ") and line.startswith("  -"):
            if current:
                cases.append(current)
            current = {}
            list_key = None
            head = stripped[2:]
            if ":" in head:
                key, value = head.split(":", 1)
                value = value.strip()
                if value:
                    current[key.strip()] = value.strip().strip('"\'')
            continue

        if current is None:
            continue

        if stripped.startswith("- ") and list_key:
            current.setdefault(list_key, [])
            assert isinstance(current[list_key], list)
            current[list_key].append(stripped[2:].strip().strip('"\''))
            continue

        if ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not value:
                current[key] = []
                list_key = key
            elif value.startswith("["):
                current[key] = _parse_bracket_list(value)
                list_key = None
            else:
                current[key] = value.strip().strip('"\'')
                list_key = None

    if current:
        cases.append(current)

    return cases


class EvalHarness:
    def __init__(
        self,
        registry: SkillRegistry,
        store: MemoryStore | None = None,
        cases_path: Path | None = None,
        scorer: ResponseScorer | None = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self.cases_path = cases_path or (Path(__file__).with_name("cases.yaml"))
        self.scorer = scorer or ResponseScorer()

    def _load_static_cases(self) -> list[dict[str, Any]]:
        if not self.cases_path.exists():
            return []

        text = self.cases_path.read_text(encoding="utf-8")
        try:
            data = json.loads(text)
            cases = data.get("cases", []) if isinstance(data, dict) else []
            if isinstance(cases, list):
                return [case for case in cases if isinstance(case, dict)]
        except Exception:
            pass

        # Optional PyYAML support if installed.
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(text) or {}
            cases = data.get("cases", []) if isinstance(data, dict) else []
            if isinstance(cases, list):
                return [case for case in cases if isinstance(case, dict)]
        except Exception:
            pass

        parsed = _parse_simple_cases_yaml(text)
        return [case for case in parsed if isinstance(case, dict)]

    def _load_recent_cases(self, limit: int = 4) -> list[dict[str, Any]]:
        if not self.store:
            return []
        task_runs = self.store.get_recent_task_runs(limit=limit)
        recent_cases: list[dict[str, Any]] = []

        for run in task_runs:
            keywords = self.scorer.extract_keywords_from_text(run["task_input"])
            if not keywords:
                continue
            recent_cases.append(
                {
                    "id": f"recent-{run['task_run_id']}",
                    "skill": run["used_skill"],
                    "task": run["task_input"],
                    "expected_keywords": keywords,
                }
            )
        return recent_cases

    def _load_cases(self) -> list[dict[str, Any]]:
        return self._load_static_cases() + self._load_recent_cases()

    def _read_skill_text(
        self,
        skill_name: str,
        candidate_skill_paths: dict[str, Path] | None = None,
    ) -> str:
        candidate = (candidate_skill_paths or {}).get(skill_name)
        if candidate:
            skill_path = candidate
            if skill_path.is_dir():
                skill_path = skill_path / "SKILL.md"
            if skill_path.exists():
                return skill_path.read_text(encoding="utf-8")

        skill = self.registry.get_skill(skill_name)
        if not skill:
            return ""
        return skill.body_md_path.read_text(encoding="utf-8")

    def _run_safety_checks(
        self,
        candidate_skill_paths: dict[str, Path] | None,
    ) -> dict[str, bool]:
        checks = {
            "inside_skills_scope": True,
            "no_dangerous_commands": True,
        }

        allowed_skills = set(self.registry.list_skill_names())
        for skill_name, path in (candidate_skill_paths or {}).items():
            if skill_name not in allowed_skills:
                checks["inside_skills_scope"] = False
                continue

            target = path / "SKILL.md" if path.is_dir() else path
            if not target.exists() or target.name != "SKILL.md":
                checks["inside_skills_scope"] = False
                continue

            lowered = target.read_text(encoding="utf-8").lower()
            if "rm -rf" in lowered or "os.system(\"rm" in lowered:
                checks["no_dangerous_commands"] = False

        return checks

    def run_regression(
        self,
        candidate_skill_paths: dict[str, Path] | None = None,
    ) -> EvalReport:
        cases = self._load_cases()
        if not cases:
            return EvalReport(
                avg_score=0.0,
                per_case_scores={},
                regressions={},
                safety_checks=self._run_safety_checks(candidate_skill_paths),
                accepted=False,
                details={"reason": "no-cases"},
            )

        per_case_scores: dict[str, float] = {}
        regressions: dict[str, float] = {}

        for case in cases:
            case_id = str(case.get("id", "unknown"))
            skill_name = str(case.get("skill", ""))
            task = str(case.get("task", ""))
            keywords = [str(v) for v in (case.get("expected_keywords") or [])]

            skill_text = self._read_skill_text(
                skill_name=skill_name,
                candidate_skill_paths=candidate_skill_paths,
            )
            simulated_output = f"{skill_text}\n\nTask: {task}"
            score = self.scorer.score(simulated_output, expected_keywords=keywords)
            per_case_scores[case_id] = score
            if score < 0.35:
                regressions[case_id] = score

        avg = sum(per_case_scores.values()) / max(1, len(per_case_scores))
        safety_checks = self._run_safety_checks(candidate_skill_paths)
        accepted = avg >= 0.5 and not regressions and all(safety_checks.values())

        return EvalReport(
            avg_score=avg,
            per_case_scores=per_case_scores,
            regressions=regressions,
            safety_checks=safety_checks,
            accepted=accepted,
            details={"num_cases": len(cases)},
        )

    def find_missing_keywords(self, skill_name: str, current_text: str) -> list[str]:
        missing: list[str] = []
        lowered = current_text.lower()
        for case in self._load_cases():
            if case.get("skill") != skill_name:
                continue
            for keyword in case.get("expected_keywords", []):
                keyword = str(keyword)
                if keyword.lower() not in lowered and keyword not in missing:
                    missing.append(keyword)
        return missing
