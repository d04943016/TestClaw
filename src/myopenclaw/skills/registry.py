from __future__ import annotations

from pathlib import Path

from myopenclaw.core.types import SkillSpec


def _parse_list_value(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"\'') for item in inner.split(",") if item.strip()]
    return [raw.strip().strip('"\'')]


def _parse_frontmatter(text: str) -> dict:
    metadata: dict[str, object] = {}
    lines = text.splitlines()
    current_key: str | None = None

    for line in lines:
        if not line.strip() or line.strip().startswith("#"):
            continue

        if line.lstrip().startswith("-") and current_key:
            value = line.split("-", 1)[1].strip().strip('"\'')
            metadata.setdefault(current_key, [])
            assert isinstance(metadata[current_key], list)
            metadata[current_key].append(value)
            continue

        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key

        if not value:
            metadata[key] = []
            continue

        if value.startswith("["):
            metadata[key] = _parse_list_value(value)
        else:
            metadata[key] = value.strip().strip('"\'')

    return metadata


class SkillRegistry:
    def __init__(self, skills_root: Path) -> None:
        self.skills_root = skills_root
        self._skills: dict[str, SkillSpec] = {}

    def _parse_skill_file(self, skill_file: Path) -> tuple[dict, str]:
        raw = skill_file.read_text(encoding="utf-8")
        if raw.startswith("---\n"):
            parts = raw.split("\n---\n", 1)
            if len(parts) == 2:
                frontmatter_text = parts[0].removeprefix("---\n")
                body = parts[1]
                metadata = _parse_frontmatter(frontmatter_text)
                return metadata, body.strip()
        return {}, raw.strip()

    def _collect_paths(self, folder: Path, subdir: str) -> list[Path]:
        target = folder / subdir
        if not target.exists() or not target.is_dir():
            return []
        return sorted([path for path in target.rglob("*") if path.is_file()])

    def load_skills(self, path: Path | None = None) -> list[SkillSpec]:
        skills_path = path or self.skills_root
        self._skills.clear()

        if not skills_path.exists():
            return []

        for entry in sorted(skills_path.iterdir()):
            if not entry.is_dir():
                continue
            skill_file = entry / "SKILL.md"
            if not skill_file.exists():
                continue

            metadata, _ = self._parse_skill_file(skill_file)
            name = str(metadata.get("name") or entry.name)
            version = str(metadata.get("version") or "0.1.0")
            description = str(metadata.get("description") or "")
            inputs = [str(v) for v in (metadata.get("inputs") or [])]
            outputs = [str(v) for v in (metadata.get("outputs") or [])]
            constraints = [str(v) for v in (metadata.get("constraints") or [])]

            spec = SkillSpec(
                name=name,
                version=version,
                description=description,
                inputs=inputs,
                outputs=outputs,
                constraints=constraints,
                body_md_path=skill_file,
                assets_paths=self._collect_paths(entry, "assets"),
                scripts_paths=self._collect_paths(entry, "scripts"),
            )
            self._skills[name] = spec

        return list(self._skills.values())

    def get_skill(self, name: str) -> SkillSpec | None:
        if not self._skills:
            self.load_skills()
        return self._skills.get(name)

    def read_skill_body(self, name: str) -> str:
        skill = self.get_skill(name)
        if not skill:
            raise KeyError(f"Unknown skill: {name}")
        _, body = self._parse_skill_file(skill.body_md_path)
        return body

    def list_skill_names(self) -> list[str]:
        if not self._skills:
            self.load_skills()
        return sorted(self._skills.keys())
