"""Truthful per-store attestation.

``TINYASSETS_BYO_VAULT_ENCRYPTED`` is an operator opt-in, not proof. This module
runs the REAL storage path at boot (and gates every ``get``) so the flag can
only be honest:

    put probe bytes under a reserved scope
      -> exact read returns them
      -> persisted bytes are backend-appropriate protected (no plaintext)
      -> a wrong-scope read FAILS
      -> delete
      -> a subsequent read is NOT_FOUND

The probe is duck-typed against a backend exposing ``custody``, ``store_id``,
``_probe_put``, ``_probe_get``, ``_probe_delete`` and ``inspect_persisted``.
Failure disables only that store.
"""

from __future__ import annotations

import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .errors import CredentialUnavailable
from .types import (
    PROBE_SCOPE,
    Custody,
    SecretBinding,
    SecretScope,
)

# One boot id per process — attestation is cached per (store, boot).
BOOT_ID = uuid.uuid4().hex

_PROBE_VALUE_BYTES = 32


@dataclass
class AttestationResult:
    ok: bool
    store_id: str
    custody: str
    boot_id: str
    tested_at: float
    checks: dict[str, bool] = field(default_factory=dict)
    failure: str | None = None

    def public_projection(self) -> dict[str, Any]:
        """Safe status projection — names the store's health, never its internals."""
        return {
            "store_id": self.store_id,
            "custody": self.custody,
            "ok": self.ok,
            "tested_at": self.tested_at,
        }


def _wrong_scope(scope: SecretScope) -> SecretScope:
    return SecretScope(
        founder_id=scope.founder_id,
        universe_id=scope.universe_id,
        provider=scope.provider,
        destination="__wrong_destination__",
        purpose=scope.purpose,
    )


def _evidence_ok(custody: Custody, evidence: dict[str, Any]) -> tuple[bool, dict[str, bool]]:
    """Backend-appropriate persisted-evidence assertions."""
    checks: dict[str, bool] = {
        "persisted": bool(evidence.get("present")),
        "plaintext_absent": bool(evidence.get("plaintext_absent")),
    }
    if custody == Custody.PLATFORM_ENCRYPTED:
        checks["algorithm_ok"] = bool(evidence.get("algorithm_ok"))
        checks["has_ciphertext"] = bool(evidence.get("has_ciphertext"))
        checks["has_wrapped_dek"] = bool(evidence.get("has_wrapped_dek"))
        checks["key_id_active"] = bool(evidence.get("key_id_active"))
    else:  # DAEMON_LOCAL
        checks["protection_current_user"] = bool(evidence.get("protection_current_user"))
        checks["current_user_bound"] = bool(evidence.get("current_user_bound"))
        checks["has_blob"] = bool(evidence.get("has_blob"))
    return all(checks.values()), checks


def attest_store(backend: Any) -> AttestationResult:
    """Run the real put/read/wrong-scope/delete/not-found probe against ``backend``."""
    custody: Custody = backend.custody
    store_id: str = backend.store_id
    result = AttestationResult(
        ok=False,
        store_id=store_id,
        custody=custody.value,
        boot_id=BOOT_ID,
        tested_at=time.time(),
    )
    probe_value = secrets.token_bytes(_PROBE_VALUE_BYTES)
    scope = PROBE_SCOPE

    try:
        descriptor = backend._probe_put(scope, probe_value)
        binding = descriptor.binding
    except Exception as exc:  # noqa: BLE001
        result.failure = f"put:{_class(exc)}"
        return result

    try:
        # 1. exact read returns the probe bytes
        read_back = backend._probe_get(binding, scope)
        result.checks["exact_read"] = read_back == probe_value

        # 2. persisted bytes are backend-appropriate protected, no plaintext
        evidence = backend.inspect_persisted(binding.ref, probe_value)
        ev_ok, ev_checks = _evidence_ok(custody, evidence)
        result.checks.update(ev_checks)

        # 3. a wrong-scope read MUST fail
        wrong = _wrong_scope(scope)
        wrong_binding = SecretBinding(
            ref=binding.ref, kind=binding.kind, scope=wrong, store=binding.store
        )
        result.checks["wrong_scope_fails"] = _must_fail(
            backend._probe_get, wrong_binding, wrong
        )
    finally:
        # 4. delete (always attempt cleanup even if a check raised)
        deleted = _safe_delete(backend, binding, scope)
    result.checks["delete_ok"] = deleted

    # 5. a subsequent read is NOT_FOUND
    result.checks["not_found_after_delete"] = _is_not_found(backend, binding, scope)

    result.ok = bool(result.checks.get("exact_read")) and ev_ok and all(
        result.checks.get(k, False)
        for k in ("wrong_scope_fails", "delete_ok", "not_found_after_delete")
    )
    if not result.ok:
        failed = [k for k, v in result.checks.items() if not v]
        result.failure = "checks_failed:" + ",".join(sorted(failed))
    return result


def _class(exc: BaseException) -> str:
    return type(exc).__name__


def _must_fail(fn: Any, *args: Any) -> bool:
    """True iff ``fn(*args)`` raises CredentialUnavailable (fail-closed)."""
    try:
        fn(*args)
    except CredentialUnavailable:
        return True
    except Exception:  # noqa: BLE001 — any failure is still "did not disclose"
        return True
    return False


def _safe_delete(backend: Any, binding: SecretBinding, scope: SecretScope) -> bool:
    try:
        backend._probe_delete(binding, scope)
        return True
    except Exception:  # noqa: BLE001
        return False


def _is_not_found(backend: Any, binding: SecretBinding, scope: SecretScope) -> bool:
    try:
        backend._probe_get(binding, scope)
    except CredentialUnavailable as exc:
        return exc.code == "NOT_FOUND"
    except Exception:  # noqa: BLE001
        return False
    return False


def operator_opt_in() -> bool:
    """Read the operator opt-in flag (honest by itself proves nothing)."""
    return os.environ.get("TINYASSETS_BYO_VAULT_ENCRYPTED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def byo_execution_enabled(
    backend: Any,
    binding: SecretBinding,
    *,
    auth_health: bool = True,
) -> bool:
    """S5 gate: BYO execution is enabled ONLY when all of these pass together.

    1. operator opt-in (``TINYASSETS_BYO_VAULT_ENCRYPTED``),
    2. this-boot store probe passes,
    3. the specific record validates (a real scope-checked ``get`` succeeds),
    4. provider auth-health (supplied by the adapter).

    Any failure returns False — never a partial or ambient enablement.
    """
    if not operator_opt_in():
        return False
    if not auth_health:
        return False
    probe = attest_store(backend)
    if not probe.ok:
        return False
    try:
        with backend.get(binding, binding.scope):
            pass
    except CredentialUnavailable:
        return False
    except Exception:  # noqa: BLE001
        return False
    return True
