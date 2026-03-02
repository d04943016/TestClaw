from __future__ import annotations

import argparse
import json
from pathlib import Path

from myopenclaw.config import Settings
from myopenclaw.core.agent import OpenClawAgent
from myopenclaw.evals.harness import EvalHarness
from myopenclaw.llm.router import LLMRouter
from myopenclaw.memory.manager import MemoryManager
from myopenclaw.memory.store import MemoryStore
from myopenclaw.skills.evolver import SkillEvolver
from myopenclaw.skills.registry import SkillRegistry
from myopenclaw.skills.sandbox import SkillSandbox


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cmd_chat(args: argparse.Namespace) -> int:
    settings = Settings()
    agent = OpenClawAgent(settings=settings)
    providers = agent.list_providers()
    default_provider = providers[0] if providers else "(none)"
    print(f"Available providers: {providers}")
    print(f"Default provider: {default_provider}")
    print("Enter /exit to stop.")

    try:
        while True:
            user_input = input("you> ").strip()
            if not user_input:
                continue
            if user_input in {"/exit", "/quit"}:
                break

            result = agent.run_turn(
                session_id=args.session,
                user_input=user_input,
                token_budget=args.token_budget,
            )
            print(f"agent[{result.used_skill}]> {result.response}")
            if result.evolution_report:
                status = "accepted" if result.evolution_report.get("accepted") else "not accepted"
                print(f"evolution> {status}")
    finally:
        agent.close()
    return 0


def _cmd_providers_list(_: argparse.Namespace) -> int:
    settings = Settings()
    router = LLMRouter(settings=settings)
    providers = router.list_available_providers()
    payload = {
        "available_providers": providers,
        "default_provider": providers[0] if providers else None,
    }
    _print_json(payload)
    return 0


def _cmd_skills_list(_: argparse.Namespace) -> int:
    settings = Settings()
    registry = SkillRegistry(settings.skills_dir)
    skills = registry.load_skills()
    for skill in skills:
        print(f"- {skill.name} (v{skill.version}): {skill.description}")
    return 0


def _cmd_skills_show(args: argparse.Namespace) -> int:
    settings = Settings()
    registry = SkillRegistry(settings.skills_dir)
    registry.load_skills()
    skill = registry.get_skill(args.name)
    if not skill:
        print(f"Skill not found: {args.name}")
        return 1

    print(f"name: {skill.name}")
    print(f"version: {skill.version}")
    print(f"description: {skill.description}")
    print(f"inputs: {skill.inputs}")
    print(f"outputs: {skill.outputs}")
    print(f"constraints: {skill.constraints}")
    print(f"file: {skill.body_md_path}")
    return 0


def _cmd_memory_compress(args: argparse.Namespace) -> int:
    settings = Settings()
    manager = MemoryManager(settings=settings)
    compressed = manager.compress_if_needed(session_id=args.session)
    print("compressed" if compressed else "no-op")
    manager.get_store().close()
    return 0


def _cmd_eval_run(_: argparse.Namespace) -> int:
    settings = Settings()
    store = MemoryStore(settings.db_path)
    registry = SkillRegistry(settings.skills_dir)
    registry.load_skills()
    harness = EvalHarness(registry=registry, store=store)
    report = harness.run_regression()
    _print_json(
        {
            "avg_score": report.avg_score,
            "per_case_scores": report.per_case_scores,
            "regressions": report.regressions,
            "safety_checks": report.safety_checks,
            "accepted": report.accepted,
        }
    )
    store.close()
    return 0


def _cmd_trace_tail(args: argparse.Namespace) -> int:
    settings = Settings()
    store = MemoryStore(settings.db_path)
    runs = store.get_recent_task_runs(limit=args.limit, session_id=args.session)
    payload = []
    for run in runs:
        payload.append(
            {
                "task_run_id": run.get("task_run_id"),
                "session_id": run.get("session_id"),
                "created_at": run.get("created_at"),
                "used_skill": run.get("used_skill"),
                "quality_score": run.get("quality_score"),
                "trace": run.get("trace", {}),
            }
        )
    _print_json({"runs": payload})
    store.close()
    return 0


def _cmd_evolve_run(args: argparse.Namespace) -> int:
    settings = Settings()
    store = MemoryStore(settings.db_path)
    registry = SkillRegistry(settings.skills_dir)
    registry.load_skills()
    harness = EvalHarness(registry=registry, store=store)
    router = LLMRouter(settings)
    evolver = SkillEvolver(
        settings=settings,
        registry=registry,
        harness=harness,
        store=store,
        router=router,
        sandbox=SkillSandbox(settings.skills_dir),
    )

    try:
        patch = evolver.propose_mutation(skill_name=args.skill)
    except KeyError as exc:
        print(str(exc))
        store.close()
        return 1
    report = evolver.evaluate_candidate(skill_patch=patch)
    outcome = evolver.apply_or_rollback(skill_patch=patch, eval_report=report)
    _print_json(
        {
            "patch": str(patch.diff_path),
            "accepted": report.accepted,
            "avg_score": report.avg_score,
            "details": report.details,
            "outcome": outcome,
        }
    )
    store.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="myopenclaw")
    sub = parser.add_subparsers(dest="command", required=True)

    chat = sub.add_parser("chat", help="Interactive chat loop")
    chat.add_argument("--session", default="default")
    chat.add_argument("--token-budget", type=int, default=1400)
    chat.set_defaults(func=_cmd_chat)

    providers = sub.add_parser("providers", help="Provider commands")
    providers_sub = providers.add_subparsers(dest="providers_command", required=True)
    providers_list = providers_sub.add_parser("list")
    providers_list.set_defaults(func=_cmd_providers_list)

    skills = sub.add_parser("skills", help="Skills commands")
    skills_sub = skills.add_subparsers(dest="skills_command", required=True)
    skills_list = skills_sub.add_parser("list")
    skills_list.set_defaults(func=_cmd_skills_list)
    skills_show = skills_sub.add_parser("show")
    skills_show.add_argument("name")
    skills_show.set_defaults(func=_cmd_skills_show)

    evolve = sub.add_parser("evolve", help="Skill evolution commands")
    evolve_sub = evolve.add_subparsers(dest="evolve_command", required=True)
    evolve_run = evolve_sub.add_parser("run")
    evolve_run.add_argument("--skill", required=True)
    evolve_run.set_defaults(func=_cmd_evolve_run)

    memory = sub.add_parser("memory", help="Memory commands")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    memory_compress = memory_sub.add_parser("compress")
    memory_compress.add_argument("--session", required=True)
    memory_compress.set_defaults(func=_cmd_memory_compress)

    eval_parser = sub.add_parser("eval", help="Evaluation commands")
    eval_sub = eval_parser.add_subparsers(dest="eval_command", required=True)
    eval_run = eval_sub.add_parser("run")
    eval_run.set_defaults(func=_cmd_eval_run)

    trace = sub.add_parser("trace", help="Tracing/observability commands")
    trace_sub = trace.add_subparsers(dest="trace_command", required=True)
    trace_tail = trace_sub.add_parser("tail")
    trace_tail.add_argument("--session", default=None)
    trace_tail.add_argument("--limit", type=int, default=5)
    trace_tail.set_defaults(func=_cmd_trace_tail)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    code = args.func(args)
    raise SystemExit(code)
