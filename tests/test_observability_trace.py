from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from myopenclaw.cli import _cmd_trace_tail
from myopenclaw.config import Settings
from myopenclaw.core.agent import OpenClawAgent
from myopenclaw.core.planner import TaskPlanner
from myopenclaw.core.types import EvalReport
from myopenclaw.memory.store import MemoryStore
from myopenclaw.skills.registry import SkillRegistry


def _write_skill(skills_root: Path, name: str, description: str, inputs: list[str], constraints: list[str]) -> None:
    folder = skills_root / name
    folder.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        [
            "---",
            f"name: {name}",
            "version: 0.1.0",
            f"description: {description}",
            "inputs:",
            *[f"  - {item}" for item in inputs],
            "outputs:",
            "  - output",
            "constraints:",
            *[f"  - {item}" for item in constraints],
            "---",
            f"# {name}",
            "Provide structured output with goal, constraints, and steps.",
        ]
    )
    (folder / "SKILL.md").write_text(content, encoding="utf-8")


class ObservabilityTraceTest(unittest.TestCase):
    def test_planner_returns_confidence_and_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            settings = Settings(project_root=tmp_path)
            _write_skill(
                settings.skills_dir,
                "research_rag",
                "retrieve papers",
                ["query", "focus"],
                ["evidence", "traceability"],
            )
            _write_skill(
                settings.skills_dir,
                "plan",
                "planning tasks",
                ["goal"],
                ["scope"],
            )
            registry = SkillRegistry(settings.skills_dir)
            registry.load_skills()
            planner = TaskPlanner(registry=registry)

            decision = planner.choose_skill_with_trace(
                "please use research_rag for literature retrieval and evidence"
            )
            self.assertIn("chosen_skill", decision)
            self.assertIn("confidence", decision)
            self.assertIn("top_candidates", decision)
            self.assertEqual(decision["chosen_skill"], "research_rag")
            self.assertGreaterEqual(float(decision["confidence"]), 0.0)
            self.assertLessEqual(float(decision["confidence"]), 1.0)

    def test_agent_persists_trace_into_task_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            settings = Settings(project_root=tmp_path)
            settings.short_term_window = 6
            settings.chunk_target_tokens = 40
            _write_skill(
                settings.skills_dir,
                "summarize",
                "summarize requests",
                ["raw_text"],
                ["factual", "constraints"],
            )

            agent = OpenClawAgent(settings=settings)
            agent.evolver.post_task_evolve = lambda task_run_id: EvalReport(  # type: ignore[method-assign]
                avg_score=0.4,
                per_case_scores={"x": 0.4},
                regressions={"x": -0.3},
                safety_checks={"inside_skills_scope": True, "no_dangerous_commands": True},
                accepted=False,
                details={"gate": {"reject_reasons": ["regressions_detected(1)"]}},
            )

            turn = agent.run_turn(
                session_id="obs",
                user_input="Summarize this architecture and include constraints.",
                token_budget=500,
            )
            self.assertTrue(turn.trace)
            self.assertIn("planner", turn.trace or {})
            self.assertIn("memory", turn.trace or {})
            self.assertIn("executor", turn.trace or {})
            self.assertIn("evolution", turn.trace or {})

            rows = agent.store.get_recent_task_runs(limit=1, session_id="obs")
            self.assertEqual(len(rows), 1)
            trace = rows[0].get("trace", {})
            self.assertEqual(trace.get("planner", {}).get("chosen_skill"), turn.used_skill)
            self.assertIn("search_hits_considered", trace.get("memory", {}))
            self.assertIn("accepted", trace.get("evolution", {}))
            agent.close()

    def test_cli_trace_tail_outputs_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            settings = Settings(project_root=tmp_path)
            store = MemoryStore(settings.db_path)
            store.add_task_run(
                task_run_id="task-test",
                session_id="trace-session",
                task_input="input",
                response="output",
                used_skill="summarize",
                quality_score=0.9,
                trace={"planner": {"chosen_skill": "summarize"}},
            )
            store.close()

            old_cwd = os.getcwd()
            os.chdir(tmp_path)
            try:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = _cmd_trace_tail(argparse.Namespace(session="trace-session", limit=3))
                self.assertEqual(code, 0)
                payload = json.loads(buf.getvalue())
                self.assertIn("runs", payload)
                self.assertEqual(len(payload["runs"]), 1)
                self.assertEqual(payload["runs"][0]["task_run_id"], "task-test")
                self.assertEqual(
                    payload["runs"][0]["trace"]["planner"]["chosen_skill"], "summarize"
                )
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
