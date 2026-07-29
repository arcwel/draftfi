"""Keep the configured LLM model usable — quietly, and without ever blocking.

Cloud providers retire model ids on their own schedule. When that happens the
provider stays up, the API key stays valid, and the model even stays in the
published catalogue — but every generation call 404s. The old behaviour was to
surface that 404 to the user as a failed sync and stop there, which put the
burden of diagnosis on someone who did nothing wrong.

This module inverts that. When the configured model is gone, DraftFi picks a
live replacement, saves it, and records a dismissible notice explaining what
changed. The user's work continues; they find out afterwards. The guard never
raises — a repair that fails leaves the config exactly as it was, and the
caller carries on with whatever the health check reported.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

from app.services import llm, llm_config
from app.services.llm_config import LLMConfig

log = logging.getLogger("draftfi.model_guard")

# How many substitutes to try before giving up for this call. A provider mid-
# reshuffle can retire several ids at once; trying forever would stall a sync.
MAX_CANDIDATES = 3


@dataclass
class GuardResult:
    config: LLMConfig
    health: llm.HealthResult
    switched: bool = False
    notice: dict | None = None


async def ensure_usable_model(
    conn: sqlite3.Connection,
    config: LLMConfig | None = None,
    *,
    health: llm.HealthResult | None = None,
) -> GuardResult:
    """Probe the active model and repair the config if it has been retired.

    Pass ``health`` to reuse a probe you already ran. Local providers (Ollama)
    are repaired the same way — a model the user never pulled reads as gone,
    and switching to one they do have beats failing.
    """
    config = config or llm_config.resolve_config(conn)
    result = health or await llm.check(config)
    if not result.model_gone:
        return GuardResult(config=config, health=result)

    original_model = config.model
    log.warning(
        "Model %r is no longer available from provider %r - looking for a "
        "replacement",
        original_model,
        config.provider,
    )

    try:
        available = await llm.list_models(config)
    except llm.LLMError as exc:
        # The catalogue is unreachable (offline, bad key). Fall back to the
        # provider's ranked list rather than abandoning the repair entirely.
        log.info("Could not list models (%s); using ranked fallbacks", exc)
        available = []

    tried: set[str] = {original_model}
    for _ in range(MAX_CANDIDATES):
        candidate = llm_config.pick_replacement_model(
            config.provider,
            [m for m in available if m not in tried],
            current=original_model,
        )
        if not candidate or candidate in tried:
            break
        tried.add(candidate)

        probe_config = LLMConfig(
            provider=config.provider,
            model=candidate,
            base_url=config.base_url,
            api_key=config.api_key,
        )
        probe = await llm.check(probe_config)
        if probe.model_gone:
            log.info("Replacement %r is also unavailable; trying the next", candidate)
            continue
        if not probe.available:
            # Reachability problems (network, rate limit) say nothing about the
            # model, so stop probing rather than churning through the whole
            # catalogue against a provider that is simply unhappy right now.
            log.info(
                "Replacement %r could not be verified (%s); leaving config alone",
                candidate,
                probe.detail,
            )
            break

        llm_config.set_model(conn, candidate)
        notice = llm_config.record_model_notice(
            conn,
            provider=config.provider,
            previous_model=original_model,
            new_model=candidate,
            reason=result.detail or "",
        )
        conn.commit()
        log.warning(
            "Switched model %r -> %r for provider %r",
            original_model,
            candidate,
            config.provider,
        )
        return GuardResult(
            config=probe_config, health=probe, switched=True, notice=notice
        )

    log.warning(
        "No usable replacement found for %r; leaving the configuration unchanged",
        original_model,
    )
    return GuardResult(config=config, health=result)
