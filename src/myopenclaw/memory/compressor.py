from __future__ import annotations

from collections import Counter
from typing import Any

from myopenclaw.llm.router import LLMRouter


class MemoryCompressor:
    def __init__(self, router: LLMRouter | None = None) -> None:
        self.router = router

    def chunk_messages(
        self,
        messages: list[dict[str, Any]],
        target_tokens: int,
    ) -> list[list[dict[str, Any]]]:
        if not messages:
            return []

        chunks: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        current_tokens = 0

        for message in messages:
            msg_tokens = int(message.get("tokens", 0))
            if current and current_tokens + msg_tokens > target_tokens:
                chunks.append(current)
                current = []
                current_tokens = 0
            current.append(message)
            current_tokens += msg_tokens

        if current:
            chunks.append(current)

        return chunks

    def summarize_messages(self, messages: list[dict[str, Any]], level: int) -> str:
        text = "\n".join(f"[{m['role']}] {m['content']}" for m in messages)
        return self.summarize_text(text=text, level=level)

    def summarize_text(self, text: str, level: int) -> str:
        if self.router:
            try:
                response = self.router.generate(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You compress conversation memory. Return concise summary preserving facts, "
                                "decisions, constraints, and unresolved questions."
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"Compression level L{level}. Summarize:\n\n{text}",
                        },
                    ],
                    temperature=0.0,
                )
                if response.content.strip():
                    return response.content.strip()
            except Exception:
                pass

        # Deterministic fallback summary for offline mode/tests.
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        head = lines[:3]
        tail = lines[-2:] if len(lines) > 3 else []

        words = [w.strip(".,:;!?()[]{}\"'").lower() for w in text.split()]
        words = [w for w in words if len(w) >= 5]
        common = [w for w, _ in Counter(words).most_common(6)]

        pieces = []
        if head:
            pieces.append("Key points: " + " | ".join(head))
        if tail:
            pieces.append("Latest state: " + " | ".join(tail))
        if common:
            pieces.append("Topics: " + ", ".join(common))

        return f"[L{level}] " + " ".join(pieces)
