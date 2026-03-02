from __future__ import annotations

import re
import unittest
from pathlib import Path


class DocsGuideTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.guide = self.repo_root / "docs" / "AGENTIC_SYSTEM_DESIGN_GUIDE_zh-TW.md"
        self.manual = self.repo_root / "docs" / "USER_MANUAL_zh-TW.md"
        self.templates = self.repo_root / "docs" / "CASE_TEMPLATES_zh-TW.md"
        self.roadmap = self.repo_root / "docs" / "TECHNICAL_ROADMAP_zh-TW.md"
        self.survey_readme = self.repo_root / "skills" / "research_pack" / "README_SURVEY_AGENT_zh-TW.md"

    def test_agentic_design_guide_exists(self) -> None:
        self.assertTrue(self.guide.exists(), "Design guide should exist in docs/")

    def test_design_core_and_rules_sections_exist(self) -> None:
        text = self.guide.read_text(encoding="utf-8")
        self.assertIn("Agentic 系統核心設計概念", text)
        self.assertIn("Design Rules", text)
        self.assertIn("如何基於本框架設計你自己的 Agent 系統", text)
        self.assertIn("反模式與避免方式", text)

    def test_design_guide_has_mermaid_diagrams(self) -> None:
        text = self.guide.read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count("```mermaid"), 5, "Design guide should include at least 5 diagrams")

    def test_has_five_scenarios(self) -> None:
        text = self.guide.read_text(encoding="utf-8")
        scenarios = re.findall(r"### 案例\s*([1-5])", text)
        self.assertEqual(len(scenarios), 5, "Guide should provide exactly 5 scenario cases")
        self.assertEqual(sorted(set(scenarios)), ["1", "2", "3", "4", "5"])

    def test_every_scenario_has_design_and_validation_blocks(self) -> None:
        text = self.guide.read_text(encoding="utf-8")
        blocks = [f"### 案例 {idx}：" for idx in range(1, 6)]
        for marker in blocks:
            self.assertIn(marker, text)
        required_keywords = ["技術設計", "設定位置", "驗收"]
        for keyword in required_keywords:
            count = text.count(keyword)
            self.assertGreaterEqual(count, 5, f"Expected keyword '{keyword}' at least 5 times")

    def test_manual_links_to_design_guide(self) -> None:
        text = self.manual.read_text(encoding="utf-8")
        self.assertIn("AGENTIC_SYSTEM_DESIGN_GUIDE_zh-TW.md", text)
        self.assertIn("TECHNICAL_ROADMAP_zh-TW.md", text)

    def test_case_templates_exists_and_has_five_scenarios(self) -> None:
        self.assertTrue(self.templates.exists(), "Case templates guide should exist in docs/")
        text = self.templates.read_text(encoding="utf-8")
        scenarios = re.findall(r"##\s*\d+\.\s*模板案例\s*([1-5])", text)
        self.assertEqual(len(scenarios), 5, "Templates guide should provide exactly 5 template scenarios")
        self.assertEqual(sorted(set(scenarios)), ["1", "2", "3", "4", "5"])

    def test_case_templates_have_required_sections(self) -> None:
        text = self.templates.read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count("Eval Case 模板"), 5)
        self.assertGreaterEqual(text.count("Memory 初始設定"), 5)
        self.assertGreaterEqual(text.count("驗證步驟"), 5)

    def test_readme_links_to_case_templates(self) -> None:
        readme = (self.repo_root / "README.md").read_text(encoding="utf-8")
        self.assertIn("CASE_TEMPLATES_zh-TW.md", readme)
        self.assertIn("ACADEMIC_DEEP_RESEARCH_SKILLPACK_zh-TW.md", readme)
        self.assertIn("TECHNICAL_ROADMAP_zh-TW.md", readme)
        self.assertIn("README_SURVEY_AGENT_zh-TW.md", readme)

    def test_survey_agent_readme_exists(self) -> None:
        self.assertTrue(self.survey_readme.exists(), "Survey-agent README should exist in skills/research_pack/")
        text = self.survey_readme.read_text(encoding="utf-8")
        self.assertIn("Survey 研究智能體 README", text)
        self.assertIn("API Key 分離", text)
        self.assertIn("research_deep_research_orchestrator", text)

    def test_technical_roadmap_exists(self) -> None:
        self.assertTrue(self.roadmap.exists(), "Technical roadmap should exist in docs/")
        text = self.roadmap.read_text(encoding="utf-8")
        required = [
            "Phase A",
            "Phase B",
            "Phase C",
            "Phase D",
            "Phase E",
            "Phase F",
            "KPI 與驗收門檻",
            "Cross-Cutting Design Rules",
        ]
        for token in required:
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
