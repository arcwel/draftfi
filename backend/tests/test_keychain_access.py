"""Keychain access must never freeze the app, and opting out must mean it.

macOS grants keychain access per binary signature. Rebuilding DraftFi (ad-hoc
signed, new hash every time) invalidates the grant, so the next read pops a
system dialog and blocks until someone clicks it. That read sits on the boot
path, which made the app look frozen with no explanation.
"""
from __future__ import annotations

import threading
import time

import pytest

from app.db import repository as repo
from app.services import llm, llm_config

KEY_ROW = "llm_api_key:gemini"


@pytest.fixture(autouse=True)
def _isolate_keychain_state(monkeypatch):
    """Module-level keychain caches are global; give each test a clean slate."""
    monkeypatch.setattr(llm_config, "_keychain_status", llm_config.KEYCHAIN_OK)
    monkeypatch.setattr(llm_config, "_keychain_reads", {})
    monkeypatch.setattr(llm_config, "_keyring_state", None)


def test_opting_out_of_the_keychain_blocks_reads_not_just_writes(conn, monkeypatch):
    """DRAFTFI_NO_KEYRING used to gate only writes, so tests and headless
    servers still hit the real OS keychain (and its dialogs) on every read."""
    monkeypatch.setenv("DRAFTFI_NO_KEYRING", "1")
    repo.set_setting(conn, KEY_ROW, llm_config._KEYRING_MARKER)

    reads: list[tuple] = []

    class SpyKeyring:
        def get_password(self, *args):
            reads.append(args)
            return "should-never-be-read"

    monkeypatch.setattr(llm_config, "keyring", SpyKeyring())

    assert llm_config.get_key(conn, "gemini") is None
    assert reads == [], "the opt-out must prevent the read itself"


def test_plaintext_keys_still_resolve_when_the_keychain_is_off(conn, monkeypatch):
    """The opt-out must not break the fallback path it exists to enable."""
    monkeypatch.setenv("DRAFTFI_NO_KEYRING", "1")
    repo.set_setting(conn, KEY_ROW, "plain-text-key")
    assert llm_config.get_key(conn, "gemini") == "plain-text-key"


def test_a_pending_keychain_prompt_does_not_hang_the_caller(conn, monkeypatch):
    monkeypatch.delenv("DRAFTFI_NO_KEYRING", raising=False)
    monkeypatch.setattr(llm_config, "_keyring_state", True)  # keychain "usable"
    monkeypatch.setattr(llm_config, "KEYCHAIN_TIMEOUT_SECONDS", 0.2)
    repo.set_setting(conn, KEY_ROW, llm_config._KEYRING_MARKER)

    approved = threading.Event()

    class DialogKeyring:
        """Stands in for a keychain read parked on an unanswered OS prompt."""

        def get_password(self, service, key_id):
            approved.wait(10)
            return "secret-key"

    monkeypatch.setattr(llm_config, "keyring", DialogKeyring())

    started = time.monotonic()
    assert llm_config.get_key(conn, "gemini") is None
    assert time.monotonic() - started < 2.0, "must give up, not wait on the user"
    assert llm_config.keychain_status() == llm_config.KEYCHAIN_WAITING

    # Once known blocked, later calls return at once instead of paying the
    # timeout again — otherwise every poll re-stalls the UI.
    started = time.monotonic()
    assert llm_config.get_key(conn, "gemini") is None
    assert time.monotonic() - started < 0.1

    # Approving the prompt resolves the read that was already in flight; no
    # restart, no second dialog.
    approved.set()
    deadline = time.monotonic() + 5
    value = None
    while time.monotonic() < deadline:
        value = llm_config.get_key(conn, "gemini")
        if value is not None:
            break
        time.sleep(0.05)
    assert value == "secret-key"
    assert llm_config.keychain_status() == llm_config.KEYCHAIN_OK


def test_one_stuck_dialog_does_not_spawn_a_thread_per_request(conn, monkeypatch):
    monkeypatch.delenv("DRAFTFI_NO_KEYRING", raising=False)
    monkeypatch.setattr(llm_config, "_keyring_state", True)
    monkeypatch.setattr(llm_config, "KEYCHAIN_TIMEOUT_SECONDS", 0.1)
    repo.set_setting(conn, KEY_ROW, llm_config._KEYRING_MARKER)

    never = threading.Event()
    starts = {"n": 0}

    class DialogKeyring:
        def get_password(self, service, key_id):
            starts["n"] += 1
            never.wait(10)
            return "secret-key"

    monkeypatch.setattr(llm_config, "keyring", DialogKeyring())

    for _ in range(5):
        assert llm_config.get_key(conn, "gemini") is None
    assert starts["n"] == 1, "the in-flight read must be reused"
    never.set()


def test_keychain_reads_run_on_daemon_threads(conn, monkeypatch):
    """A thread parked on an unanswered dialog must not stop the app quitting."""
    monkeypatch.delenv("DRAFTFI_NO_KEYRING", raising=False)
    monkeypatch.setattr(llm_config, "_keyring_state", True)
    monkeypatch.setattr(llm_config, "KEYCHAIN_TIMEOUT_SECONDS", 0.1)
    repo.set_setting(conn, KEY_ROW, llm_config._KEYRING_MARKER)

    release = threading.Event()

    class DialogKeyring:
        def get_password(self, service, key_id):
            release.wait(10)
            return "k"

    monkeypatch.setattr(llm_config, "keyring", DialogKeyring())
    llm_config.get_key(conn, "gemini")

    reads = llm_config._keychain_reads
    assert reads, "expected an in-flight read"
    assert all(r.thread.daemon for r in reads.values())
    release.set()


def test_a_failing_keychain_read_is_retried_not_cached_forever(conn, monkeypatch):
    monkeypatch.delenv("DRAFTFI_NO_KEYRING", raising=False)
    monkeypatch.setattr(llm_config, "_keyring_state", True)
    repo.set_setting(conn, KEY_ROW, llm_config._KEYRING_MARKER)

    attempts = {"n": 0}

    class FlakyKeyring:
        def get_password(self, service, key_id):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("keychain locked")
            return "secret-key"

    monkeypatch.setattr(llm_config, "keyring", FlakyKeyring())

    assert llm_config.get_key(conn, "gemini") is None
    assert llm_config.keychain_status() == llm_config.KEYCHAIN_ERROR
    assert llm_config.get_key(conn, "gemini") == "secret-key"
    assert llm_config.keychain_status() == llm_config.KEYCHAIN_OK


@pytest.mark.asyncio
async def test_status_explains_a_pending_prompt_instead_of_blaming_the_key(
    conn, monkeypatch
):
    """"no API key configured" is wrong and unactionable when the key exists and
    the OS is merely waiting for a click."""
    from app.api import llm_status as llm_api

    llm_api._invalidate_health_cache()
    repo.set_setting(conn, llm_config.K_PROVIDER, "gemini")
    repo.set_setting(conn, llm_config.K_MODEL, "gemini-flash-latest")
    monkeypatch.setattr(llm_config, "get_key", lambda c, p: None)
    monkeypatch.setattr(
        llm_config, "keychain_status", lambda: llm_config.KEYCHAIN_WAITING
    )

    async def must_not_probe(config):
        raise AssertionError("must not spend a provider call with no key")

    monkeypatch.setattr(llm, "check", must_not_probe)

    status = await llm_api.llm_status(conn)

    assert status.available is False
    assert status.keychain == llm_config.KEYCHAIN_WAITING
    assert "keychain" in (status.detail or "").lower()
    assert "always allow" in (status.detail or "").lower()
    # Must not be cached: the user is one click from resolving it.
    assert not llm_api._health_cache


def test_log_dir_is_redirectable(monkeypatch, tmp_path):
    """The suite relies on this to stay out of the user's real log file."""
    from app.services import logging_setup

    monkeypatch.setenv("DRAFTFI_LOG_DIR", str(tmp_path / "logs"))
    assert logging_setup.log_dir() == tmp_path / "logs"
    assert logging_setup.log_path().parent == tmp_path / "logs"
