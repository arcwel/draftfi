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

import asyncio
import json
import logging
import random
import re
import time
from dataclasses import dataclass

import httpx

from app.services.llm_config import LLMConfig

log = logging.getLogger("draftfi.llm")

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


# Distinguishes "no default given" from a default of None/""/[].
_UNSET = object()


class LLMError(Exception):
    """Raised when the model is unreachable or returns unusable output."""


class LLMUnavailable(LLMError):
    """The endpoint itself failed (rate limit, auth, 5xx, connection).

    Distinct from a parse failure: retrying individual rows against a provider
    that just refused the batch only multiplies the load, so callers should back
    off instead of falling back to per-row calls.
    """


class ModelUnavailable(LLMUnavailable):
    """The provider is reachable but the configured model no longer exists.

    This is the single most common way a working setup breaks weeks later: the
    provider keeps answering, the key stays valid, the model still appears in
    the catalogue — and every generation call 404s. Kept as a subclass so
    existing ``except LLMUnavailable`` handlers still degrade gracefully, while
    callers that can *repair* the config (see ``services.model_guard``) can
    catch it specifically and switch to a live model instead of giving up.
    """


# Phrasings that unambiguously mean "this model id is dead". Providers word it
# differently: Gemini says "is no longer available", OpenAI returns a
# ``model_not_found`` code, Ollama says the model was never pulled.
_STRONG_MODEL_GONE_HINTS = (
    "no longer available",
    "not available to new users",
    "model_not_found",
    "has been retired",
    "is deprecated",
    "was deprecated",
)
# Weaker phrasings only count when the provider actually names a model — a 404
# from a mistyped base URL also says "not found", and swapping the model in
# response to that would be a confusing non-fix.
_WEAK_MODEL_GONE_HINTS = (
    "not found",
    "does not exist",
    "unknown model",
    "is not supported",
    "try pulling it first",
)


def _response_text(resp) -> str:
    try:
        return resp.text or ""
    except Exception:  # pragma: no cover - streamed or already-closed response
        return ""


def _is_model_gone(status: int | None, body: str) -> bool:
    """True when this looks like a retired/renamed/missing model id."""
    if status not in (400, 404):
        return False
    low = body.lower()
    if any(hint in low for hint in _STRONG_MODEL_GONE_HINTS):
        return True
    return "model" in low and any(hint in low for hint in _WEAK_MODEL_GONE_HINTS)


# Providers such as Gemini carry the API key in the URL query string, which
# httpx echoes verbatim in its error messages. Redact it before any detail can
# reach the frontend or logs.
_KEY_IN_URL_RE = re.compile(r"([?&]key=)[^&\s'\"]+")


def _redact(text: str) -> str:
    return _KEY_IN_URL_RE.sub(r"\1REDACTED", text)


def _endpoint_error(exc: Exception) -> LLMUnavailable:
    """Turn a transport/HTTP failure into a message a user can act on."""
    resp = getattr(exc, "response", None)
    status = getattr(resp, "status_code", None)
    if resp is not None and _is_model_gone(status, _response_text(resp)):
        return ModelUnavailable(
            "The selected model is no longer available from this provider. "
            "DraftFi will switch to a supported model automatically."
        )
    if status == 429:
        return LLMUnavailable(
            "Provider rate limit reached (HTTP 429). Wait for your quota to "
            "reset, or switch to a local Ollama model for bulk categorization."
        )
    if status in (401, 403):
        return LLMUnavailable(
            f"Provider rejected the API key (HTTP {status}). Check the key in "
            "the LLM Provider panel."
        )
    if status is not None and status >= 500:
        return LLMUnavailable(f"Provider is having trouble (HTTP {status}).")
    return LLMUnavailable(_redact(f"Could not reach the provider: {exc}"))


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
@dataclass
class HealthResult:
    available: bool
    latency_ms: float | None = None
    detail: str | None = None
    # The endpoint answered, but the configured model is gone. Callers repair
    # the config rather than reporting a dead provider to the user.
    model_gone: bool = False


async def check(config: LLMConfig) -> HealthResult:
    """Verify the provider *and* the configured model with one real call.

    Listing models is not enough, and that gap is exactly what let a broken
    setup look healthy: providers keep advertising retired ids in their
    catalogue long after generation stops working. Gemini will happily return a
    retired model from ListModels with ``generateContent`` among its supported
    methods while the generation call itself 404s — so a catalogue lookup
    reports a green status pill for a config that cannot categorize a single
    row. Only a real generation proves the provider/model/key triple works,
    so that is what this does, using the smallest request each API accepts.
    """
    if config.spec.requires_key and not config.api_key:
        return HealthResult(False, None, "no API key configured")

    base = config.base_url.rstrip("/")
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            if config.provider == "ollama":
                resp = await client.post(
                    f"{base}/api/generate",
                    json={
                        "model": config.model,
                        "prompt": "ping",
                        "stream": False,
                        "options": {"num_predict": 1},
                    },
                )
            elif config.provider == "openai":
                resp = await client.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {config.api_key}"},
                    json={
                        "model": config.model,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
            elif config.provider == "anthropic":
                resp = await client.post(
                    f"{base}/v1/messages",
                    headers=_anthropic_headers(config),
                    json={
                        "model": config.model,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
            elif config.provider == "gemini":
                resp = await client.post(
                    f"{base}/models/{config.model}:generateContent",
                    params={"key": config.api_key},
                    json={
                        "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
                        "generationConfig": {"maxOutputTokens": 1},
                    },
                )
            else:  # pragma: no cover - guarded by config resolution
                return HealthResult(
                    False, None, f"unknown provider {config.provider}"
                )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if _is_model_gone(code, _response_text(exc.response)):
            return HealthResult(
                False,
                None,
                f"Model '{config.model}' is no longer available from this provider.",
                model_gone=True,
            )
        detail = "invalid API key" if code in (401, 403) else f"HTTP {code}"
        return HealthResult(False, None, detail)
    except httpx.HTTPError as exc:
        return HealthResult(False, None, _redact(str(exc)))
    latency_ms = (time.perf_counter() - start) * 1000.0
    return HealthResult(True, round(latency_ms, 1), None)


async def health(config: LLMConfig) -> tuple[bool, float | None, str | None]:
    """Tuple view of :func:`check`, kept for existing callers."""
    result = await check(config)
    return result.available, result.latency_ms, result.detail


# --------------------------------------------------------------------------- #
# Model discovery (per provider) — A2
# --------------------------------------------------------------------------- #
async def list_models(config: LLMConfig) -> list[str]:
    """Return the provider's available model ids, sorted.

    Raises :class:`LLMError` when the endpoint is unreachable or the key is
    rejected, so the caller can fall back to free-text entry.
    """
    if config.spec.requires_key and not config.api_key:
        raise LLMError("no API key configured")
    base = config.base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            if config.provider == "ollama":
                resp = await client.get(f"{base}/api/tags")
                resp.raise_for_status()
                names = [m["name"] for m in resp.json().get("models", [])]
            elif config.provider == "openai":
                resp = await client.get(
                    f"{base}/models",
                    headers={"Authorization": f"Bearer {config.api_key}"},
                )
                resp.raise_for_status()
                names = [m["id"] for m in resp.json().get("data", [])]
            elif config.provider == "gemini":
                resp = await client.get(
                    f"{base}/models", params={"key": config.api_key}
                )
                resp.raise_for_status()
                # Gemini ids look like "models/gemini-2.0-flash"; strip the prefix.
                names = [
                    m["name"].split("/", 1)[-1]
                    for m in resp.json().get("models", [])
                    if "generateContent" in m.get("supportedGenerationMethods", [])
                ]
            elif config.provider == "anthropic":
                resp = await client.get(
                    f"{base}/v1/models", headers=_anthropic_headers(config)
                )
                resp.raise_for_status()
                names = [m["id"] for m in resp.json().get("data", [])]
            else:  # pragma: no cover - guarded by config resolution
                raise LLMError(f"unknown provider {config.provider}")
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        detail = "invalid API key" if code in (401, 403) else f"HTTP {code}"
        raise LLMError(detail) from exc
    except httpx.HTTPError as exc:
        raise LLMError(_redact(str(exc))) from exc
    return sorted(set(names))


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
            return _extract(config, resp, ("choices", 0, "message", "content"))

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
            parts = _extract(config, resp, ("content",), default=[])
            if not parts:
                return ""
            return _extract(config, resp, ("content", 0, "text"), default="")

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
            cands = _extract(config, resp, ("candidates",), default=[])
            if not cands:
                return ""
            # A candidate blocked by a safety filter, or truncated by
            # MAX_TOKENS, arrives with no content.parts at all. Reading
            # ["content"]["parts"][0]["text"] raised a bare KeyError that no
            # caller caught, so one filtered chunk ended an entire sync.
            return _extract(
                config, resp, ("candidates", 0, "content", "parts", 0, "text"),
                default="",
            )

    raise LLMError(f"Unknown provider: {config.provider}")  # pragma: no cover


def _extract(config: LLMConfig, resp, path: tuple, default=_UNSET):
    """Walk a response body defensively.

    Providers do not always return the shape their docs describe. A Gemini
    candidate blocked by a safety filter has no ``parts``; an OpenAI-compatible
    proxy (LiteLLM, OpenRouter, LM Studio) returns ``{"error": ...}`` with HTTP
    200; a captive portal returns HTML. Indexing straight into ``resp.json()``
    turned each of those into a raw KeyError/JSONDecodeError that escaped every
    handler between here and the sync job, killing the whole run on the first
    bad chunk.
    """
    try:
        node = resp.json()
    except ValueError as exc:
        raise LLMError(
            f"{config.provider} returned a non-JSON response "
            f"({resp.headers.get('content-type', 'unknown type')})."
        ) from exc
    try:
        for step in path:
            node = node[step]
        return node
    except (KeyError, IndexError, TypeError) as exc:
        if default is not _UNSET:
            return default
        raise LLMError(
            f"Unexpected {config.provider} response shape: missing "
            f"{'.'.join(str(p) for p in path)}."
        ) from exc


# Transient conditions worth another attempt. A retired model, a bad key, or a
# malformed request is deliberately absent: those fail identically every time,
# so retrying them only burns quota and delays the real error.
_RETRY_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3
_BASE_BACKOFF_SECONDS = 0.75
_MAX_BACKOFF_SECONDS = 20.0


def _retry_after_seconds(exc: Exception) -> float | None:
    """Honour a provider's ``Retry-After`` header when it sends one."""
    resp = getattr(exc, "response", None)
    if resp is None:
        return None
    raw = getattr(resp, "headers", {}).get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def _should_retry(exc: Exception) -> bool:
    resp = getattr(exc, "response", None)
    if resp is None:
        # Timeouts and dropped connections carry no response at all.
        return isinstance(exc, httpx.TimeoutException | httpx.NetworkError)
    return resp.status_code in _RETRY_STATUSES


async def _generate_with_retry(
    config: LLMConfig,
    prompt: str,
    system: str,
    *,
    attempts: int = _MAX_ATTEMPTS,
) -> str:
    """``_generate`` with exponential backoff over transient provider failures.

    One bad response used to be able to end a long run: sync aborts after two
    consecutive failed chunks, and across hundreds of chunks a transient 5xx is
    close to certain. Absorbing it here means the caller only ever sees a
    failure that survived several attempts, which is the only kind worth
    reporting to the user.
    """
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await _generate(config, prompt, system)
        except httpx.HTTPError as exc:
            last = exc
            if attempt >= attempts or not _should_retry(exc):
                raise
            delay = _retry_after_seconds(exc)
            if delay is None:
                delay = _BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                # Jitter so simultaneous chunk failures don't resynchronise
                # into a thundering herd against an already-struggling provider.
                delay += random.uniform(0.0, delay * 0.25)
            delay = min(delay, _MAX_BACKOFF_SECONDS)
            log.warning(
                "Provider call failed (attempt %d/%d): %s - retrying in %.1fs",
                attempt,
                attempts,
                _redact(str(exc)),
                delay,
            )
            await asyncio.sleep(delay)
    raise last if last is not None else LLMError("LLM failed")  # pragma: no cover


# Classifying a *merchant name* is a different, much easier task than
# classifying a raw descriptor: the noise is already gone, and one answer covers
# every transaction for that merchant. The model is also given an explicit way
# to abstain, because benchmarks show it will otherwise invent a confident
# answer for merchants it does not recognise.
MERCHANT_SYSTEM_PROMPT = (
    "You assign spending categories to merchant names from a bank statement. "
    "For each numbered merchant, choose the single best category from this "
    "list: __CATEGORIES__. "
    "Respond with ONLY a JSON object of the exact form: "
    '{"items": [{"i": 1, "merchant": "...", "category": "...", '
    '"confidence": 0.0}, ...]} '
    "with one element per input line, using each line's number as \"i\". "
    "\"merchant\" is a clean, human-readable name for the business. "
    "\"category\" MUST be copied exactly from the list above. "
    "\"confidence\" is 0.0-1.0 for how sure you are. "
    "If you do not recognise the merchant or cannot tell what it sells, use "
    "the category \"Uncategorized\" with a low confidence rather than "
    "guessing. Do not include markdown, code fences, or explanation."
)


@dataclass
class MerchantVerdict:
    merchant: str
    category: str
    confidence: float | None = None

    @property
    def display_name(self) -> str:
        return self.merchant


def parse_merchant_json(text: str, count: int) -> list[MerchantVerdict | None]:
    """Parse a merchant-classification response into an index-aligned list."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        candidate = re.sub(r"^json\s*", "", candidate, flags=re.IGNORECASE).strip()
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, TypeError) as exc:
        raise LLMError(f"Unparseable merchant output: {text[:200]!r}") from exc
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise LLMError(f"Merchant output missing 'items': {text[:200]!r}")

    results: list[MerchantVerdict | None] = [None] * count
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("i", 0)) - 1
        except (TypeError, ValueError):
            continue
        if not (0 <= idx < count):
            continue
        category = str(item.get("category", "")).strip()
        if not category:
            continue
        try:
            confidence = float(item["confidence"]) if "confidence" in item else None
        except (TypeError, ValueError):
            confidence = None
        results[idx] = MerchantVerdict(
            merchant=str(item.get("merchant", "")).strip(),
            category=category,
            confidence=confidence,
        )
    return results


async def classify_merchants(
    config: LLMConfig,
    merchants: list[str],
    categories: list[str],
) -> list[MerchantVerdict | None]:
    """Assign a category to each canonical merchant name in ONE model call."""
    if not merchants:
        return []
    system = MERCHANT_SYSTEM_PROMPT.replace("__CATEGORIES__", ", ".join(categories))
    lines = "\n".join(f'{i + 1}. "{m}"' for i, m in enumerate(merchants))
    prompt = f"Merchants:\n{lines}"
    try:
        text = await _generate_with_retry(config, prompt, system)
    except httpx.HTTPError as exc:
        raise _endpoint_error(exc) from exc
    return parse_merchant_json(text, len(merchants))


BATCH_SYSTEM_PROMPT = (
    "You are a financial transaction normalizer. You receive a numbered list "
    "of raw bank statement descriptors. For each one, identify the real-world "
    "merchant and the best-fit spending category. Respond with ONLY a single "
    "JSON object of the exact form: "
    '{"items": [{"i": 1, "clean_merchant": "...", "category": "..."}, ...]} '
    "with one element per input line, using each line's number as \"i\". "
    "Choose categories from this list when possible: __CATEGORIES__. "
    "Do not include markdown, code fences, or explanation."
)


def parse_batch_json(text: str, count: int) -> list[CleanResult | None]:
    """Parse a batch response into an index-aligned list (None = unresolved)."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        candidate = re.sub(r"^json\s*", "", candidate, flags=re.IGNORECASE).strip()
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, TypeError) as exc:
        raise LLMError(f"Unparseable batch output: {text[:200]!r}") from exc
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise LLMError(f"Batch output missing 'items': {text[:200]!r}")

    results: list[CleanResult | None] = [None] * count
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("i", 0)) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= idx < count and item.get("clean_merchant"):
            results[idx] = CleanResult(
                clean_merchant=str(item["clean_merchant"]).strip() or "Unknown",
                category=str(item.get("category", "Uncategorized")).strip()
                or "Uncategorized",
            )
    return results


async def clean_merchants_batch(
    config: LLMConfig,
    raw_descriptions: list[str],
    categories: list[str],
) -> list[CleanResult | None]:
    """Clean + categorize many descriptors in ONE model call.

    Returns an index-aligned list; entries the model failed to resolve are
    ``None`` (the caller decides whether to retry them individually). Raises
    ``LLMError`` when the endpoint is unreachable or output is unusable.
    """
    if not raw_descriptions:
        return []
    system = BATCH_SYSTEM_PROMPT.replace("__CATEGORIES__", ", ".join(categories))
    lines = "\n".join(
        f'{i + 1}. "{raw}"' for i, raw in enumerate(raw_descriptions)
    )
    prompt = f"Raw descriptors:\n{lines}"
    try:
        text = await _generate_with_retry(config, prompt, system)
    except httpx.HTTPError as exc:
        raise _endpoint_error(exc) from exc
    return parse_batch_json(text, len(raw_descriptions))


async def generate_json(config: LLMConfig, system: str, prompt: str) -> dict:
    """Run one JSON-mode generation and return the parsed object.

    Generic helper for structured tasks beyond categorization (e.g. parsing a
    natural-language scenario). Raises ``LLMError`` on transport/parse failure.
    """
    try:
        text = await _generate_with_retry(config, prompt, system)
    except httpx.HTTPError as exc:
        raise _endpoint_error(exc) from exc
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        candidate = re.sub(r"^json\s*", "", candidate, flags=re.IGNORECASE).strip()
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise LLMError(f"Unparseable JSON output: {text[:200]!r}") from None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise LLMError(f"Unparseable JSON output: {text[:200]!r}") from exc
    if not isinstance(data, dict):
        raise LLMError("Model returned non-object JSON")
    return data


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
            text = await _generate_with_retry(config, prompt, system)
            return parse_model_json(text)
        except httpx.HTTPError as exc:
            raise _endpoint_error(exc) from exc
        except LLMError as exc:
            last_exc = exc
            continue
    raise LLMError(str(last_exc) if last_exc else "LLM failed")
