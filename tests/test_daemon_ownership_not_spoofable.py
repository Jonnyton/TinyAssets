"""Ownership on a daemon must come from the authenticated actor, not the body."""
from __future__ import annotations

from pathlib import Path

from tinyassets.daemon_registry import PROJECT_LOOP_FLAG, create_daemon, select_project_loop_daemon


def test_caller_cannot_spoof_daemon_ownership(tmp_path: Path):
    """Regression: metadata used setdefault, so a caller's value won.

    `daemon_create` takes caller metadata from the public surface. With
    setdefault an attacker could mint a daemon claiming owner_user_id="victim"
    and satisfy any owner-scoped check built on it — including the project-loop
    selector whose flag cloud_worker uses to register runtime authority.
    """
    daemon = create_daemon(
        str(tmp_path),
        display_name="attacker daemon",
        created_by="attacker",
        soul_mode="soul",
        soul_text="attacker soul",
        metadata={
            "universe_id": "u-victim",
            PROJECT_LOOP_FLAG: True,
            "owner_user_id": "victim",     # spoof attempt
            "created_by": "victim",        # spoof attempt
            "tenant_id": "victim",         # spoof attempt
        },
    )
    assert daemon["owner_user_id"] == "attacker", "ownership was spoofable"

    # And the victim-scoped selector must not find it.
    assert select_project_loop_daemon(
        str(tmp_path), universe_id="u-victim", owner_user_id="victim"
    ) is None
    # It IS the attacker's own.
    assert select_project_loop_daemon(
        str(tmp_path), universe_id="u-victim", owner_user_id="attacker"
    ) is not None


def test_ownership_still_derives_from_created_by(tmp_path: Path):
    """The happy path must stay green: no metadata -> owner is the actor."""
    daemon = create_daemon(
        str(tmp_path),
        display_name="ordinary daemon",
        created_by="alice",
        soul_mode="soul",
        soul_text="alice soul",
        metadata={"universe_id": "u-alice"},
    )
    assert daemon["owner_user_id"] == "alice"
    assert daemon["tenant_id"] == "alice"


def test_summon_cannot_spoof_runtime_ownership(tmp_path: Path):
    """summon_daemon had the same setdefault hole as create_daemon.

    `daemon_summon` forwards caller metadata from the public surface, so with
    setdefault an attacker could mint a RUNTIME carrying owner_user_id/tenant_id
    naming a victim — even though the daemon row itself was protected.
    Ownership must come from the daemon row, which is server state.
    """
    from tinyassets.daemon_registry import summon_daemon

    daemon = create_daemon(
        str(tmp_path),
        display_name="victim daemon",
        created_by="victim",
        soul_mode="soul",
        soul_text="victim soul",
        metadata={"universe_id": "u-victim"},
    )
    assert daemon["owner_user_id"] == "victim"

    runtime = summon_daemon(
        str(tmp_path),
        daemon_id=daemon["daemon_id"],
        universe_id="u-victim",
        provider_name="claude-code",
        model_name="claude-opus",
        created_by="attacker",
        metadata={
            "owner_user_id": "attacker",   # spoof attempt
            "tenant_id": "attacker",       # spoof attempt
        },
    )
    meta = runtime.get("metadata") or runtime
    owner = str(meta.get("owner_user_id") or runtime.get("owner_user_id") or "")
    assert owner == "victim", f"runtime ownership was spoofable: {owner}"
