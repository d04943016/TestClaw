from __future__ import annotations

from myopenclaw.config import Settings
from myopenclaw.memory.manager import MemoryManager


def test_memory_compression_and_retrieval(tmp_path):
    settings = Settings(project_root=tmp_path)
    settings.short_term_window = 10
    settings.chunk_target_tokens = 60

    manager = MemoryManager(settings=settings)
    session_id = "mem-test"

    for i in range(18):
        manager.append_message(
            session_id=session_id,
            role="user" if i % 2 == 0 else "assistant",
            content=(
                f"Message {i} about project context, constraints, and decisions "
                f"with enough words to trigger chunking in compression."
            ),
        )

    baseline_count = manager.get_store().count_messages(session_id)
    assert baseline_count == 18

    changed = manager.compress_if_needed(session_id)
    assert changed is True
    assert manager.get_store().count_messages(session_id) == settings.short_term_window

    compressed = manager.get_store().get_compressed_chunks(session_id=session_id, level=1)
    assert compressed

    retrieved = manager.retrieve(
        query="what were the main constraints and decisions",
        session_id=session_id,
        token_budget=600,
    )
    assert retrieved.total_tokens > 0
    assert len(retrieved.segments) >= 1
    assert any("recent:" in segment or "memory:" in segment for segment in retrieved.segments)

    # Compressed retrieval context should be substantially smaller than raw history.
    assert retrieved.total_tokens < 1200

    manager.get_store().close()
