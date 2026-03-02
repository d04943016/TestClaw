from __future__ import annotations


class ResponseScorer:
    def __init__(self) -> None:
        self._stopwords = {
            "the",
            "and",
            "with",
            "that",
            "this",
            "from",
            "your",
            "have",
            "will",
            "into",
            "about",
        }

    def keyword_score(self, text: str, expected_keywords: list[str]) -> float:
        if not expected_keywords:
            return 1.0

        normalized_text = text.lower()
        hits = 0
        for keyword in expected_keywords:
            if keyword.lower() in normalized_text:
                hits += 1
        return hits / len(expected_keywords)

    def structure_score(self, text: str) -> float:
        lowered = text.lower()
        markers = ["goal", "constraints", "steps", "output", "summary"]
        hits = sum(1 for marker in markers if marker in lowered)
        return min(1.0, hits / 3.0)

    def score(self, text: str, expected_keywords: list[str]) -> float:
        base = self.keyword_score(text=text, expected_keywords=expected_keywords)
        structure = self.structure_score(text=text)
        score = 0.75 * base + 0.25 * structure
        return max(0.0, min(1.0, score))

    def extract_keywords_from_text(self, text: str, limit: int = 4) -> list[str]:
        words = [w.strip(".,:;!?()[]{}\"'").lower() for w in text.split()]
        words = [w for w in words if len(w) >= 5 and w not in self._stopwords]
        unique: list[str] = []
        for word in words:
            if word not in unique:
                unique.append(word)
            if len(unique) >= limit:
                break
        return unique
