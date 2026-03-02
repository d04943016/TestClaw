from __future__ import annotations

import difflib
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from myopenclaw.config import Settings
from myopenclaw.core.types import EvalReport, EvolutionDecision, SkillPatch
from myopenclaw.evals.harness import EvalHarness
from myopenclaw.llm.router import LLMRouter
from myopenclaw.memory.store import MemoryStore
from myopenclaw.skills.registry import SkillRegistry, _parse_frontmatter
from myopenclaw.skills.sandbox import SkillSandbox


class SkillEvolver:
    def __init__(
        self,
        settings: Settings,
        registry: SkillRegistry,
        harness: EvalHarness,
        store: MemoryStore,
        router: LLMRouter | None = None,
        sandbox: SkillSandbox | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.harness = harness
        self.store = store
        self.router = router
        self.sandbox = sandbox or SkillSandbox(settings.skills_dir)

    def post_task_evolve(self, task_run_id: str) -> EvalReport | None:
        decision = self._decide_evolution(task_run_id=task_run_id)
        if not decision.should_evolve:
            return None

        patch = self.propose_mutation(
            skill_name=decision.target_skill,
            hypothesis=decision.hypothesis,
        )
        report = self.evaluate_candidate(patch)
        self.apply_or_rollback(skill_patch=patch, eval_report=report)
        return report

    def _decide_evolution(self, task_run_id: str) -> EvolutionDecision:
        task = self.store.get_task_run(task_run_id)
        skill_names = self.registry.list_skill_names()
        default_skill = task["used_skill"] if task else (skill_names[0] if skill_names else "")

        if not task:
            return EvolutionDecision(False, default_skill, "No task run record found.")

        if self.router and skill_names:
            try:
                response = self.router.generate(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Decide if skills should evolve after this task. "
                                "Return JSON with keys: should_evolve (bool), target_skill (string), hypothesis (string)."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "task_run": task,
                                    "available_skills": skill_names,
                                    "policy": {
                                        "edit_scope": "skills/* only",
                                        "goal": "improve future performance",
                                    },
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    temperature=0.1,
                )
                parsed = json.loads(response.content)
                should_evolve = bool(parsed.get("should_evolve"))
                target_skill = str(parsed.get("target_skill") or default_skill)
                if target_skill not in skill_names:
                    target_skill = default_skill
                hypothesis = str(parsed.get("hypothesis") or "Improve response quality.")
                return EvolutionDecision(
                    should_evolve=should_evolve,
                    target_skill=target_skill,
                    hypothesis=hypothesis,
                )
            except Exception:
                pass

        should = float(task.get("quality_score", 0.0)) < 0.75
        hypothesis = "Improve clarity, constraints handling, and actionability."
        return EvolutionDecision(
            should_evolve=should,
            target_skill=default_skill,
            hypothesis=hypothesis,
        )

    def _snapshot_root(self, skill_name: str, snapshot_id: str) -> Path:
        root = self.settings.state_dir / skill_name / snapshot_id
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _split_skill_content(self, content: str) -> tuple[dict[str, Any], str]:
        if content.startswith("---\n"):
            parts = content.split("\n---\n", 1)
            if len(parts) == 2:
                metadata = _parse_frontmatter(parts[0].removeprefix("---\n"))
                return metadata, parts[1]
        return {}, content

    def _dump_frontmatter(self, metadata: dict[str, Any]) -> str:
        lines: list[str] = []
        for key, value in metadata.items():
            if isinstance(value, list):
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)

    def _join_skill_content(self, metadata: dict[str, Any], body: str) -> str:
        if metadata:
            return f"---\n{self._dump_frontmatter(metadata).strip()}\n---\n{body.strip()}\n"
        return body.strip() + "\n"

    def _increment_version(self, version: str) -> str:
        parts = version.split(".")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            return "0.1.1"
        major, minor, patch = [int(p) for p in parts]
        return f"{major}.{minor}.{patch + 1}"

    def _mutate_content(self, skill_name: str, source_text: str, hypothesis: str) -> str:
        metadata, body = self._split_skill_content(source_text)
        metadata["version"] = self._increment_version(str(metadata.get("version", "0.1.0")))

        missing_keywords = self.harness.find_missing_keywords(skill_name=skill_name, current_text=source_text)
        keyword_text = ", ".join(missing_keywords[:8]) if missing_keywords else "goal, constraints, steps, output"

        if self.router:
            try:
                response = self.router.generate(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You improve one agent skill file. Keep it concise, preserve structure, "
                                "and improve task success. Return only markdown body content."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Skill: {skill_name}\n"
                                f"Hypothesis: {hypothesis}\n"
                                f"Must include keywords: {keyword_text}\n\n"
                                f"Current body:\n{body}"
                            ),
                        },
                    ],
                    temperature=0.2,
                )
                candidate_body = response.content.strip()
                if candidate_body:
                    return self._join_skill_content(metadata, candidate_body)
            except Exception:
                pass

        improvement_block = (
            "\n\n## Auto-Improvement\n"
            f"- Hypothesis: {hypothesis}\n"
            f"- Ensure responses explicitly include: {keyword_text}.\n"
            "- Preserve source facts, decisions, assumptions, and unresolved issues.\n"
            "- Prefer structured output with goal, constraints, steps, risks, and expected output.\n"
        )
        return self._join_skill_content(metadata, body.strip() + improvement_block)

    def propose_mutation(self, skill_name: str, hypothesis: str | None = None) -> SkillPatch:
        skill = self.registry.get_skill(skill_name)
        if not skill:
            raise KeyError(f"Unknown skill: {skill_name}")

        snapshot_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
        snapshot_root = self._snapshot_root(skill_name=skill_name, snapshot_id=snapshot_id)

        source_dir = skill.body_md_path.parent
        original_dir = snapshot_root / "original" / skill_name
        candidate_dir = snapshot_root / "candidate" / skill_name
        original_dir.parent.mkdir(parents=True, exist_ok=True)
        candidate_dir.parent.mkdir(parents=True, exist_ok=True)

        shutil.copytree(source_dir, original_dir)
        shutil.copytree(source_dir, candidate_dir)

        source_skill = source_dir / "SKILL.md"
        candidate_skill = candidate_dir / "SKILL.md"

        source_text = source_skill.read_text(encoding="utf-8")
        mutation_hypothesis = hypothesis or "Improve skill quality from recent failures."
        candidate_text = self._mutate_content(
            skill_name=skill_name,
            source_text=source_text,
            hypothesis=mutation_hypothesis,
        )
        candidate_skill.write_text(candidate_text, encoding="utf-8")

        diff_lines = difflib.unified_diff(
            source_text.splitlines(keepends=True),
            candidate_text.splitlines(keepends=True),
            fromfile=str(source_skill),
            tofile=str(candidate_skill),
        )
        diff_path = snapshot_root / "patch.diff"
        diff_path.write_text("".join(diff_lines), encoding="utf-8")

        return SkillPatch(
            skill_name=skill_name,
            source_path=source_skill,
            candidate_path=candidate_dir,
            hypothesis=mutation_hypothesis,
            diff_path=diff_path,
            snapshot_id=snapshot_id,
        )

    def evaluate_candidate(self, skill_patch: SkillPatch) -> EvalReport:
        baseline_report = self.harness.run_regression(candidate_skill_paths=None)
        candidate_report = self.harness.run_regression(
            candidate_skill_paths={skill_patch.skill_name: skill_patch.candidate_path}
        )

        regressions: dict[str, float] = {}
        for case_id, baseline_score in baseline_report.per_case_scores.items():
            candidate_score = candidate_report.per_case_scores.get(case_id, baseline_score)
            delta = candidate_score - baseline_score
            if delta < self.settings.evolution_regression_floor:
                regressions[case_id] = delta

        avg_delta = candidate_report.avg_score - baseline_report.avg_score
        failed_safety_checks = [name for name, status in candidate_report.safety_checks.items() if not status]
        reject_reasons: list[str] = []
        if avg_delta < self.settings.evolution_improvement_threshold:
            reject_reasons.append(
                f"avg_delta_below_threshold({avg_delta:.3f} < {self.settings.evolution_improvement_threshold:.3f})"
            )
        if regressions:
            reject_reasons.append(f"regressions_detected({len(regressions)})")
        if failed_safety_checks:
            reject_reasons.append("safety_failed:" + ",".join(failed_safety_checks))

        accepted = (
            avg_delta >= self.settings.evolution_improvement_threshold
            and not regressions
            and all(candidate_report.safety_checks.values())
        )

        return EvalReport(
            avg_score=candidate_report.avg_score,
            per_case_scores=candidate_report.per_case_scores,
            regressions=regressions,
            safety_checks=candidate_report.safety_checks,
            accepted=accepted,
            details={
                "baseline_avg": baseline_report.avg_score,
                "candidate_avg": candidate_report.avg_score,
                "avg_delta": avg_delta,
                "snapshot_id": skill_patch.snapshot_id,
                "hypothesis": skill_patch.hypothesis,
                "gate": {
                    "accepted": accepted,
                    "threshold": self.settings.evolution_improvement_threshold,
                    "avg_delta": avg_delta,
                    "regressions": len(regressions),
                    "failed_safety_checks": failed_safety_checks,
                    "reject_reasons": reject_reasons,
                },
            },
        )

    def apply_or_rollback(self, skill_patch: SkillPatch, eval_report: EvalReport) -> dict[str, Any]:
        snapshot_root = skill_patch.diff_path.parent
        report_path = snapshot_root / "eval_report.json"
        report_path.write_text(
            json.dumps(
                {
                    "avg_score": eval_report.avg_score,
                    "per_case_scores": eval_report.per_case_scores,
                    "regressions": eval_report.regressions,
                    "safety_checks": eval_report.safety_checks,
                    "accepted": eval_report.accepted,
                    "details": eval_report.details,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        if not eval_report.accepted:
            return {"applied": False, "reason": "gate_rejected", "report": str(report_path)}

        target_dir = skill_patch.source_path.parent
        backup_dir = snapshot_root / "rollback_backup" / skill_patch.skill_name
        backup_dir.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copytree(target_dir, backup_dir)
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(skill_patch.candidate_path, target_dir)
            self.registry.load_skills()
            return {"applied": True, "report": str(report_path)}
        except Exception as exc:
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(backup_dir, target_dir)
            return {
                "applied": False,
                "reason": f"rollback:{exc}",
                "report": str(report_path),
            }
