"""Multiprocess concurrency + single-refresh-race proofs for the platform vault.

This closes the known concurrent-refresh CVE class (Better Auth CVE-2026-53517;
rotating-refresh providers revoke the whole token family on replay). Two proofs:

* **50+ concurrent put/get/delete** across real OS processes against one
  rollback-journal (DELETE + EXTRA, NOT WAL) DB — proves the store survives
  simultaneous writers with no corruption or lost fail-closed semantics.
* **single-refresh race** — many workers race to refresh ONE ref; the fenced
  exclusive per-ref lease + still-held check + fenced commit means exactly ONE
  refresh runs and the losers skip gracefully (no error, no double token-burn).
  The fenced TTL-overrun / crash-reacquire proof lives in
  ``test_credential_vault_hardening.py``.
* **daemon-local CAS** — concurrent DPAPI writers serialize through the control
  DB mutation lock; exactly one CAS winner.

Workers are module-level so they pickle under Windows spawn.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import nacl.bindings as sodium
import pytest

from tinyassets.credentials import (
    CredentialUnavailable,
    Custody,
    DpapiVaultBackend,
    InMemoryKeyProvider,
    PlatformVaultBackend,
    SecretBinding,
    SecretBytes,
    SecretKind,
    SecretScope,
    VaultErrorCode,
    VaultStore,
)

WINDOWS_ONLY = pytest.mark.skipif(
    sys.platform != "win32", reason="DPAPI local backend is Windows-only"
)

SCOPE = SecretScope(
    founder_id="founder:cc",
    universe_id="u-conc",
    provider="github",
    destination="octo/repo",
    purpose="external_write",
)
STORE_ID = "platform:default"
DAEMON_ID = "daemon-conc"


@pytest.fixture(autouse=True)
def _isolate_rollback_guard(tmp_path, monkeypatch):
    """Per-test anti-rollback guard OUTSIDE the vault data dir. Set in the parent
    BEFORE workers spawn so every worker process inherits the SAME guard domain
    (concurrent ``advance`` is BEGIN IMMEDIATE + monotonic-max, race-safe); the
    home-dir default would otherwise leak epochs across tests as false rollbacks."""
    monkeypatch.setenv("TINYASSETS_VAULT_ROLLBACK_GUARD", str(tmp_path / "_vault_guard"))


def _build(db_path: str, kek_hex: str, key_id: str) -> PlatformVaultBackend:
    kp = InMemoryKeyProvider({key_id: bytes.fromhex(kek_hex)}, key_id)
    return PlatformVaultBackend(kp, store_id=STORE_ID, db_path=db_path)


def _store() -> VaultStore:
    return VaultStore(custody=Custody.PLATFORM_ENCRYPTED, store_id=STORE_ID)


# ---------------------------------------------------------------------------
# Worker 1: full put/get/delete lifecycle (own ref, no logical conflict)
# ---------------------------------------------------------------------------


def _lifecycle_worker(args: tuple[str, str, str, int]) -> str:
    db_path, kek_hex, key_id, n = args
    try:
        be = _build(db_path, kek_hex, key_id)
        secret = f"secret-{n}-{os.getpid()}".encode()
        d = be.put(_store(), SCOPE, SecretKind.API_KEY, SecretBytes(secret))
        with be.get(d.binding, SCOPE) as lease:
            if lease.reveal() != secret:
                return f"mismatch:{n}"
        be.delete(d.binding, SCOPE)
        try:
            be.get(d.binding, SCOPE)
        except CredentialUnavailable as exc:
            if exc.code != VaultErrorCode.NOT_FOUND:
                return f"bad-code:{exc.code}"
        else:
            return f"not-deleted:{n}"
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"error:{type(exc).__name__}:{exc}"


def test_50plus_concurrent_put_get_delete(tmp_path):
    db_path = str(tmp_path / "vault.db")
    key_id = "k1"
    kek_hex = sodium.randombytes(32).hex()
    # Bootstrap schema + attestation once in the parent to avoid a first-op race
    # that is separately tested; here we stress steady-state concurrency.
    _build(db_path, kek_hex, key_id).attest()

    tasks = 64  # > 50 concurrent operations
    workers = min(16, (os.cpu_count() or 4) * 2)
    args = [(db_path, kek_hex, key_id, i) for i in range(tasks)]
    results: list[str] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_lifecycle_worker, a) for a in args]
        for fut in as_completed(futures):
            results.append(fut.result())

    assert results.count("ok") == tasks, f"failures: {[r for r in results if r != 'ok']}"


# ---------------------------------------------------------------------------
# Worker 2: concurrent bare CAS — exactly one writer wins version 1 -> 2
# ---------------------------------------------------------------------------


def _cas_worker(args: tuple[str, str, str, str, int]) -> str:
    db_path, kek_hex, key_id, ref, n = args
    be = _build(db_path, kek_hex, key_id)
    try:
        be.put(
            _store(), SCOPE, SecretKind.API_KEY, SecretBytes(f"cas-{n}".encode()),
            replace=ref, expected_version=1,
        )
        return "won"
    except CredentialUnavailable as exc:
        return f"conflict:{exc.code}"
    except Exception as exc:  # noqa: BLE001
        return f"error:{type(exc).__name__}"


def test_concurrent_cas_exactly_one_winner(tmp_path):
    db_path = str(tmp_path / "vault.db")
    key_id = "k1"
    kek_hex = sodium.randombytes(32).hex()
    be = _build(db_path, kek_hex, key_id)
    be.attest()
    d = be.put(_store(), SCOPE, SecretKind.API_KEY, SecretBytes(b"initial"))
    ref = d.binding.ref

    racers = 12
    args = [(db_path, kek_hex, key_id, ref, i) for i in range(racers)]
    results: list[str] = []
    with ProcessPoolExecutor(max_workers=racers) as pool:
        for fut in as_completed([pool.submit(_cas_worker, a) for a in args]):
            results.append(fut.result())

    assert results.count("won") == 1, f"results: {results}"
    assert all(r.startswith("conflict:") for r in results if r != "won"), results
    # final state is version 2 (exactly one CAS applied)
    with be.get(d.binding, SCOPE) as lease:
        assert lease.version == 2


# ---------------------------------------------------------------------------
# Worker 3: single-refresh race — lease + re-check means exactly ONE refresh
# ---------------------------------------------------------------------------


def _refresh_worker(args: tuple[str, str, str, str, str, int]) -> str:
    db_path, kek_hex, key_id, ref, marker_dir, n = args
    be = _build(db_path, kek_hex, key_id)
    binding = SecretBinding(
        ref=ref, kind=SecretKind.GITHUB_APP_USER_TOKEN, scope=SCOPE, store=_store()
    )
    try:
        with be.refresh_lease(ref, f"worker-{n}", wait=60.0):
            # re-check the stored version INSIDE the lock
            with be.get(binding, SCOPE) as got:
                current = got.version
            if current != 1:
                return "skipped"
            ticket = be.begin_refresh(binding, SCOPE, f"worker-{n}", at_version=current)
            if ticket is None:
                return "skipped"
            Path(marker_dir, f"refresh-{n}.marker").write_text("1", encoding="utf-8")
            be.complete_refresh(
                binding, SCOPE, ticket, SecretBytes(f"refreshed-by-{n}".encode())
            )
            return "refreshed"
    except Exception as exc:  # noqa: BLE001
        return f"error:{type(exc).__name__}:{exc}"


def test_single_refresh_race_runs_exactly_once(tmp_path):
    db_path = str(tmp_path / "vault.db")
    key_id = "k1"
    kek_hex = sodium.randombytes(32).hex()
    marker_dir = tmp_path / "markers"
    marker_dir.mkdir()

    be = _build(db_path, kek_hex, key_id)
    be.attest()
    d = be.put(
        _store(), SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"initial-token")
    )
    ref = d.binding.ref

    racers = 8
    args = [(db_path, kek_hex, key_id, ref, str(marker_dir), i) for i in range(racers)]
    results: list[str] = []
    with ProcessPoolExecutor(max_workers=racers) as pool:
        for fut in as_completed([pool.submit(_refresh_worker, a) for a in args]):
            results.append(fut.result())

    errors = [r for r in results if r.startswith("error:")]
    assert not errors, f"refresh workers errored: {errors}"
    # exactly ONE refresh ran; the rest skipped gracefully (no VERSION_CONFLICT)
    assert results.count("refreshed") == 1, f"results: {results}"
    assert results.count("skipped") == racers - 1, f"results: {results}"
    assert len(list(marker_dir.glob("*.marker"))) == 1
    # the refreshed value is at version 2 — no double burn
    with be.get(d.binding, SCOPE) as lease:
        assert lease.version == 2
        assert lease.reveal().startswith(b"refreshed-by-")


# ---------------------------------------------------------------------------
# Worker 4: daemon-local (DPAPI) CAS is atomic under the mutation lock
# ---------------------------------------------------------------------------


def _dpapi_store(store_id: str, daemon_id: str) -> VaultStore:
    return VaultStore(custody=Custody.DAEMON_LOCAL, store_id=store_id, daemon_id=daemon_id)


def _dpapi_cas_worker(args: tuple[str, str, str]) -> str:
    base, ref, n = args
    be = DpapiVaultBackend(daemon_id=DAEMON_ID, store_id=STORE_ID, base=base)
    store = _dpapi_store(STORE_ID, DAEMON_ID)
    try:
        be.put(
            store, SCOPE, SecretKind.API_KEY, SecretBytes(f"dpapi-cas-{n}".encode()),
            replace=ref, expected_version=1,
        )
        return "won"
    except CredentialUnavailable as exc:
        return f"conflict:{exc.code}"
    except Exception as exc:  # noqa: BLE001
        return f"error:{type(exc).__name__}:{exc}"


# ---------------------------------------------------------------------------
# Worker 5: EXACTLY ONE actual provider call (consume-before-mint), even on a
# TTL overrun — counts real redemptions, not just commits (review r2 crit #1)
# ---------------------------------------------------------------------------


def _claim_worker(args: tuple[str, str, str, str, str, int, bool]) -> str:
    db_path, kek_hex, key_id, ref, marker_dir, n, slow = args
    be = _build(db_path, kek_hex, key_id)
    binding = SecretBinding(
        ref=ref, kind=SecretKind.GITHUB_APP_USER_TOKEN, scope=SCOPE, store=_store()
    )
    try:
        with be.refresh_lease(ref, f"w{n}", ttl=0.3, wait=60.0):
            if slow:
                time.sleep(0.6)  # overrun the lease TTL → lease may be stolen
            with be.get(binding, SCOPE) as got:
                current = got.version
            if current != 1:
                return "skip-fresh"  # already refreshed by someone
            # ATOMIC consume-before-mint tied to the observed version: only the
            # claim winner may call the provider.
            ticket = be.begin_refresh(binding, SCOPE, f"w{n}", at_version=current)
            if ticket is None:
                return "skip-claimed"
            # THE single provider redemption for this refresh event
            Path(marker_dir, f"call-{n}.marker").write_text("1", encoding="utf-8")
            # completion bound to the durable ticket (sanctioned broker path)
            be.complete_refresh(
                binding, SCOPE, ticket, SecretBytes(f"fresh-{n}".encode())
            )
            return "refreshed"
    except CredentialUnavailable as exc:
        return f"cu:{exc.code}"
    except Exception as exc:  # noqa: BLE001
        return f"error:{type(exc).__name__}:{exc}"


def test_refresh_makes_exactly_one_provider_call(tmp_path):
    db_path = str(tmp_path / "vault.db")
    key_id = "k1"
    kek_hex = sodium.randombytes(32).hex()
    marker_dir = tmp_path / "calls"
    marker_dir.mkdir()

    be = _build(db_path, kek_hex, key_id)
    be.attest()
    d = be.put(_store(), SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"v1-token"))
    ref = d.binding.ref

    racers = 8
    # worker 0 overruns its lease TTL (simulated stall) to force a steal.
    args = [(db_path, kek_hex, key_id, ref, str(marker_dir), i, i == 0) for i in range(racers)]
    results: list[str] = []
    with ProcessPoolExecutor(max_workers=racers) as pool:
        for fut in as_completed([pool.submit(_claim_worker, a) for a in args]):
            results.append(fut.result())

    errors = [r for r in results if r.startswith("error:")]
    assert not errors, f"claim workers errored: {errors}"
    # THE guarantee: exactly ONE real provider call across every worker, ever.
    assert len(list(marker_dir.glob("*.marker"))) == 1, results
    assert results.count("refreshed") == 1, results
    with be.get(d.binding, SCOPE) as lease:
        assert lease.version == 2


# ---------------------------------------------------------------------------
# Worker 6: refresh claims survive a HARD process kill (os._exit) — this proves
# PROCESS-CRASH durability (committed rollback-journal + EXTRA). Full power-cut /
# VM-reset durability is a deploy-validation release gate, NOT proven by os._exit.
# ---------------------------------------------------------------------------


def _crash_after_claim(args: tuple[str, str, str, str]) -> None:
    db_path, kek_hex, key_id, ref = args
    be = _build(db_path, kek_hex, key_id)
    binding = SecretBinding(
        ref=ref, kind=SecretKind.GITHUB_APP_USER_TOKEN, scope=SCOPE, store=_store()
    )
    ticket = be.begin_refresh(binding, SCOPE, "crasher", at_version=1)
    if ticket is None:
        os._exit(3)  # claim should have won
    os._exit(0)  # HARD crash immediately after the committed claim — no cleanup


def test_refresh_claim_survives_hard_crash(tmp_path):
    db_path = str(tmp_path / "vault.db")
    key_id = "k1"
    kek_hex = sodium.randombytes(32).hex()
    be = _build(db_path, kek_hex, key_id)
    be.attest()
    d = be.put(_store(), SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"v1"))
    ref = d.binding.ref

    ctx = mp.get_context("spawn")
    proc = ctx.Process(target=_crash_after_claim, args=((db_path, kek_hex, key_id, ref),))
    proc.start()
    proc.join(timeout=60)
    assert proc.exitcode == 0, f"crash worker exit={proc.exitcode}"

    # The committed claim survived the hard kill → a fresh process cannot re-redeem
    # version 1's one-time token (durability, not just logic).
    be2 = _build(db_path, kek_hex, key_id)
    be2.attest()
    binding = SecretBinding(
        ref=ref, kind=SecretKind.GITHUB_APP_USER_TOKEN, scope=SCOPE, store=_store()
    )
    assert be2.begin_refresh(binding, SCOPE, "recover", at_version=1) is None


def test_vault_db_durability_posture(tmp_path):
    be = _build(str(tmp_path / "v.db"), sodium.randombytes(32).hex(), "k1")
    info = be.durability_info()
    # EXTRA's extra fsync is a DELETE-mode guarantee — TRUNCATE is not durable,
    # WAL has the reset-corruption bug. Assert the EFFECTIVE (queried-back) pragmas.
    assert info["synchronous"] == "EXTRA"
    assert info["journal_mode"].upper() == "DELETE"


# ---------------------------------------------------------------------------
# Worker 7: daemon-local writes survive a HARD process kill (os._exit) — the
# durable-write sequence (fsync + write-through). Proves PROCESS-CRASH durability;
# full power-cut proof is a deploy-validation gate (review r4 #6).
# ---------------------------------------------------------------------------


def _dpapi_put_then_crash(args: tuple[str, str]) -> None:
    base, ref_file = args
    be = DpapiVaultBackend(daemon_id=DAEMON_ID, store_id=STORE_ID, base=base)
    store = _dpapi_store(STORE_ID, DAEMON_ID)
    d = be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"durable-local"))
    Path(ref_file).write_text(d.binding.ref, encoding="utf-8")
    os._exit(0)  # HARD crash after the fsync'd durable write


@WINDOWS_ONLY
def test_local_write_survives_hard_crash(tmp_path):
    base = str(tmp_path / "loc")
    ref_file = str(tmp_path / "ref.txt")
    ctx = mp.get_context("spawn")
    proc = ctx.Process(target=_dpapi_put_then_crash, args=((base, ref_file),))
    proc.start()
    proc.join(timeout=60)
    assert proc.exitcode == 0, f"crash worker exit={proc.exitcode}"

    ref = Path(ref_file).read_text(encoding="utf-8").strip()
    be = DpapiVaultBackend(daemon_id=DAEMON_ID, store_id=STORE_ID, base=base)
    be.attest()
    binding = SecretBinding(
        ref=ref, kind=SecretKind.API_KEY, scope=SCOPE,
        store=_dpapi_store(STORE_ID, DAEMON_ID),
    )
    with be.get(binding, SCOPE) as lease:
        assert lease.reveal() == b"durable-local"


@WINDOWS_ONLY
def test_dpapi_concurrent_cas_exactly_one_winner(tmp_path):
    base = str(tmp_path / "local")
    be = DpapiVaultBackend(daemon_id=DAEMON_ID, store_id=STORE_ID, base=base)
    be.attest()
    store = _dpapi_store(STORE_ID, DAEMON_ID)
    d = be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"initial"))
    ref = d.binding.ref

    racers = 10
    args = [(base, ref, i) for i in range(racers)]
    results: list[str] = []
    with ProcessPoolExecutor(max_workers=racers) as pool:
        for fut in as_completed([pool.submit(_dpapi_cas_worker, a) for a in args]):
            results.append(fut.result())

    errors = [r for r in results if r.startswith("error:")]
    assert not errors, f"dpapi cas workers errored: {errors}"
    assert results.count("won") == 1, f"results: {results}"
    with be.get(d.binding, SCOPE) as lease:
        assert lease.version == 2
