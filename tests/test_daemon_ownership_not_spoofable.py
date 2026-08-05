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
