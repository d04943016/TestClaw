from __future__ import annotations

from myopenclaw.config import Settings
from myopenclaw.llm.router import LLMRouter


def test_single_provider_detected(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "x-openai")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    settings = Settings(project_root=tmp_path)
    router = LLMRouter(settings)

    assert router.list_available_providers() == ["openai"]


def test_multiple_provider_detected(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "x-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x-anthropic")
    monkeypatch.setenv("GEMINI_API_KEY", "x-gemini")

    settings = Settings(project_root=tmp_path)
    router = LLMRouter(settings)

    assert router.list_available_providers() == ["openai", "anthropic", "gemini"]
    assert router.default_provider() == "openai"
