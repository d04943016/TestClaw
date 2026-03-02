from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


class SandboxViolationError(RuntimeError):
    pass


class SkillSandbox:
    def __init__(self, skills_root: Path) -> None:
        self.skills_root = skills_root.resolve()

    def _skill_dir(self, skill_name: str) -> Path:
        return (self.skills_root / skill_name).resolve()

    def _assert_within(self, path: Path, root: Path) -> None:
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise SandboxViolationError(f"Path '{path}' is outside sandbox root '{root}'") from exc

    def is_path_allowed(self, skill_name: str, path: Path) -> bool:
        try:
            self._assert_within(path, self._skill_dir(skill_name))
            return True
        except SandboxViolationError:
            return False

    def safe_write_file(self, skill_name: str, relative_path: str, content: str) -> Path:
        skill_dir = self._skill_dir(skill_name)
        target = (skill_dir / relative_path).resolve()
        self._assert_within(target, skill_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def run_script(self, skill_name: str, script_path: Path, payload: dict) -> dict:
        skill_dir = self._skill_dir(skill_name)
        resolved_script = script_path.resolve()
        self._assert_within(resolved_script, skill_dir)

        process = subprocess.run(
            [sys.executable, str(resolved_script)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=str(skill_dir),
            timeout=30,
            check=False,
        )

        return {
            "returncode": process.returncode,
            "stdout": process.stdout.strip(),
            "stderr": process.stderr.strip(),
        }
