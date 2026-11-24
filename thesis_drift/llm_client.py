"""Thin LLM adapter: Anthropic or OpenAI via environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODELS = {"anthropic": "claude-3-5-haiku-latest", "openai": "gpt-4o-mini"}


def configured_provider() -> str:
    return os.getenv("LLM_PROVIDER", "").strip().lower()


def is_configured() -> bool:
    """True only when a supported provider, key, and reachable SDK are configured."""
    return bool(
        os.getenv("LLM_API_KEY", "").strip()
        and configured_provider() in DEFAULT_MODELS
    )


def call_llm(system_prompt: str, user_prompt: str) -> str:
    """Call the configured LLM provider and return its text response."""
    provider = configured_provider()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL") or DEFAULT_MODELS.get(provider)
    if not api_key or provider not in DEFAULT_MODELS:
        raise RuntimeError(
            "LLM is not configured. Set LLM_PROVIDER (anthropic|openai), "
            "LLM_API_KEY, and optionally LLM_MODEL; or run with dry_run=True."
        )
    if provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=1500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")
    import openai

    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        max_tokens=1500,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content or ""
