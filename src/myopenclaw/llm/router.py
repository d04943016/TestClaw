from __future__ import annotations

import json
from typing import Any

from myopenclaw.config import Settings
from myopenclaw.core.types import LLMResponse


class LLMRouter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._providers = settings.available_provider_keys()

    def list_available_providers(self) -> list[str]:
        preferred = ["openai", "anthropic", "gemini"]
        return [p for p in preferred if p in self._providers]

    def default_provider(self) -> str:
        providers = self.list_available_providers()
        if not providers:
            raise RuntimeError(
                "No LLM provider configured. Put API key(s) in .env: "
                "OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY"
            )
        return providers[0]

    def _resolve_provider(self, provider: str | None) -> str:
        if provider:
            if provider not in self._providers:
                raise ValueError(f"Provider '{provider}' is unavailable in current .env")
            return provider
        return self.default_provider()

    def _resolve_model(self, provider: str, model: str | None) -> str:
        if model:
            if "/" in model:
                return model
            return f"{provider}/{model}"
        return self.settings.default_models[provider]

    def generate(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        provider: str | None = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        resolved_provider = self._resolve_provider(provider)
        resolved_model = self._resolve_model(resolved_provider, model)

        try:
            from litellm import completion
        except ImportError as exc:
            raise RuntimeError(
                "litellm is required for provider calls. Install requirements.txt first."
            ) from exc

        response = completion(
            model=resolved_model,
            messages=messages,
            temperature=temperature,
        )

        try:
            content = response.choices[0].message.content or ""
        except Exception as exc:
            raw = json.loads(response.model_dump_json()) if hasattr(response, "model_dump_json") else {}
            raise RuntimeError(f"Unexpected provider response shape: {raw}") from exc

        raw_payload: dict[str, Any]
        if hasattr(response, "model_dump"):
            raw_payload = response.model_dump()
        elif hasattr(response, "json"):
            raw_payload = response.json()  # type: ignore[assignment]
        else:
            raw_payload = {"raw": str(response)}

        return LLMResponse(
            content=content,
            model=resolved_model,
            provider=resolved_provider,
            raw=raw_payload,
        )
