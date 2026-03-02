from __future__ import annotations

from pathlib import Path

from myopenclaw.core.types import SkillRunResult
from myopenclaw.llm.router import LLMRouter
from myopenclaw.skills.registry import SkillRegistry, _parse_frontmatter
from myopenclaw.skills.sandbox import SkillSandbox


class SkillExecutor:
    def __init__(
        self,
        registry: SkillRegistry,
        sandbox: SkillSandbox,
        router: LLMRouter | None = None,
    ) -> None:
        self.registry = registry
        self.sandbox = sandbox
        self.router = router

    def _read_frontmatter(self, skill_file: Path) -> dict:
        raw = skill_file.read_text(encoding="utf-8")
        if not raw.startswith("---\n"):
            return {}
        parts = raw.split("\n---\n", 1)
        if len(parts) != 2:
            return {}
        return _parse_frontmatter(parts[0].removeprefix("---\n"))

    def execute(
        self,
        skill_name: str,
        task_context: str,
        memory_context: list[str],
    ) -> SkillRunResult:
        skill = self.registry.get_skill(skill_name)
        if not skill:
            raise KeyError(f"Unknown skill: {skill_name}")

        metadata = self._read_frontmatter(skill.body_md_path)
        skill_dir = skill.body_md_path.parent

        entry_script = metadata.get("entry_script")
        if isinstance(entry_script, str):
            script = (skill_dir / "scripts" / entry_script).resolve()
            result = self.sandbox.run_script(
                skill_name=skill_name,
                script_path=script,
                payload={
                    "task_context": task_context,
                    "memory_context": memory_context,
                    "skill": skill_name,
                },
            )
            output = result["stdout"] if result["returncode"] == 0 else result["stderr"]
            return SkillRunResult(skill_name=skill_name, output=output, metadata=result)

        body = self.registry.read_skill_body(skill_name)
        composed_memory = "\n".join(memory_context[-8:])

        if self.router:
            try:
                response = self.router.generate(
                    messages=[
                        {"role": "system", "content": body},
                        {
                            "role": "user",
                            "content": f"Task:\n{task_context}\n\nMemory:\n{composed_memory}",
                        },
                    ],
                    temperature=0.2,
                )
                return SkillRunResult(
                    skill_name=skill_name,
                    output=response.content,
                    metadata={"provider": response.provider, "model": response.model},
                )
            except Exception as exc:
                fallback = (
                    f"[offline:{skill_name}] {task_context}\n"
                    f"Context used: {len(memory_context)} memory segments.\n"
                    "Skill guidance was loaded but provider call is unavailable."
                )
                return SkillRunResult(
                    skill_name=skill_name,
                    output=fallback,
                    metadata={"fallback_reason": str(exc)},
                )

        return SkillRunResult(
            skill_name=skill_name,
            output=f"[{skill_name}] {task_context}",
            metadata={"mode": "no-router"},
        )
