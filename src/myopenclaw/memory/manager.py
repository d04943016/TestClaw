from __future__ import annotations

import itertools
from typing import Any

from myopenclaw.config import Settings
from myopenclaw.core.types import RetrievedContext
from myopenclaw.memory.compressor import MemoryCompressor
from myopenclaw.memory.retriever import MemoryRetriever
from myopenclaw.memory.store import MemoryStore


class MemoryManager:
    def __init__(
        self,
        settings: Settings,
        store: MemoryStore | None = None,
        compressor: MemoryCompressor | None = None,
        retriever: MemoryRetriever | None = None,
    ) -> None:
        self.settings = settings
        self.store = store or MemoryStore(settings.db_path)
        self.compressor = compressor or MemoryCompressor()
        self.retriever = retriever or MemoryRetriever(settings=settings, store=self.store)

    def _estimate_tokens(self, text: str) -> int:
        # Lightweight approximation to avoid tokenizer dependencies in MVP.
        return max(1, int(len(text.split()) * 1.2))

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tokens: int | None = None,
    ) -> int:
        effective_tokens = tokens if tokens is not None else self._estimate_tokens(content)
        return self.store.add_message(
            session_id=session_id,
            role=role,
            content=content,
            tokens=effective_tokens,
        )

    def compress_if_needed(self, session_id: str) -> bool:
        messages = self.store.get_messages(session_id)
        if len(messages) <= self.settings.short_term_window:
            return False

        older_messages = messages[: -self.settings.short_term_window]
        if not older_messages:
            return False

        chunks = self.compressor.chunk_messages(
            older_messages,
            target_tokens=self.settings.chunk_target_tokens,
        )

        for chunk in chunks:
            summary = self.compressor.summarize_messages(messages=chunk, level=1)
            source_ids = [int(message["id"]) for message in chunk]
            self.store.add_compressed_chunk(
                session_id=session_id,
                level=1,
                content=summary,
                source_ids=source_ids,
            )

        self.store.delete_messages([int(message["id"]) for message in older_messages])
        self._rollup(session_id=session_id, from_level=1, to_level=2)
        self._rollup(session_id=session_id, from_level=2, to_level=3)
        return True

    def _rollup(self, session_id: str, from_level: int, to_level: int) -> None:
        while True:
            pending = self.store.get_compressed_chunks(
                session_id=session_id,
                level=from_level,
                only_unrolled=True,
                limit=self.settings.rollup_batch_size,
            )
            if len(pending) < self.settings.rollup_batch_size:
                return

            joined = "\n".join(f"[chunk:{c['id']}] {c['content']}" for c in pending)
            summary = self.compressor.summarize_text(joined, level=to_level)

            source_ids = sorted(
                set(
                    itertools.chain.from_iterable(
                        [chunk.get("source_ids", []) for chunk in pending]
                    )
                )
            )
            parent_ids = [int(chunk["id"]) for chunk in pending]

            self.store.add_compressed_chunk(
                session_id=session_id,
                level=to_level,
                content=summary,
                source_ids=[int(value) for value in source_ids],
                parent_chunk_ids=parent_ids,
            )
            self.store.mark_chunks_rolled(parent_ids)

    def retrieve(self, query: str, session_id: str, token_budget: int) -> RetrievedContext:
        segments: list[str] = []
        used_tokens = 0
        trace: dict[str, Any] = {
            "token_budget": token_budget,
            "recent_messages_considered": 0,
            "recent_messages_included": 0,
            "search_hits_considered": 0,
            "search_hits_included": [],
            "high_level_included": [],
            "search_top_k": self.settings.memory_retrieval_top_k,
        }

        recent_messages = self.store.get_recent_messages(
            session_id=session_id,
            limit=self.settings.short_term_window,
        )
        trace["recent_messages_considered"] = len(recent_messages)
        for message in recent_messages:
            text = f"[recent:{message['role']}] {message['content']}"
            message_tokens = int(message["tokens"])
            if used_tokens + message_tokens > token_budget:
                break
            segments.append(text)
            used_tokens += message_tokens
            trace["recent_messages_included"] = int(trace["recent_messages_included"]) + 1

        if used_tokens >= token_budget:
            trace["used_tokens"] = used_tokens
            trace["segments_returned"] = len(segments)
            return RetrievedContext(segments=segments, total_tokens=used_tokens, metadata=trace)

        seen_chunk_ids: set[int] = set()
        search_hits = self.retriever.search(
            session_id=session_id,
            query=query,
            top_k=self.settings.memory_retrieval_top_k,
        )
        trace["search_hits_considered"] = len(search_hits)
        for chunk in search_hits:
            chunk_id = int(chunk["id"])
            if chunk_id in seen_chunk_ids:
                continue
            text = f"[memory:L{chunk['level']}:score={chunk['score']:.3f}] {chunk['content']}"
            text_tokens = self._estimate_tokens(text)
            if used_tokens + text_tokens > token_budget:
                continue
            segments.append(text)
            used_tokens += text_tokens
            seen_chunk_ids.add(chunk_id)
            trace["search_hits_included"].append(
                {
                    "id": chunk_id,
                    "level": int(chunk["level"]),
                    "score": round(float(chunk.get("score", 0.0)), 4),
                    "semantic_score": round(float(chunk.get("semantic_score", 0.0)), 4),
                    "keyword_score": round(float(chunk.get("keyword_score", 0.0)), 4),
                    "backend": str(chunk.get("retrieval_backend", "")),
                }
            )

        # Ensure higher-level summaries are included when there is budget left.
        for level in [3, 2]:
            if used_tokens >= token_budget:
                break
            level_chunks = self.store.get_compressed_chunks(
                session_id=session_id,
                level=level,
                only_unrolled=False,
            )
            for chunk in reversed(level_chunks[-2:]):
                chunk_id = int(chunk["id"])
                if chunk_id in seen_chunk_ids:
                    continue
                text = f"[memory:L{level}] {chunk['content']}"
                text_tokens = self._estimate_tokens(text)
                if used_tokens + text_tokens > token_budget:
                    continue
                segments.append(text)
                used_tokens += text_tokens
                seen_chunk_ids.add(chunk_id)
                trace["high_level_included"].append(
                    {
                        "id": chunk_id,
                        "level": level,
                    }
                )

        trace["used_tokens"] = used_tokens
        trace["segments_returned"] = len(segments)
        return RetrievedContext(segments=segments, total_tokens=used_tokens, metadata=trace)

    def get_store(self) -> MemoryStore:
        return self.store
