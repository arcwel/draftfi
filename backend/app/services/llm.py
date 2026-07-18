"""BYO-LLM provider abstraction (multi-provider).

Cleans + categorizes raw bank descriptors via one of four backends — Ollama
(local), OpenAI/ChatGPT, Anthropic/Claude, or Google Gemini — selected from the
active :class:`~app.services.llm_config.LLMConfig`. Ollama keeps data fully on
the machine; the cloud providers send the descriptor string to their APIs.

Public surface:

* ``health(config)``         — availability + latency for the status pill.
* ``clean_merchant(config, raw, categories)`` — strict-JSON clean + categorize.

Parsing is defensive: models often wrap JSON in prose or code fences, so we
repair/extract before giving up.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

import httpx

from app.services.llm_config import LLMConfig

SYSTEM_PROMPT = (
    "You are a financial transaction normalizer. Given a raw bank statement "
    "descriptor, identify the real-world merchant and the best-fit spending "
    "category. Respond with ONLY a single minified JSON object and nothing "
    'else, in the exact form: {"clean_merchant": "...", "category": "..."}. '
    "Choose the category from this list when possible: __CATEGORIES__. "
    "Do not include markdown, code fences, or explanation."
)

# Matches the first {...} block, tolerating surrounding prose / code fences.
_JSON_RE = re.compile(r"\{.*?\}", re.DOTALL)


@dataclass
class CleanResult:
    clean_merchant: str
    category: str


class LLMError(Exception):
    """Raised when the model is unreachable or returns unusable output."""


def parse_model_json(text: str) -> CleanResult:
    """Extract ``{clean_merchant, category}`` from possibly-noisy model output."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        candidate = re.sub(r"^json\s*", "", candidate, flags=re.IGNORECASE).strip()

    for blob in (candidate, *(_JSON_RE.findall(text))):
        try:
            data = json.loads(blob)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and "clean_merchant" in data:
            return CleanResult(
                clean_merchant=str(data.get("clean_merchant", "")).strip() or "Unknown",
                category=str(data.get("category", "Uncategorized")).strip()
                or "Uncategorized",
            )
    raise LLMError(f"Could not parse JSON from model output: {text[:200]!r}")


# --------------------------------------------------------------------------- #
# Health checks (per provider)
# --------------------------------------------------------------------------- #
async def health(config: LLMConfig) -> tuple[bool, float | None, str | None]:
    """Return (available, latency_ms, detail) for the active provider."""
    if config.spec.requires_key and not config.api_key:
        return False, None, "no API key configured"

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            if config.provider == "ollama":
                resp = await client.get(f"{config.base_url.rstrip('/')}/api/tags")
            elif config.provider == "openai":
                resp = await client.get(
                    f"{config.base_url.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {config.api_key}"},
                )
            elif config.provider == "gemini":
                resp = await client.get(
                    f"{config.base_url.rstrip('/')}/models",
                    params={"key": config.api_key},
                )
            elif config.provider == "anthropic":
                # No unauthenticated list endpoint; a 1-token message validates
                # both reachability and the key.
                resp = await client.post(
                    f"{config.base_url.rstrip('/')}/v1/messages",
                    headers=_anthropic_headers(config),
                    json={
                        "model": config.model,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
            else:  # pragma: no cover - guarded by config resolution
                return False, None, f"unknown provider {config.provider}"
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        detail = "invalid API key" if code in (401, 403) else f"HTTP {code}"
        return False, None, detail
    except httpx.HTTPError as exc:
        return False, None, str(exc)
    latency_ms = (time.perf_counter() - start) * 1000.0
    return True, round(latency_ms, 1), None


# --------------------------------------------------------------------------- #
# Generation (per provider) — each returns raw model text
# --------------------------------------------------------------------------- #
def _anthropic_headers(config: LLMConfig) -> dict[str, str]:
    return {
        "x-api-key": config.api_key or "",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }


async def _generate(config: LLMConfig, prompt: str, system: str) -> str:
    base = config.base_url.rstrip("/")
    timeout = 30.0
    async with httpx.AsyncClient(timeout=timeout) as client:
        if config.provider == "ollama":
            resp = await client.post(
                f"{base}/api/generate",
                json={
                    "model": config.model,
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.0},
                },
            )
            resp.raise_for_status()
            return resp.json().get("response", "")

        if config.provider == "openai":
            resp = await client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {config.api_key}"},
                json={
                    "model": config.model,
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        if config.provider == "anthropic":
            resp = await client.post(
                f"{base}/v1/messages",
                headers=_anthropic_headers(config),
                json={
                    "model": config.model,
                    "max_tokens": 256,
                    "system": system,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            parts = resp.json().get("content", [])
            return parts[0]["text"] if parts else ""

        if config.provider == "gemini":
            resp = await client.post(
                f"{base}/models/{config.model}:generateContent",
                params={"key": config.api_key},
                json={
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.0,
                        "responseMimeType": "application/json",
                    },
                },
            )
            resp.raise_for_status()
            cands = resp.json().get("candidates", [])
            if not cands:
                return ""
            return cands[0]["content"]["parts"][0]["text"]

    raise LLMError(f"Unknown provider: {config.provider}")  # pragma: no cover


async def clean_merchant(
    config: LLMConfig,
    raw_description: str,
    categories: list[str],
    *,
    retries: int = 1,
) -> CleanResult:
    """Clean + categorize a raw descriptor via the active provider.

    Retries once on parse failure. Raises ``LLMError`` if the model is
    unreachable or output stays unusable.
    """
    system = SYSTEM_PROMPT.replace("__CATEGORIES__", ", ".join(categories))
    prompt = f'Raw descriptor: "{raw_description}"'
    last_exc: Exception | None = None
    for _attempt in range(retries + 1):
        try:
            text = await _generate(config, prompt, system)
            return parse_model_json(text)
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM endpoint error: {exc}") from exc
        except LLMError as exc:
            last_exc = exc
            continue
    raise LLMError(str(last_exc) if last_exc else "LLM failed")
