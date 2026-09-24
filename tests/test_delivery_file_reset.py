"""Scoped identity reset against real receiver-owned file custody.

``account_deletion`` owns erasure of ``graph_delivery_files`` and proves it by
deleting rows (``test_delivery_file_transfer``). The operator-only *reset* path
is a different surface: ``apply_test_identity_reset`` only ever deletes from the
main database, so root run history -- where delivery custody provenance lives --
is classified read-only and refuses anything it cannot account for.

This module pins that refusal with a real transferred file present. It is a
cleanup test, not a table-allowlist test: adding ``graph_delivery_files`` to
``_KNOWN_ROOT_RUN_TABLES`` would clear the blocker and delete nothing, leaving
the subject's custody provenance behind a reset that reported success. The
assertion below is therefore that the reset fails closed AND that the row and
its bytes survive intact under enforced foreign keys.
"""
# ruff: noqa: F811 -- pytest resolves imported fixtures by their public names
import pytest

from tests.test_delivery_file_transfer import (  # noqa: F401
    RECEIVER,
    SENDER,
    custody_capacity,
    custody_rows,
    deliver,
    node_env,
    receiver_file_link,
    running_sender_run,
    sender_custody,
    transfer_rows,
)
from tests.test_delivery_public import linked  # noqa: F401
from tests.test_receiver_links import env  # noqa: F401
from tinyassets.daemon_server import (
    ensure_universe_registered,
    grant_universe_access,
    set_founder_home,
)
from tinyassets.storage import deliveries


def _roster(subject):
    from tinyassets.scoped_reset import TestIdentityRoster

    return TestIdentityRoster(
        revision="file-bridge-reset-v1",
        aliases={"subject": subject},
        allowlisted_subjects=frozenset({subject}),
    )


def _bind_home(base, owner):
    principal, universe_id = owner
    home = base / universe_id
    home.mkdir(exist_ok=True)
    (home / "soul.md").write_text(f"# {universe_id}\n", encoding="utf-8")
    ensure_universe_registered(base, universe_id=universe_id, universe_path=home)
    grant_universe_access(
        base, universe_id=universe_id, actor_id=principal,
        permission="admin", granted_by=principal,
    )
    set_founder_home(
        base, founder_sub=principal, universe_id=universe_id, platform_generated=True,
    )


def test_scoped_reset_refuses_while_delivery_file_custody_is_unerased(node_env):
    from tinyassets.scoped_reset import (
        ScopedResetBlocked,
        apply_test_identity_reset,
        plan_test_identity_reset,
    )

    base, auth, _, _, branch, _ = node_env
    _, link = receiver_file_link(base, auth)
    body = b"custody provenance a reset must not silently orphan"
    _, refs = sender_custody(base, [body])
    run_id = running_sender_run(base, branch, refs)
    receipt = deliver(base, branch, link, {"result": refs[0]}, run_id)
    transferred = transfer_rows(base, receipt["delivery_id"])
    assert len(transferred) == 1
    receiver_file = transferred[0]["receiver_file_id"]
    receiver_blob = base / ".run-file-custody" / (
        custody_rows(base, RECEIVER)[0]["storage_key"] + ".body"
    )
    assert receiver_blob.read_bytes() == body

    _bind_home(base, SENDER)
    subject = SENDER[0]

    from tinyassets.scoped_reset import inspect_reset_scope

    blockers = inspect_reset_scope(base, principal=subject).blockers
    assert any("graph_delivery_files" in blocker for blocker in blockers), blockers
    assert any(
        blocker.startswith("unclassified root run-history table")
        for blocker in blockers
    ), blockers

    plan = plan_test_identity_reset(base, alias="subject", roster=_roster(subject))
    with pytest.raises(ScopedResetBlocked):
        apply_test_identity_reset(
            base, alias="subject", roster=_roster(subject), plan_id=plan["plan_id"],
        )

    # Fail-closed, not fail-quiet: nothing about the transferred file moved.
    with deliveries.transaction(base) as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute(
            "SELECT COUNT(*) FROM graph_delivery_files WHERE receiver_file_id = ?",
            (receiver_file,),
        ).fetchone()[0] == 1
    assert transfer_rows(base, receipt["delivery_id"]) == transferred
    assert receiver_blob.read_bytes() == body
    assert [row["file_id"] for row in custody_rows(base, RECEIVER)] == [receiver_file]
