from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv as _dotenv_load

    def load_env_file(path: Path, override: bool = False) -> None:
        _dotenv_load(path, override=override)
except Exception:
    def load_env_file(path: Path, override: bool = False) -> None:
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and (override or key not in os.environ):
                os.environ[key] = value


@dataclass(slots=True)
class Settings:
    project_root: Path = field(default_factory=lambda: Path.cwd())
    data_dir: Path = field(init=False)
    db_path: Path = field(init=False)
    faiss_index_path: Path = field(init=False)
    skills_dir: Path = field(init=False)
    state_dir: Path = field(init=False)
    active_profile_path: Path | None = field(init=False, default=None)
    short_term_window: int = 30
    chunk_target_tokens: int = 1000
    rollup_batch_size: int = 10
    embedding_dim: int = 256
    memory_retrieval_top_k: int = 6
    evolution_improvement_threshold: float = 0.15
    evolution_regression_floor: float = -0.20
    default_models: dict[str, str] = field(
        default_factory=lambda: {
            "openai": "openai/gpt-4.1-mini",
            "anthropic": "anthropic/claude-3-5-sonnet-latest",
            "gemini": "gemini/gemini-1.5-pro",
        }
    )

    def __post_init__(self) -> None:
        load_env_file(self.project_root / ".env")
        profile = self._resolve_profile()
        if profile:
            load_env_file(profile)
            self.active_profile_path = profile

        self.short_term_window = self._env_int(
            "MEMORY_SHORT_TERM_WINDOW",
            self.short_term_window,
            min_value=6,
            max_value=200,
        )
        self.chunk_target_tokens = self._env_int(
            "MEMORY_CHUNK_TARGET_TOKENS",
            self.chunk_target_tokens,
            min_value=250,
            max_value=8000,
        )
        self.rollup_batch_size = self._env_int(
            "MEMORY_ROLLUP_BATCH_SIZE",
            self.rollup_batch_size,
            min_value=2,
            max_value=30,
        )
        self.embedding_dim = self._env_int(
            "MEMORY_HASH_EMBEDDING_DIM",
            self.embedding_dim,
            min_value=64,
            max_value=2048,
        )
        self.memory_retrieval_top_k = self._env_int(
            "AGENT_MEMORY_TOP_K",
            self.memory_retrieval_top_k,
            min_value=1,
            max_value=20,
        )

        self.data_dir = self.project_root / "data"
        self.db_path = self.data_dir / "agent.db"
        self.faiss_index_path = self.data_dir / "faiss.index"
        self.skills_dir = self.project_root / "skills"
        self.state_dir = self.project_root / ".agent_state" / "skill_versions"
        self.ensure_dirs()

    def _resolve_profile(self) -> Path | None:
        raw = os.getenv("MYOPENCLAW_PROFILE", "").strip()
        if not raw:
            return None
        profile = Path(raw).expanduser()
        if not profile.is_absolute():
            profile = (self.project_root / profile).resolve()
        return profile if profile.exists() and profile.is_file() else None

    def _env_int(self, key: str, default: int, min_value: int, max_value: int) -> int:
        raw = os.getenv(key, "").strip()
        if not raw:
            return default
        try:
            parsed = int(raw)
        except Exception:
            return default
        return max(min_value, min(max_value, parsed))

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def provider_env_map(self) -> dict[str, list[str]]:
        return {
            "openai": ["OPENAI_API_KEY"],
            "anthropic": ["ANTHROPIC_API_KEY"],
            "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        }

    def available_provider_keys(self) -> dict[str, str]:
        providers: dict[str, str] = {}
        for provider, keys in self.provider_env_map().items():
            for key in keys:
                value = os.getenv(key)
                if value:
                    providers[provider] = key
                    break
        return providers
