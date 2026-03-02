from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from myopenclaw.config import Settings


class ResearchProfileTest(unittest.TestCase):
    def test_settings_loads_profile_file(self) -> None:
        tracked_keys = [
            "MYOPENCLAW_PROFILE",
            "MEMORY_SHORT_TERM_WINDOW",
            "MEMORY_CHUNK_TARGET_TOKENS",
            "MEMORY_ROLLUP_BATCH_SIZE",
            "AGENT_MEMORY_TOP_K",
        ]
        backup = {key: os.environ.get(key) for key in tracked_keys}
        try:
            for key in tracked_keys:
                os.environ.pop(key, None)

            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                (tmp_path / ".env").write_text(
                    "MYOPENCLAW_PROFILE=profiles/paper.env\n",
                    encoding="utf-8",
                )
                profile = tmp_path / "profiles" / "paper.env"
                profile.parent.mkdir(parents=True, exist_ok=True)
                profile.write_text(
                    "\n".join(
                        [
                            "MEMORY_SHORT_TERM_WINDOW=44",
                            "MEMORY_CHUNK_TARGET_TOKENS=860",
                            "MEMORY_ROLLUP_BATCH_SIZE=7",
                            "AGENT_MEMORY_TOP_K=9",
                        ]
                    ),
                    encoding="utf-8",
                )

                settings = Settings(project_root=tmp_path)
                self.assertEqual(settings.active_profile_path, profile.resolve())
                self.assertEqual(settings.short_term_window, 44)
                self.assertEqual(settings.chunk_target_tokens, 860)
                self.assertEqual(settings.rollup_batch_size, 7)
                self.assertEqual(settings.memory_retrieval_top_k, 9)
        finally:
            for key, value in backup.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_paper_profile_exists_and_has_expected_knobs(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        profile = repo_root / "profiles" / "paper_deep_research.env"
        self.assertTrue(profile.exists())
        text = profile.read_text(encoding="utf-8")
        required = [
            "PAPER_ROOT=",
            "AGENT_MEMORY_SEMANTIC_WEIGHT=",
            "AGENT_MEMORY_TOP_K=",
            "MEMORY_SHORT_TERM_WINDOW=",
            "MEMORY_CHUNK_TARGET_TOKENS=",
            "SKILL_MEMORY_SEMANTIC_WEIGHT=",
            "SKILL_FILE_SCAN_LIMIT=",
            "SKILL_RETRIEVAL_TOP_K=",
            "SKILL_SEMANTIC_PREVIEW_COUNT=",
        ]
        for key in required:
            self.assertIn(key, text)

    def test_research_scripts_use_profile_tunable_limits(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        scripts = sorted((repo_root / "skills" / "research_pack").glob("*/scripts/run.py"))
        self.assertTrue(scripts, "Expected research skill scripts to exist")

        for script in scripts:
            text = script.read_text(encoding="utf-8")
            if "collect_paper_files(" in text:
                self.assertIn("skill_scan_limit(", text, f"{script} should use skill_scan_limit")
            if "rank_files(" in text:
                self.assertIn("skill_top_k(", text, f"{script} should use skill_top_k")


if __name__ == "__main__":
    unittest.main()
