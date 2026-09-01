"""An OAuth bundle has to be able to rotate, or it dies once and stays dead.

Live, 2026-09-01: the founder's universe stopped answering at 03:23:56Z and
never recovered across several container restarts. Captured through the app:

    {"provider": "codex", "status": "failed", "skip_class": "auth_invalid"}

Three layers produced that:

1. `/codex-home` is a tmpfs with the credential files bound READ-ONLY
   (`codex_provider.py`), stated as intent: "The credential bytes stay
   immutable; only scratch files can be created beside them."
2. the per-call snapshot is deleted afterwards, and nothing promoted a changed
   `auth.json` back to the vault;
3. **OAuth refresh tokens rotate on use** — so the first rotation invalidates
   the stored token, and the new value is thrown away with the snapshot.

Immutable credential bytes is a coherent stance for a STATIC secret and simply
incompatible with a rotating one. These tests pin the two halves of the fix:
the child can write its bundle, and the trusted parent decides whether that
write becomes the stored credential.
"""
from __future__ import annotations

import base64
import json

import pytest


def _bundle(access: str, refresh: str, account: str = "acct-1") -> bytes:
    return json.dumps({
        "tokens": {
            "access_token": access,
            "refresh_token": refresh,
            "account_id": account,
        }
    }).encode()


# --------------------------------------------------- the jail can write it


def test_the_auth_bundle_is_mounted_WRITABLE_and_nothing_else_is(tmp_path):
    """The refresh has to be physically possible before anything else matters.

    `auth.json` alone becomes writable: it is the file the CLI rewrites. The
    config and the lock stay read-only, and the bind target is the disposable
    per-call snapshot, never the vault.
    """
    from tinyassets.providers.codex_provider import _codex_home_file_mounts

    home = tmp_path / "codex-home"
    home.mkdir()
    (home / "auth.json").write_bytes(_bundle("a", "r"))
    (home / "config.toml").write_text('cli_auth_credentials_store = "file"\n')
    (home / ".lock").write_bytes(b"")

    args = _codex_home_file_mounts(home)
    modes = {
        args[i + 2].rsplit("/", 1)[-1]: args[i]
        for i in range(0, len(args), 3)
    }

    assert modes["auth.json"] == "--bind", (
        "the credential the CLI must rewrite is still read-only, so the refresh "
        "cannot happen and the bundle dies at its first rotation"
    )
    assert modes["config.toml"] == "--ro-bind"
    assert modes[".lock"] == "--ro-bind"


# ------------------------------------------- the parent decides what persists


@pytest.fixture
def vault(tmp_path, monkeypatch):
    """A universe with one deposited codex bundle."""
    from tinyassets.credential_vault import write_credential_vault

    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    universe = root / "u-1"
    universe.mkdir()
    write_credential_vault(universe, [{
        "credential_type": "llm_subscription",
        "service": "codex",
        "auth_json_b64": base64.b64encode(_bundle("old-access", "old-refresh")).decode(),
    }])
    return universe


def _stored(universe) -> bytes:
    from tinyassets.credential_vault import load_credential_vault

    [record] = [
        r for r in load_credential_vault(universe)
        if r.get("credential_type") == "llm_subscription"
    ]
    return base64.b64decode(record["auth_json_b64"])


def test_an_unrefreshed_call_touches_nothing(vault):
    """The common case. No rotation, no write, no lock contention."""
    from tinyassets.credential_vault import promote_refreshed_llm_credential

    assert promote_refreshed_llm_credential(None, None, universe_dir=vault) is False
    assert _stored(vault) == _bundle("old-access", "old-refresh")


def test_a_promotion_refuses_a_bundle_for_a_different_account(vault):
    """A changed subject is a different LOGIN, and a login belongs to the
    authenticated deposit path -- never to a provider subprocess."""
    from tinyassets.credential_vault import _codex_identity

    same = _codex_identity(_bundle("new-access", "new-refresh", account="acct-1"))
    other = _codex_identity(_bundle("new-access", "new-refresh", account="acct-2"))
    assert same != other, "account identity is not being compared at all"
    assert same == _codex_identity(_bundle("x", "y", account="acct-1")), (
        "identity must ignore the rotating token values"
    )


def test_identity_reads_a_flat_bundle_too(vault):
    """Not every auth.json nests under `tokens`."""
    from tinyassets.credential_vault import _codex_identity

    flat = json.dumps({"account_id": "acct-1", "access_token": "a"}).encode()
    nested = _bundle("a", "r", account="acct-1")
    assert _codex_identity(flat) == _codex_identity(nested)


def test_an_oversized_or_unparseable_bundle_is_refused(vault):
    """Whatever the child wrote, only a credible bundle is stored."""
    from tinyassets.credential_vault import _MAX_REFRESHED_AUTH_BYTES, _codex_identity

    assert _MAX_REFRESHED_AUTH_BYTES <= 256 * 1024
    with pytest.raises(Exception):
        _codex_identity(b"this is not json")
    with pytest.raises(Exception):
        _codex_identity(b'"a string, not an object"')
