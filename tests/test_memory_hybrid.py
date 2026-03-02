from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from myopenclaw.config import Settings
from myopenclaw.memory.manager import MemoryManager


class MemoryHybridRetrieverTest(unittest.TestCase):
    def test_hybrid_search_returns_semantic_and_keyword_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(project_root=Path(tmp))
            settings.short_term_window = 8
            settings.chunk_target_tokens = 45

            manager = MemoryManager(settings=settings)
            session_id = "hybrid-memory"

            messages = [
                "OLED efficiency roll-off is linked to exciton quenching and triplet dynamics.",
                "Metasurface patterning can shape polarized light extraction in OLED devices.",
                "Inverse design optimization improves nano-photonic device performance.",
                "Graph-based retrieval can connect related literature communities.",
                "Progressive reading starts from figures and abstract before methods.",
                "Evidence structuring requires source-linked tables and audit trails.",
                "Hypothesis generation should be falsifiable and evidence-grounded.",
                "Gap analysis highlights under-covered terms in the literature.",
                "Research workflow should output JSON and markdown artifacts.",
                "Study design needs control, treatment, and measurable metrics.",
                "Keyword and semantic retrieval should be hybridized for robustness.",
                "Token-efficient reading can reduce cost while preserving quality.",
            ]

            for idx, text in enumerate(messages):
                manager.append_message(
                    session_id=session_id,
                    role="user" if idx % 2 == 0 else "assistant",
                    content=text,
                )

            changed = manager.compress_if_needed(session_id)
            self.assertTrue(changed)

            hits = manager.retriever.search(
                session_id=session_id,
                query="how to perform hybrid semantic keyword literature retrieval",
                top_k=4,
            )
            self.assertTrue(hits)
            top = hits[0]
            self.assertIn("semantic_score", top)
            self.assertIn("keyword_score", top)
            self.assertIn("retrieval_backend", top)
            self.assertIn("score", top)

            manager.get_store().close()

    def test_embedding_key_separation_contract(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        retriever_text = (repo_root / "src" / "myopenclaw" / "memory" / "retriever.py").read_text(encoding="utf-8")
        utils_text = (
            repo_root / "skills" / "research_pack" / "_shared" / "research_utils.py"
        ).read_text(encoding="utf-8")

        self.assertIn("AGENT_EMBEDDING_API_KEY", retriever_text)
        self.assertIn("SKILL_EMBEDDING_API_KEY", utils_text)
        self.assertNotIn("SKILL_EMBEDDING_API_KEY", retriever_text)
        self.assertNotIn("AGENT_EMBEDDING_API_KEY", utils_text)


if __name__ == "__main__":
    unittest.main()
