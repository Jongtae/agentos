"""
Model Adapter — builds a LangChain BaseChatModel from workspace spec.
API keys are read from environment variables only — never from spec.yaml.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


def build_llm(spec: dict):
    """
    Build a chat model from workspace spec.

    spec["ai_model"]["provider"] → "openai" | "anthropic"
    spec["ai_model"]["model"]    → model name string

    Raises:
        ValueError: if provider is unsupported or API key is missing.
    """
    ai_cfg  = spec.get("ai_model", {})
    provider = ai_cfg.get("provider", "openai").lower()
    model    = ai_cfg.get("model", "gpt-4o-mini")

    if provider == "anthropic":
        return _build_anthropic(model)
    elif provider == "openai":
        return _build_openai(model)
    else:
        raise ValueError(
            f"Unsupported provider: '{provider}'. "
            "Supported: anthropic, openai"
        )


def _build_anthropic(model: str):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to your .env file or environment."
        )
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        raise ImportError(
            "langchain-anthropic is not installed. "
            "Run: pip install langchain-anthropic"
        )

    return ChatAnthropic(
        model=model or "claude-sonnet-4-5-20250929",
        api_key=api_key,
        max_tokens=4096,
    )


def _build_openai(model: str):
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is not set. "
            "Add it to your .env file or environment."
        )
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        raise ImportError(
            "langchain-openai is not installed. "
            "Run: pip install langchain-openai"
        )

    return ChatOpenAI(
        model=model or "gpt-4o-mini",
        api_key=api_key,
    )
