from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from myopenclaw.config import Settings
from myopenclaw.core.planner import TaskPlanner
from myopenclaw.evals.harness import EvalHarness
from myopenclaw.llm.router import LLMRouter
from myopenclaw.memory.compressor import MemoryCompressor
from myopenclaw.memory.manager import MemoryManager
from myopenclaw.memory.retriever import MemoryRetriever
from myopenclaw.memory.store import MemoryStore
from myopenclaw.skills.evolver import SkillEvolver
from myopenclaw.skills.executor import SkillExecutor
from myopenclaw.skills.registry import SkillRegistry
from myopenclaw.skills.sandbox import SkillSandbox


@dataclass(slots=True)
class TurnResult:
    response: str
    used_skill: str
    evolved: bool
    evolution_report: dict[str, Any] | None
    trace: dict[str, Any] | None = None


class OpenClawAgent:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.router = LLMRouter(self.settings)

        self.store = MemoryStore(self.settings.db_path)
        self.registry = SkillRegistry(self.settings.skills_dir)
        self.registry.load_skills()

        self.memory = MemoryManager(
            settings=self.settings,
            store=self.store,
            compressor=MemoryCompressor(router=self.router),
            retriever=MemoryRetriever(settings=self.settings, store=self.store),
        )

        self.sandbox = SkillSandbox(self.settings.skills_dir)
        self.executor = SkillExecutor(
            registry=self.registry,
            sandbox=self.sandbox,
            router=self.router,
        )
        self.planner = TaskPlanner(registry=self.registry)

        self.harness = EvalHarness(registry=self.registry, store=self.store)
        self.evolver = SkillEvolver(
            settings=self.settings,
            registry=self.registry,
            harness=self.harness,
            store=self.store,
            router=self.router,
            sandbox=self.sandbox,
        )

    def _estimate_quality(self, response: str) -> float:
        text = response.strip().lower()
        if not text:
            return 0.1

        score = 0.4
        if len(text) > 120:
            score += 0.2
        if "step" in text or "summary" in text:
            score += 0.15
        if "risk" in text or "constraint" in text:
            score += 0.15
        return min(1.0, score)

    def run_turn(self, session_id: str, user_input: str, token_budget: int = 1400) -> TurnResult:
        self.memory.append_message(session_id=session_id, role="user", content=user_input)

        retrieved = self.memory.retrieve(
            query=user_input,
            session_id=session_id,
            token_budget=token_budget,
        )

        planning = self.planner.choose_skill_with_trace(user_input)
        chosen_skill = str(planning["chosen_skill"])
        execution = self.executor.execute(
            skill_name=chosen_skill,
            task_context=user_input,
            memory_context=retrieved.segments,
        )

        self.memory.append_message(
            session_id=session_id,
            role="assistant",
            content=execution.output,
        )
        self.memory.compress_if_needed(session_id=session_id)

        task_run_id = f"task-{uuid.uuid4().hex[:12]}"
        trace_payload: dict[str, Any] = {
            "planner": planning,
            "memory": {
                **retrieved.metadata,
                "segment_count": len(retrieved.segments),
                "context_tokens": retrieved.total_tokens,
            },
            "executor": {
                "skill": chosen_skill,
                "metadata": execution.metadata,
            },
            "token_budget": token_budget,
        }

        self.store.add_task_run(
            task_run_id=task_run_id,
            session_id=session_id,
            task_input=user_input,
            response=execution.output,
            used_skill=chosen_skill,
            quality_score=self._estimate_quality(execution.output),
            trace=trace_payload,
        )

        evolution_report = None
        evolved = False
        try:
            report = self.evolver.post_task_evolve(task_run_id=task_run_id)
            if report is not None:
                evolved = bool(report.accepted)
                evolution_report = {
                    "accepted": report.accepted,
                    "avg_score": report.avg_score,
                    "details": report.details,
                    "regressions": report.regressions,
                }
                trace_payload["evolution"] = evolution_report
                self.store.update_task_run_trace(task_run_id=task_run_id, trace=trace_payload)
        except Exception as exc:
            evolution_report = {"error": str(exc)}
            trace_payload["evolution"] = evolution_report
            self.store.update_task_run_trace(task_run_id=task_run_id, trace=trace_payload)

        return TurnResult(
            response=execution.output,
            used_skill=chosen_skill,
            evolved=evolved,
            evolution_report=evolution_report,
            trace=trace_payload,
        )

    def list_providers(self) -> list[str]:
        return self.router.list_available_providers()

    def close(self) -> None:
        self.store.close()
