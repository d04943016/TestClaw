from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from myopenclaw.config import Settings
from myopenclaw.core.agent import OpenClawAgent


class ExampleCompatibilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.pack_root = self.repo_root / "skills" / "research_pack"

    def _build_demo_corpus(self, root: Path) -> None:
        (root / "oled").mkdir(parents=True, exist_ok=True)
        (root / "photonics").mkdir(parents=True, exist_ok=True)
        (root / "methods").mkdir(parents=True, exist_ok=True)
        (root / "oled" / "paper_oled_a.txt").write_text(
            "OLED efficiency roll-off relates to exciton quenching and triplet interactions.",
            encoding="utf-8",
        )
        (root / "oled" / "paper_oled_b.txt").write_text(
            "Metasurface OLED structures improve polarized emission and extraction efficiency.",
            encoding="utf-8",
        )
        (root / "photonics" / "paper_photonics_a.txt").write_text(
            "Inverse design improves photonic layouts with optimization and benchmark evaluation.",
            encoding="utf-8",
        )
        (root / "methods" / "paper_methods_a.txt").write_text(
            "Ablation, control-treatment design, and reproducibility are required for robust conclusions.",
            encoding="utf-8",
        )

    def _run_skill_script(
        self,
        skill_name: str,
        query: str,
        paper_root: Path,
        memory_context: list[str] | None = None,
    ) -> tuple[Path, dict]:
        script = self.pack_root / skill_name / "scripts" / "run.py"
        self.assertTrue(script.exists(), f"Missing script for {skill_name}")

        payload = {
            "task_context": query,
            "memory_context": memory_context or [],
            "skill": skill_name,
        }
        env = os.environ.copy()
        env["PAPER_ROOT"] = str(paper_root)

        proc = subprocess.run(
            [sys.executable, str(script)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=str(self.repo_root),
            env=env,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Artifacts:", proc.stdout)

        match = re.search(r"- JSON: (.+\.json)", proc.stdout)
        self.assertIsNotNone(match, f"JSON artifact path not found in output for {skill_name}")
        json_path = Path(str(match.group(1)).strip())
        if not json_path.is_absolute():
            json_path = self.repo_root / json_path
        self.assertTrue(json_path.exists(), f"Artifact missing for {skill_name}: {json_path}")
        return json_path, json.loads(json_path.read_text(encoding="utf-8"))

    def test_documented_research_skill_scripts_still_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper_root = Path(tmp) / "paper"
            self._build_demo_corpus(paper_root)

            _, deep_payload = self._run_skill_script(
                "research_deep_research_orchestrator",
                "請使用 research_deep_research_orchestrator。研究 OLED efficiency roll-off。focus: oled, exciton, triplet",
                paper_root=paper_root,
            )
            self.assertIn("query", deep_payload)

            _, rag_payload = self._run_skill_script(
                "research_rag",
                "請使用 research_rag。研究 metasurface OLED display pixel density optimization",
                paper_root=paper_root,
            )
            self.assertIn("top_candidates", rag_payload)

            _, graph_payload = self._run_skill_script(
                "research_graphrag",
                "請使用 research_graphrag。研究 inverse design for photonic OLED structures",
                paper_root=paper_root,
            )
            self.assertIn("communities", graph_payload)

            _, progressive_payload = self._run_skill_script(
                "research_progressive_reader",
                "請使用 research_progressive_reader。研究 polarized OLED emission mechanisms",
                paper_root=paper_root,
            )
            self.assertIn("plans", progressive_payload)

            evidence_json, evidence_payload = self._run_skill_script(
                "research_evidence_structurer",
                "請使用 research_evidence_structurer。整理關鍵證據",
                paper_root=paper_root,
            )
            self.assertIn("research_map", evidence_payload)

            _, gap_payload = self._run_skill_script(
                "research_gap_finder",
                "請使用 research_gap_finder。目前文獻還缺什麼關鍵證據？",
                paper_root=paper_root,
            )
            self.assertIn("gaps", gap_payload)

            _, hypo_payload = self._run_skill_script(
                "research_hypothesis_generator",
                "請使用 research_hypothesis_generator。提出可驗證假說",
                paper_root=paper_root,
                memory_context=[str(evidence_json)],
            )
            self.assertIn("sufficient_evidence", hypo_payload)

            _, study_payload = self._run_skill_script(
                "research_study_designer",
                "請使用 research_study_designer。如何驗證假說 H1/H2？",
                paper_root=paper_root,
                memory_context=[str(evidence_json)],
            )
            self.assertIn("designs", study_payload)

    def test_documented_prompts_still_route_in_agent_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paper_root = tmp_path / "paper"
            self._build_demo_corpus(paper_root)

            old_paper_root = os.environ.get("PAPER_ROOT")
            os.environ["PAPER_ROOT"] = str(paper_root)
            try:
                settings = Settings(project_root=tmp_path)
                settings.skills_dir = self.repo_root / "skills"
                agent = OpenClawAgent(settings=settings)
                agent.evolver.post_task_evolve = lambda task_run_id: None  # type: ignore[method-assign]

                prompts = [
                    ("research_deep_research_orchestrator", "請使用 research_deep_research_orchestrator。研究 OLED efficiency roll-off"),
                    ("research_rag", "請使用 research_rag。研究 metasurface OLED display pixel density optimization"),
                    ("research_graphrag", "請使用 research_graphrag。研究 inverse design for photonic OLED structures"),
                    ("research_progressive_reader", "請使用 research_progressive_reader。研究 polarized OLED emission mechanisms"),
                    ("research_evidence_structurer", "請使用 research_evidence_structurer。整理上述檢索到的關鍵論文證據"),
                ]

                for expected_skill, prompt in prompts:
                    turn = agent.run_turn(session_id="compat-agent", user_input=prompt, token_budget=800)
                    self.assertEqual(turn.used_skill, expected_skill)
                    self.assertIn("Artifacts:", turn.response)
                    self.assertTrue(turn.trace)

                agent.close()
            finally:
                if old_paper_root is None:
                    os.environ.pop("PAPER_ROOT", None)
                else:
                    os.environ["PAPER_ROOT"] = old_paper_root


if __name__ == "__main__":
    unittest.main()
