from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class MemoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cursor = self._conn.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tokens INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS compressed_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                level INTEGER NOT NULL,
                content TEXT NOT NULL,
                source_ids TEXT NOT NULL,
                parent_chunk_ids TEXT,
                rolled_to_next INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS task_runs (
                task_run_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                task_input TEXT NOT NULL,
                response TEXT NOT NULL,
                used_skill TEXT NOT NULL,
                quality_score REAL NOT NULL,
                trace_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS chunk_embeddings (
                chunk_id INTEGER NOT NULL,
                namespace TEXT NOT NULL,
                embedding TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chunk_id, namespace)
            );
            """
        )
        self._ensure_column("task_runs", "trace_json", "TEXT")
        self._conn.commit()

    def _ensure_column(self, table: str, column: str, ddl_type: str) -> None:
        rows = self._conn.cursor().execute(f"PRAGMA table_info({table})").fetchall()
        names = {str(row["name"]) for row in rows}
        if column in names:
            return
        self._conn.cursor().execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"
        )

    def close(self) -> None:
        self._conn.close()

    def add_message(self, session_id: str, role: str, content: str, tokens: int) -> int:
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT INTO messages (session_id, role, content, tokens) VALUES (?, ?, ?, ?)",
            (session_id, role, content, tokens),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        rows = cursor.execute(
            "SELECT id, role, content, tokens FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_recent_messages(self, session_id: str, limit: int) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        rows = cursor.execute(
            "SELECT id, role, content, tokens FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        ordered = [dict(row) for row in rows]
        ordered.reverse()
        return ordered

    def count_messages(self, session_id: str) -> int:
        cursor = self._conn.cursor()
        row = cursor.execute(
            "SELECT COUNT(*) as n FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["n"]) if row else 0

    def delete_messages(self, message_ids: list[int]) -> None:
        if not message_ids:
            return
        placeholders = ",".join(["?"] * len(message_ids))
        cursor = self._conn.cursor()
        cursor.execute(f"DELETE FROM messages WHERE id IN ({placeholders})", message_ids)
        self._conn.commit()

    def add_compressed_chunk(
        self,
        session_id: str,
        level: int,
        content: str,
        source_ids: list[int],
        parent_chunk_ids: list[int] | None = None,
    ) -> int:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO compressed_chunks (session_id, level, content, source_ids, parent_chunk_ids)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                level,
                content,
                json.dumps(source_ids),
                json.dumps(parent_chunk_ids or []),
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def get_compressed_chunks(
        self,
        session_id: str,
        level: int | None = None,
        only_unrolled: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT id, level, content, source_ids, parent_chunk_ids, rolled_to_next "
            "FROM compressed_chunks WHERE session_id = ?"
        )
        params: list[Any] = [session_id]

        if level is not None:
            query += " AND level = ?"
            params.append(level)
        if only_unrolled:
            query += " AND rolled_to_next = 0"

        query += " ORDER BY id ASC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        rows = self._conn.cursor().execute(query, params).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "id": row["id"],
                    "level": row["level"],
                    "content": row["content"],
                    "source_ids": json.loads(row["source_ids"]),
                    "parent_chunk_ids": json.loads(row["parent_chunk_ids"] or "[]"),
                    "rolled_to_next": bool(row["rolled_to_next"]),
                }
            )
        return result

    def mark_chunks_rolled(self, chunk_ids: list[int]) -> None:
        if not chunk_ids:
            return
        placeholders = ",".join(["?"] * len(chunk_ids))
        cursor = self._conn.cursor()
        cursor.execute(
            f"UPDATE compressed_chunks SET rolled_to_next = 1 WHERE id IN ({placeholders})",
            chunk_ids,
        )
        self._conn.commit()

    def add_task_run(
        self,
        task_run_id: str,
        session_id: str,
        task_input: str,
        response: str,
        used_skill: str,
        quality_score: float,
        trace: dict[str, Any] | None = None,
    ) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO task_runs
            (task_run_id, session_id, task_input, response, used_skill, quality_score, trace_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_run_id,
                session_id,
                task_input,
                response,
                used_skill,
                quality_score,
                json.dumps(trace or {}, ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def update_task_run_trace(self, task_run_id: str, trace: dict[str, Any]) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            "UPDATE task_runs SET trace_json = ? WHERE task_run_id = ?",
            (json.dumps(trace or {}, ensure_ascii=False), task_run_id),
        )
        self._conn.commit()

    def _decode_task_run(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if not row:
            return None
        payload = dict(row)
        raw_trace = payload.get("trace_json")
        trace: dict[str, Any] = {}
        if isinstance(raw_trace, str) and raw_trace.strip():
            try:
                parsed = json.loads(raw_trace)
                if isinstance(parsed, dict):
                    trace = parsed
            except Exception:
                trace = {}
        payload["trace"] = trace
        return payload

    def get_task_run(self, task_run_id: str) -> dict[str, Any] | None:
        row = self._conn.cursor().execute(
            "SELECT * FROM task_runs WHERE task_run_id = ?",
            (task_run_id,),
        ).fetchone()
        return self._decode_task_run(row)

    def get_recent_task_runs(self, limit: int = 5, session_id: str | None = None) -> list[dict[str, Any]]:
        if session_id:
            rows = self._conn.cursor().execute(
                "SELECT * FROM task_runs WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = self._conn.cursor().execute(
                "SELECT * FROM task_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [decoded for decoded in (self._decode_task_run(row) for row in rows) if decoded]

    def get_chunk_embedding(self, chunk_id: int, namespace: str) -> list[float] | None:
        row = self._conn.cursor().execute(
            "SELECT embedding FROM chunk_embeddings WHERE chunk_id = ? AND namespace = ?",
            (chunk_id, namespace),
        ).fetchone()
        if not row:
            return None
        try:
            raw = json.loads(row["embedding"])
            if isinstance(raw, list):
                return [float(value) for value in raw]
        except Exception:
            return None
        return None

    def upsert_chunk_embedding(self, chunk_id: int, namespace: str, embedding: list[float]) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO chunk_embeddings (chunk_id, namespace, embedding)
            VALUES (?, ?, ?)
            """,
            (chunk_id, namespace, json.dumps(embedding)),
        )
        self._conn.commit()
