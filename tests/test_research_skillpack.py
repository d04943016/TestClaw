from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ResearchSkillPackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.pack_root = self.repo_root / "skills" / "research_pack"
        self.skills = [
            "research_deep_research_orchestrator",
            "research_rag",
            "research_graphrag",
            "research_progressive_reader",
            "research_evidence_structurer",
            "research_hypothesis_generator",
            "research_gap_finder",
            "research_study_designer",
        ]

    def test_pack_structure(self) -> None:
        self.assertTrue(self.pack_root.exists())
        self.assertTrue((self.pack_root / "_shared" / "research_utils.py").exists())

        for skill in self.skills:
            skill_dir = self.pack_root / skill
            self.assertTrue(skill_dir.exists(), f"Missing skill folder: {skill}")
            self.assertTrue((skill_dir / "SKILL.md").exists(), f"Missing SKILL.md: {skill}")
            self.assertTrue((skill_dir / "scripts" / "run.py").exists(), f"Missing entry script: {skill}")

    def test_skill_entries_are_symlinked_for_runtime(self) -> None:
        for skill in self.skills:
            link = self.repo_root / "skills" / skill
            self.assertTrue(link.exists(), f"Missing runtime skill entry: {skill}")
            self.assertTrue(link.is_symlink(), f"Runtime entry should be symlink: {skill}")
            resolved = link.resolve()
            self.assertEqual(resolved, (self.pack_root / skill).resolve())

    def test_skill_specs_define_entry_script(self) -> None:
        for skill in self.skills:
            text = (self.pack_root / skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("entry_script: run.py", text)
            self.assertIn("description:", text)
            self.assertIn("outputs:", text)
            self.assertIn("constraints:", text)

    def test_deep_research_doc_exists_with_prompting_guidance(self) -> None:
        guide = self.repo_root / "docs" / "ACADEMIC_DEEP_RESEARCH_SKILLPACK_zh-TW.md"
        self.assertTrue(guide.exists())
        text = guide.read_text(encoding="utf-8")
        self.assertIn("是否可「自行建構」", text)
        self.assertIn("如何 prompting", text)
        self.assertIn("research_deep_research_orchestrator", text)

    def test_orchestrator_script_smoke(self) -> None:
        script = self.pack_root / "research_deep_research_orchestrator" / "scripts" / "run.py"
        self.assertTrue(script.exists())

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "paper_a.txt").write_text(
                "OLED efficiency roll-off mechanisms with exciton and triplet interactions.",
                encoding="utf-8",
            )
            (tmp_path / "paper_b.txt").write_text(
                "Metasurface design improves pixel density and polarized emission.",
                encoding="utf-8",
            )
            sub = tmp_path / "topic"
            sub.mkdir(parents=True, exist_ok=True)
            (sub / "paper_c.txt").write_text(
                "Inverse design for photonic structures with optimization methods.",
                encoding="utf-8",
            )

            payload = {
                "task_context": "research_deep_research_orchestrator: study OLED efficiency roll-off",
                "memory_context": ["focus: oled, exciton, triplet"],
                "skill": "research_deep_research_orchestrator",
            }

            env = os.environ.copy()
            env["PAPER_ROOT"] = str(tmp_path)

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
            self.assertIn("deep_research_report.json", proc.stdout)

            match = re.search(r"- JSON: (.+deep_research_report\.json)", proc.stdout)
            self.assertIsNotNone(match)
            artifact_json = Path(match.group(1).strip())
            if not artifact_json.is_absolute():
                artifact_json = self.repo_root / artifact_json
            self.assertTrue(artifact_json.exists())

            payload_json = json.loads(artifact_json.read_text(encoding="utf-8"))
            self.assertIn("query", payload_json)
            self.assertIn("retrieval", payload_json)
            self.assertIn("evidence_rows", payload_json)


if __name__ == "__main__":
    unittest.main()
