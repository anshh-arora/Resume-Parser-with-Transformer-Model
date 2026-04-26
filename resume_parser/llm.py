"""Thin wrapper around the Ollama Python SDK that targets either cloud or local."""
from __future__ import annotations

import json
import time
from functools import lru_cache
from typing import Any

from ollama import Client

from . import config
from .logging_setup import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=1)
def get_client() -> Client:
    headers: dict[str, str] = {}
    if config.OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {config.OLLAMA_API_KEY}"
        log.info("Ollama client → cloud %s (key set)", config.OLLAMA_HOST)
    else:
        log.info("Ollama client → local %s", config.OLLAMA_HOST)
    return Client(host=config.OLLAMA_HOST, headers=headers or None)


def health_check() -> tuple[bool, str]:
    """Catch the two common pre-flight failures: cloud + missing key, or unreachable host."""
    is_cloud = "ollama.com" in config.OLLAMA_HOST
    if is_cloud and not config.OLLAMA_API_KEY:
        return False, (
            f"OLLAMA_HOST is {config.OLLAMA_HOST} but OLLAMA_API_KEY is not set. "
            "Add your key to .env or switch OLLAMA_HOST to a local daemon."
        )
    try:
        get_client().list()
        target = "Ollama Cloud" if is_cloud else "local Ollama"
        return True, f"{target} reachable at {config.OLLAMA_HOST}"
    except Exception as exc:
        return False, f"Ollama unreachable at {config.OLLAMA_HOST}: {exc}"


def chat_json(
    system: str,
    user: str,
    *,
    schema: dict[str, Any] | None = None,
    model: str | None = None,
) -> dict:
    """Chat completion that constrains output to JSON.

    Pass `schema` (a JSON Schema dict, e.g. ParsedResume.model_json_schema()) to
    enable grammar-constrained generation — the strongest anti-hallucination
    lever available short of fine-tuning. Falls back to free-form JSON mode
    when no schema is given.
    """
    target_model = model or config.OLLAMA_MODEL
    fmt: Any = schema if schema is not None else "json"
    log.info(
        "LLM call → model=%s, prompt_chars=%d, schema=%s",
        target_model, len(user), "yes" if schema else "no",
    )
    started = time.perf_counter()

    try:
        response = get_client().chat(
            model=target_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            format=fmt,
            options={"temperature": 0.0},
        )
    except Exception as exc:
        log.error("LLM call failed after %.2fs: %s", time.perf_counter() - started, exc)
        raise

    elapsed = time.perf_counter() - started
    content = response["message"]["content"] if isinstance(response, dict) else response.message.content
    if not content:
        log.error("LLM returned empty content (%.2fs)", elapsed)
        raise RuntimeError("Model returned an empty response")

    log.info("LLM call ok in %.2fs (%d chars)", elapsed, len(content))
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        log.error("LLM returned non-JSON: %s\n--- payload ---\n%s\n---", exc, content[:500])
        raise
