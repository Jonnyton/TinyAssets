"""Tests for the ``workspace`` effect sink (``tinyassets.effectors.workspace``).

Real connection ledger, real grant, real consent store, real pool database. The
worker is injected (no spawn, no git, no network) and the pool lane's directory
handles are injected too -- they land on ``claude/workspace-pool``, and a test
that asserts THEY were called is what makes the seam real before the merge.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tinyassets.effectors import EffectChain, WorkspaceMount
from tinyassets.effectors import workspace as wse
from tinyassets.effectors.workspace import (
    EXTERNAL_WRITE_SINK_WORKSPACE,
    WORKSPACE_READ_EFFECTS,
    run_workspace_effector,
)
from tinyassets.storage.outbound_connections import ConnectionLedger
from tinyassets.storage.workspace_authority import workspace_consent_destination

UNIVERSE = "universe-1"
REPO = "owner/name"
HOST = "github.com"
SHA = "c" * 40
TOKEN = "ghp_EFFECTORTOKEN0123456789ABCDEFGHI"


# --------------------------------------------------------------------------- #
# Scaffolding
# --------------------------------------------------------------------------- #


def _setup(
    tmp_path: Path,
    *,
    scopes=(f"git_read:{REPO}", f"git_write:{REPO}"),
    destination=f"github.com/{REPO}",
    endpoints=None,
    grant_universe=None,
    consents=("checkout", "push"),
) -> tuple[Path, Path]:
    """A universe with a git connection, a grant and the typed consents."""
    data_root = tmp_path / "data"
    universe_dir = data_root / UNIVERSE
    universe_dir.mkdir(parents=True)
    ledger = ConnectionLedger(
        data_root / "outbound.db", verify_authenticated_principal=lambda: "user-1"
    )
    ledger.create_connection(
        connection_id="conn-git",
        owner_user_id="user-1",
        connection_class="outbound-http",
        scopes=scopes,
        provider="http",
        destination=destination,
        credential_ref="vault://http/github",
        connection_type="http",
        auth_scheme="bearer",
        allowed_endpoints=endpoints
        or [{"host": HOST, "path_template": "/owner/name", "methods": ["GET"]}],
    )
    ledger.grant_connection(
        grant_id="grant-git",
        connection_id="conn-git",
        owner_user_id="user-1",
        universe_id=grant_universe or UNIVERSE,
    )
    from tinyassets.storage.effector_consents import grant_consent

    for op in consents:
        grant_consent(
            universe_dir,
            sink=EXTERNAL_WRITE_SINK_WORKSPACE,
            destination=workspace_consent_destination(
                f"workspace_{op}", REPO, connection_id="conn-git"
            ),
            granted_by="test",
        )
    return data_root, universe_dir


def _packet(**over: Any) -> dict[str, Any]:
    packet = {
        "sink": EXTERNAL_WRITE_SINK_WORKSPACE,
        "op": "checkout",
        "connection_id": "conn-git",
        "grant_id": "grant-git",
        "repo": REPO,
        "ref": "main",
        "storage": "scratch",
    }
    packet.update(over)
    return packet


class FakeWorker:
    """Stands in for the spawned worker. Records every request it was given."""

    def __init__(self, answer: dict[str, Any] | None = None, staging_holder: list | None = None):
        self.answer = answer if answer is not None else {
            "ok": True,
            "resolved_sha": SHA,
            "bytes": 4096,
            "bundle_name": "out.bundle",
            "ref_name": "refs/tiny/export",
        }
        self.requests: list[dict] = []
        self.staging_holder = staging_holder

    def __call__(self, request: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(request)
        # a real worker writes the bundle into the staging dir the parent made
        staging = Path(request["staging_dir"])
        if request["op"] == "checkout" and self.answer.get("ok"):
            (staging / str(self.answer.get("bundle_name") or "out.bundle")).write_bytes(b"PACK")
        return self.answer


@pytest.fixture()
def fs_spy(monkeypatch: pytest.MonkeyPatch):
    """Inject the pool lane's directory-handle helpers.

    They are unmerged (``claude/workspace-pool``); the adapter imports them
    lazily and this is the seam. Asserting THESE were called is what proves the
    lease directory is created under a no-follow handle rather than with mkdir.
    """
    from tinyassets import workspace_fs

    calls: dict[str, list] = {"open_dir_nofollow": [], "create_lease_dir": [], "copy": []}

    def open_dir_nofollow(path):
        calls["open_dir_nofollow"].append(str(path))
        Path(path).mkdir(parents=True, exist_ok=True)
        return f"fd:{path}"

    def create_lease_dir(parent_fd, name):
        calls["create_lease_dir"].append((parent_fd, name))
        parent = str(parent_fd).removeprefix("fd:")
        (Path(parent) / name).mkdir(parents=True, exist_ok=True)
        return f"fd:{parent}/{name}"

    def copy_regular_file_beneath(dir_fd, relpath, dest_path, *, max_bytes):
        calls["copy"].append((dir_fd, relpath, str(dest_path), max_bytes))
        source = Path(str(dir_fd).removeprefix("fd:")) / relpath
        if not source.is_file():
            raise FileNotFoundError(relpath)
        data = source.read_bytes()
        if len(data) > max_bytes:
            raise ValueError("bundle exceeds max_bytes")
        Path(dest_path).write_bytes(data)
        return len(data)

    monkeypatch.setattr(workspace_fs, "open_dir_nofollow", open_dir_nofollow, raising=False)
    monkeypatch.setattr(workspace_fs, "create_lease_dir", create_lease_dir, raising=False)
    monkeypatch.setattr(
        workspace_fs, "copy_regular_file_beneath", copy_regular_file_beneath, raising=False
    )
    return calls


@pytest.fixture()
def no_real_git(monkeypatch: pytest.MonkeyPatch):
    """The host-side population is workspace_git's job and is tested there."""
    populated: list[tuple] = []

    def populate(bundle, dest, ref_name, checkout_ref, *, home_dir, path, **kwargs):
        populated.append((str(bundle), str(dest), ref_name, checkout_ref))
        Path(dest).mkdir(parents=True, exist_ok=True)
        (Path(dest) / ".git").mkdir(exist_ok=True)
        return SHA

    monkeypatch.setattr(wse, "_git_path", lambda: "/usr/bin")
    import tinyassets.workspace_git as wg

    monkeypatch.setattr(wg, "populate_workspace_from_bundle", populate)
    return populated


def _run(
    tmp_path: Path,
    packet: dict[str, Any],
    *,
    universe_dir: Path,
    chain: EffectChain,
    worker: FakeWorker | None = None,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    return run_workspace_effector(
        node_id="n1",
        output_keys=["ws"],
        run_state={"ws": packet},
        base_path=universe_dir,
        run_id="run-1",
        dry_run=dry_run,
        chain=chain,
        execute=worker or FakeWorker(),
    )


@pytest.fixture()
def chain(tmp_path: Path) -> EffectChain:
    return EffectChain(run_id="run-1", base_path=str(tmp_path), universe_id=UNIVERSE)


# --------------------------------------------------------------------------- #
# Packet parsing
# --------------------------------------------------------------------------- #


def test_a_node_without_a_workspace_packet_is_no_matching_packet(
    tmp_path: Path, chain: EffectChain
) -> None:
    _root, universe_dir = _setup(tmp_path)
    result = run_workspace_effector(
        node_id="n1",
        output_keys=["ws"],
        run_state={"ws": {"sink": "authenticated_external_call"}},
        base_path=universe_dir,
        run_id="run-1",
        chain=chain,
        execute=FakeWorker(),
    )
    assert result["error_kind"] == "no_matching_packet"


def test_a_json_string_packet_parses(tmp_path: Path, chain: EffectChain, fs_spy, no_real_git):
    _root, universe_dir = _setup(tmp_path)
    result = _run(tmp_path, json.dumps(_packet()), universe_dir=universe_dir, chain=chain)
    assert result.get("error_kind") is None, result
    assert result["op"] == "checkout"


@pytest.mark.parametrize("op", ["", "clone", "fetch", "CHECKOUT"])
def test_an_unknown_op_is_an_invalid_packet(
    tmp_path: Path, chain: EffectChain, op: str
) -> None:
    _root, universe_dir = _setup(tmp_path)
    result = _run(tmp_path, _packet(op=op), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "invalid_packet"


@pytest.mark.parametrize(
    "repo",
    ["", "name", "owner/name/extra", "/owner/name", "owner/", "../name", "owner/na me"],
)
def test_a_malformed_repo_is_refused(tmp_path: Path, chain: EffectChain, repo: str) -> None:
    _root, universe_dir = _setup(tmp_path)
    result = _run(tmp_path, _packet(repo=repo), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "invalid_packet"


@pytest.mark.parametrize("missing", ["connection_id", "grant_id"])
def test_a_packet_without_its_authority_fields_is_refused(
    tmp_path: Path, chain: EffectChain, missing: str
) -> None:
    _root, universe_dir = _setup(tmp_path)
    packet = _packet()
    packet.pop(missing)
    result = _run(tmp_path, packet, universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "invalid_packet"


def test_an_unknown_storage_class_is_refused(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    _root, universe_dir = _setup(tmp_path)
    result = _run(tmp_path, _packet(storage="permanent"), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "invalid_packet"


def test_no_universe_authority_is_refused(tmp_path: Path, chain: EffectChain) -> None:
    result = run_workspace_effector(
        node_id="n1",
        output_keys=["ws"],
        run_state={"ws": _packet()},
        base_path=None,
        run_id="run-1",
        chain=chain,
        execute=FakeWorker(),
    )
    assert result["error_kind"] == "no_universe_authority"


# --------------------------------------------------------------------------- #
# Authority: grant, scope, consent
# --------------------------------------------------------------------------- #


def test_a_grant_from_another_universe_is_refused(tmp_path: Path, chain: EffectChain) -> None:
    _root, universe_dir = _setup(tmp_path, grant_universe="universe-2")
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "grant_not_for_universe"


def test_an_unknown_grant_is_refused(tmp_path: Path, chain: EffectChain) -> None:
    _root, universe_dir = _setup(tmp_path)
    result = _run(tmp_path, _packet(grant_id="nope"), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "unknown_grant"


def test_a_checkout_needs_the_git_read_scope(tmp_path: Path, chain: EffectChain) -> None:
    _root, universe_dir = _setup(tmp_path, scopes=(f"git_write:{REPO}",))
    result = _run(tmp_path, _packet(op="checkout"), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "scope_not_granted"


def test_a_push_needs_the_git_write_scope(tmp_path: Path, chain: EffectChain) -> None:
    _root, universe_dir = _setup(tmp_path, scopes=(f"git_read:{REPO}",))
    result = _run(
        tmp_path,
        _packet(op="push", commit_sha=SHA, branch_slug="slug", workspace="n0"),
        universe_dir=universe_dir,
        chain=chain,
    )
    assert result["error_kind"] == "scope_not_granted"


def test_a_scope_bound_to_another_repository_cannot_be_borrowed(
    tmp_path: Path, chain: EffectChain
) -> None:
    """The binding lives in the SCOPE (``git_read:owner/name``), not in the
    connection's destination string: a scope for one repo is not a scope for
    its neighbour, and a prefix is not a match."""
    _root, universe_dir = _setup(
        tmp_path, scopes=("git_read:someone/else", "git_write:someone/else")
    )
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "scope_not_granted"


def test_a_scope_for_a_repo_whose_name_extends_this_one_is_not_a_match(
    tmp_path: Path, chain: EffectChain
) -> None:
    _root, universe_dir = _setup(tmp_path, scopes=(f"git_read:{REPO}-evil",))
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "scope_not_granted"


def test_a_git_scope_on_a_non_github_connection_is_refused_at_creation(
    tmp_path: Path,
) -> None:
    """The host check moved EARLIER than the sink: a connection carrying a git
    scope whose endpoints are not github cannot be created at all, so the sink
    never has to refuse one."""
    from tinyassets.storage.workspace_authority import GitScopeError

    with pytest.raises((GitScopeError, ValueError)):
        _setup(
            tmp_path,
            endpoints=[{"host": "gitlab.example", "path_template": "/x", "methods": ["GET"]}],
        )


def test_a_checkout_without_its_consent_is_refused(tmp_path: Path, chain: EffectChain) -> None:
    _root, universe_dir = _setup(tmp_path, consents=("push",))
    result = _run(tmp_path, _packet(op="checkout"), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "missing_consent"
    assert result["consent"] == "workspace_checkout"


def test_a_push_without_its_consent_is_refused(tmp_path: Path, chain: EffectChain) -> None:
    _root, universe_dir = _setup(tmp_path, consents=("checkout",))
    result = _run(
        tmp_path,
        _packet(op="push", commit_sha=SHA, branch_slug="slug", workspace="n0"),
        universe_dir=universe_dir,
        chain=chain,
    )
    assert result["error_kind"] == "missing_consent"
    assert result["consent"] == "workspace_push"


def test_a_checkout_consent_does_not_authorize_a_push(
    tmp_path: Path, chain: EffectChain
) -> None:
    """The consents are typed per op: one is never the other."""
    _root, universe_dir = _setup(tmp_path, consents=("checkout",))
    checkout_dest = workspace_consent_destination(
        "workspace_checkout", REPO, connection_id="conn-git"
    )
    push_dest = workspace_consent_destination(
        "workspace_push", REPO, connection_id="conn-git"
    )
    assert checkout_dest != push_dest
    from tinyassets.storage.effector_consents import is_consent_active

    assert is_consent_active(
        universe_dir, sink=EXTERNAL_WRITE_SINK_WORKSPACE, destination=checkout_dest
    )
    assert not is_consent_active(
        universe_dir, sink=EXTERNAL_WRITE_SINK_WORKSPACE, destination=push_dest
    )


def test_a_consent_for_another_repository_does_not_authorize_this_one(
    tmp_path: Path, chain: EffectChain
) -> None:
    _root, universe_dir = _setup(tmp_path, consents=())
    from tinyassets.storage.effector_consents import grant_consent

    grant_consent(
        universe_dir,
        sink=EXTERNAL_WRITE_SINK_WORKSPACE,
        destination=workspace_consent_destination(
            "workspace_checkout", "someone/else", connection_id="conn-git"
        ),
        granted_by="test",
    )
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "missing_consent"


def test_no_gate_runs_the_worker(tmp_path: Path, chain: EffectChain) -> None:
    """Every refusal above must happen BEFORE the worker is ever spawned."""
    _root, universe_dir = _setup(tmp_path, consents=())
    worker = FakeWorker()
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain, worker=worker)
    assert result["error_kind"] == "missing_consent"
    assert worker.requests == []


# --------------------------------------------------------------------------- #
# checkout
# --------------------------------------------------------------------------- #


def test_a_checkout_admits_populates_and_registers_the_mount(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    _root, universe_dir = _setup(tmp_path)
    worker = FakeWorker()
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain, worker=worker)
    assert result["op"] == "checkout"
    assert result["repo"] == REPO
    assert result["resolved_sha"] == SHA
    assert result["bytes"] == 4096
    assert result["storage"] == "scratch"
    assert "lease_generation" in result
    mount = chain.workspace_mount("n1")
    assert mount is not None
    assert mount.bind_source.endswith("repo")


def test_the_startup_barrier_runs_before_the_pool_admits(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An entry an earlier process left must be finished before a new job is
    admitted, even when this run is the first thing to touch the runs DB."""
    from tinyassets import runs as _runs
    from tinyassets import workspace_pool

    order: list[str] = []
    real_reconcile = _runs.ensure_workspace_reconciled
    real_admit = workspace_pool.admit

    def spy_reconcile(base_path, **kwargs):
        order.append("reconcile")
        return real_reconcile(base_path, start_sweeper=False)

    def spy_admit(*args, **kwargs):
        order.append("admit")
        return real_admit(*args, **kwargs)

    monkeypatch.setattr(_runs, "ensure_workspace_reconciled", spy_reconcile)
    monkeypatch.setattr(workspace_pool, "admit", spy_admit)
    _root, universe_dir = _setup(tmp_path)
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert result.get("error_kind") is None, result
    assert order[:2] == ["reconcile", "admit"], order


def test_the_lease_directory_is_created_through_the_no_follow_handles(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    """Not ``mkdir``: a symlinked parent would otherwise place the lease
    somewhere the pool never admitted."""
    _root, universe_dir = _setup(tmp_path)
    _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert fs_spy["open_dir_nofollow"], "the lease parent was not opened no-follow"
    assert fs_spy["create_lease_dir"], "the lease dir was not created through the handle"


def test_the_worker_request_carries_a_reference_never_a_secret(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    _root, universe_dir = _setup(tmp_path)
    worker = FakeWorker()
    _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain, worker=worker)
    request = worker.requests[0]
    assert request["credential_ref"] == "vault://http/github"
    assert TOKEN not in json.dumps(request)
    assert request["op"] == "checkout"
    assert request["owner_repo"] == REPO
    assert request["host"] == HOST
    assert Path(request["staging_dir"]).is_dir()


def test_the_staging_dir_is_never_inside_the_lease(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    _root, universe_dir = _setup(tmp_path)
    worker = FakeWorker()
    _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain, worker=worker)
    staging = Path(worker.requests[0]["staging_dir"])
    mount = chain.workspace_mount("n1")
    assert not str(staging).startswith(str(Path(mount.bind_source).parent))


def test_a_failed_checkout_is_workspace_checkout_failed(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    _root, universe_dir = _setup(tmp_path)
    worker = FakeWorker({"ok": False, "error": "auth: nope", "stderr_class": "auth"})
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain, worker=worker)
    assert result["error_kind"] == "workspace_checkout_failed"
    assert result["stderr_class"] == "auth"
    assert chain.workspace_mount_or_none("n1") is None


def test_a_universe_checkout_publishes_a_generation(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    _root, universe_dir = _setup(tmp_path)
    first = _run(tmp_path, _packet(storage="universe"), universe_dir=universe_dir, chain=chain)
    assert first["storage"] == "universe"
    assert first.get("replaced_generation") is None

    # Same run: the universe job lock is held until the outbox processor
    # releases it, and D4 makes it reentrant for the run that holds it.
    second = run_workspace_effector(
        node_id="n2",
        output_keys=["ws"],
        run_state={"ws": _packet(storage="universe")},
        base_path=universe_dir,
        run_id="run-1",
        chain=chain,
        execute=FakeWorker(),
    )
    assert second.get("error_kind") is None, second
    assert second["replaced_generation"] == first["lease_generation"]

    # and the replaced generation is OWED a discard, not deleted inline
    from tinyassets import workspace_pool

    db = workspace_pool_db(universe_dir)
    entries = _outbox_rows(db)
    assert any(
        row["action"] == "discard_permanent_generation"
        and row["generation"] == first["lease_generation"]
        for row in entries
    ), entries
    del workspace_pool


def workspace_pool_db(universe_dir: Path) -> Path:
    from tinyassets import runs

    return runs.runs_db_path(universe_dir)


def _outbox_rows(db: Path) -> list[dict]:
    import sqlite3

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM workspace_outbox").fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def test_a_lock_held_by_another_run_is_workspace_busy_not_a_quota_error(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    """The pool's own refusal code is the answer, never a re-translation.

    A held lock reported as ``workspace_quota_exceeded`` tells the universe to
    wait for an hour when the truth is "another run is using it right now".
    """
    _root, universe_dir = _setup(tmp_path)
    first = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert first.get("error_kind") is None, first

    other_chain = EffectChain(run_id="run-2", base_path=str(tmp_path), universe_id=UNIVERSE)
    second = run_workspace_effector(
        node_id="n2",
        output_keys=["ws"],
        run_state={"ws": _packet()},
        base_path=universe_dir,
        run_id="run-2",
        chain=other_chain,
        execute=FakeWorker(),
    )
    assert second["error_kind"] == "workspace_busy"


def test_a_busy_pool_is_swept_once_then_retried_once(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lock still recorded against a FINISHED run is owed to the outbox, not
    in use. One sweep, one retry -- never a loop."""
    from tinyassets import runs as _runs
    from tinyassets import workspace_pool
    from tinyassets.workspace_pool import WorkspacePoolRefused

    _root, universe_dir = _setup(tmp_path)
    real_admit = workspace_pool.admit
    calls: list[str] = []

    def flaky_admit(*args, **kwargs):
        calls.append("admit")
        if len(calls) == 1:
            raise WorkspacePoolRefused("workspace_busy", "held by a finished run")
        return real_admit(*args, **kwargs)

    swept: list[str] = []
    monkeypatch.setattr(workspace_pool, "admit", flaky_admit)
    monkeypatch.setattr(
        _runs, "_workspace_sweep_once",
        lambda base, *, claimant: swept.append(claimant) or 1,
    )
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert result.get("error_kind") is None, result
    assert calls == ["admit", "admit"], "exactly one retry"
    assert swept == ["adapter:run-1"], swept


def test_the_retry_happens_at_most_once(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pool that is genuinely busy must refuse, not stall in a sweep loop."""
    from tinyassets import runs as _runs
    from tinyassets import workspace_pool
    from tinyassets.workspace_pool import WorkspacePoolRefused

    _root, universe_dir = _setup(tmp_path)
    calls: list[str] = []
    swept: list[str] = []

    def always_busy(*args, **kwargs):
        calls.append("admit")
        raise WorkspacePoolRefused("workspace_busy", "really held")

    monkeypatch.setattr(workspace_pool, "admit", always_busy)
    monkeypatch.setattr(
        _runs, "_workspace_sweep_once",
        lambda base, *, claimant: swept.append(claimant) or 0,
    )
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "workspace_busy"
    assert calls == ["admit", "admit"], "one retry and no more"
    assert len(swept) == 1


def test_a_quota_refusal_is_not_swept(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cleanup does not create quota. Sweeping here would fail twice for nothing."""
    from tinyassets import runs as _runs
    from tinyassets import workspace_pool
    from tinyassets.workspace_pool import WorkspacePoolRefused

    _root, universe_dir = _setup(tmp_path)
    calls: list[str] = []
    swept: list[str] = []

    def over_quota(*args, **kwargs):
        calls.append("admit")
        raise WorkspacePoolRefused("workspace_quota_exceeded", "hourly bytes exhausted")

    monkeypatch.setattr(workspace_pool, "admit", over_quota)
    monkeypatch.setattr(
        _runs, "_workspace_sweep_once",
        lambda base, *, claimant: swept.append(claimant) or 0,
    )
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "workspace_quota_exceeded"
    assert calls == ["admit"], "no retry for a quota refusal"
    assert swept == []


def test_a_sweep_that_itself_fails_reports_the_original_refusal(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tinyassets import runs as _runs
    from tinyassets import workspace_pool
    from tinyassets.workspace_pool import WorkspacePoolRefused

    _root, universe_dir = _setup(tmp_path)

    def busy(*args, **kwargs):
        raise WorkspacePoolRefused("workspace_pool_busy", "pool full")

    def broken_sweep(base, *, claimant):
        raise OSError("the runs db is locked")

    monkeypatch.setattr(workspace_pool, "admit", busy)
    monkeypatch.setattr(_runs, "_workspace_sweep_once", broken_sweep)
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "workspace_pool_busy"


@pytest.mark.parametrize(
    "code,expected",
    [
        ("workspace_busy", "workspace_busy"),
        ("workspace_pool_busy", "workspace_pool_busy"),
        ("workspace_quota_exceeded", "workspace_quota_exceeded"),
        ("something_new", "workspace_checkout_failed"),
        ("", "workspace_checkout_failed"),
    ],
)
def test_every_pool_refusal_keeps_its_own_kind(code: str, expected: str) -> None:
    from tinyassets.workspace_pool import WorkspacePoolRefused

    assert wse._pool_error_kind(WorkspacePoolRefused(code, "detail")) == expected


def test_the_adapter_uses_the_pool_module_s_own_constants() -> None:
    """If the pool renames a code, this test fails rather than the mapping
    silently falling through to workspace_checkout_failed."""
    from tinyassets import workspace_pool

    assert wse._POOL_KINDS == {
        workspace_pool.REFUSED_BUSY,
        workspace_pool.REFUSED_POOL_BUSY,
        workspace_pool.REFUSED_QUOTA,
    }


def test_provisioning_without_its_consent_does_not_fail_the_checkout(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    """The spec scenario: the checkout completes, provisioning is refused."""
    _root, universe_dir = _setup(tmp_path)
    result = _run(
        tmp_path,
        _packet(provision={"python": ["x==1.0"]}),
        universe_dir=universe_dir,
        chain=chain,
    )
    assert result.get("error_kind") is None, result
    assert result["op"] == "checkout"
    assert result["provision"] == "workspace_provision_refused"


# --------------------------------------------------------------------------- #
# push and discard
# --------------------------------------------------------------------------- #


def _with_mount(chain: EffectChain, tmp_path: Path, *, node_id: str = "n0") -> Path:
    lease_dir = tmp_path / "lease"
    (lease_dir / "repo" / ".tiny-export").mkdir(parents=True)
    (lease_dir / "repo" / ".tiny-export" / f"{SHA}.bundle").write_bytes(b"PACK-export")

    class FakeLease:
        lease_id = "lease-1"
        storage_class = "scratch"
        repo_key = "github.com--owner--name"
        generation = 1
        path = lease_dir

    chain.register_workspace(
        node_id,
        WorkspaceMount(
            node_id=node_id,
            bind_source=str(lease_dir / "repo"),
            lease_fd=f"fd:{lease_dir}",
            lease=FakeLease(),
            storage_class="scratch",
            repo_key="github.com--owner--name",
            generation=1,
        ),
    )
    return lease_dir


def test_a_push_copies_the_bundle_through_the_lease_handle_and_names_the_branch(
    tmp_path: Path, chain: EffectChain, fs_spy
) -> None:
    _root, universe_dir = _setup(tmp_path)
    _with_mount(chain, tmp_path)
    worker = FakeWorker({"ok": True, "bytes": 11, "resolved_sha": SHA})
    result = _run(
        tmp_path,
        _packet(op="push", commit_sha=SHA, branch_slug="my-slug", workspace="n0"),
        universe_dir=universe_dir,
        chain=chain,
        worker=worker,
    )
    assert result["op"] == "push"
    assert result["remote_ref"].startswith("refs/heads/tiny/")
    assert result["remote_ref"].endswith("/my-slug")
    assert fs_spy["copy"], "the bundle was not read through the lease handle"
    dir_fd, relpath, _dest, max_bytes = fs_spy["copy"][0]
    assert relpath == f"repo/.tiny-export/{SHA}.bundle"
    assert max_bytes == 512 * 1024 * 1024
    assert worker.requests[0]["op"] == "push"
    assert worker.requests[0]["commit_sha"] == SHA


def test_a_push_naming_a_workspace_this_run_does_not_hold_is_refused(
    tmp_path: Path, chain: EffectChain
) -> None:
    _root, universe_dir = _setup(tmp_path)
    result = _run(
        tmp_path,
        _packet(op="push", commit_sha=SHA, branch_slug="slug", workspace="nowhere"),
        universe_dir=universe_dir,
        chain=chain,
    )
    assert result["error_kind"] == "no_matching_packet"


@pytest.mark.parametrize("slug", ["", "a/b", "-evil", "with space"])
def test_a_bad_branch_slug_is_refused(
    tmp_path: Path, chain: EffectChain, slug: str
) -> None:
    _root, universe_dir = _setup(tmp_path)
    _with_mount(chain, tmp_path)
    result = _run(
        tmp_path,
        _packet(op="push", commit_sha=SHA, branch_slug=slug, workspace="n0"),
        universe_dir=universe_dir,
        chain=chain,
    )
    assert result["error_kind"] == "invalid_packet"


def test_a_refused_push_reports_the_observed_ref(
    tmp_path: Path, chain: EffectChain, fs_spy
) -> None:
    _root, universe_dir = _setup(tmp_path)
    _with_mount(chain, tmp_path)
    worker = FakeWorker(
        {
            "ok": False,
            "error": "the push outcome was lost",
            "stderr_class": "non_fast_forward",
            "observed_sha": "d" * 40,
        }
    )
    result = _run(
        tmp_path,
        _packet(op="push", commit_sha=SHA, branch_slug="slug", workspace="n0"),
        universe_dir=universe_dir,
        chain=chain,
        worker=worker,
    )
    assert result["error_kind"] == "workspace_push_refused"
    assert result["observed_sha"] == "d" * 40


def test_a_discard_revokes_the_capability_then_owes_the_bytes(
    tmp_path: Path, chain: EffectChain
) -> None:
    _root, universe_dir = _setup(tmp_path)
    _with_mount(chain, tmp_path)
    assert chain.workspace_mount("n0") is not None
    result = _run(
        tmp_path,
        _packet(op="discard", workspace="n0"),
        universe_dir=universe_dir,
        chain=chain,
    )
    assert result["op"] == "discard"
    assert chain.workspace_mount_or_none("n0") is None, "the capability must be gone"
    rows = _outbox_rows(workspace_pool_db(universe_dir))
    assert any(row["action"] == "wipe_scratch" for row in rows), rows


# --------------------------------------------------------------------------- #
# dry run, classification, registry
# --------------------------------------------------------------------------- #


def test_dry_run_describes_and_spawns_nothing(
    tmp_path: Path, chain: EffectChain, fs_spy
) -> None:
    _root, universe_dir = _setup(tmp_path)
    worker = FakeWorker()
    result = _run(
        tmp_path, _packet(), universe_dir=universe_dir, chain=chain, worker=worker, dry_run=True
    )
    assert result["dry_run"] is True
    assert result["op"] == "checkout"
    assert worker.requests == []
    assert fs_spy["create_lease_dir"] == []
    assert chain.workspace_mount_or_none("n1") is None


def test_dry_run_still_reports_a_refusal_a_live_run_would_hit(
    tmp_path: Path, chain: EffectChain
) -> None:
    _root, universe_dir = _setup(tmp_path, consents=())
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain, dry_run=True)
    assert result["error_kind"] == "missing_consent"


def test_the_adapter_binds_to_the_real_filesystem_helpers_by_name() -> None:
    """The names are the contract with the pool lane.

    The adapter imports them lazily and the Windows suite injects them, so a
    rename over there would otherwise surface as a runtime AttributeError on
    Linux only. These assertions fail HERE instead.
    """
    from tinyassets import workspace_fs

    for name in (
        "open_dir_nofollow",
        "create_lease_dir",
        "read_regular_file_beneath",
        "copy_regular_file_beneath",
        "bind_target_for",
    ):
        assert callable(getattr(workspace_fs, name, None)), f"workspace_fs.{name} is gone"
    assert issubclass(workspace_fs.UnsafePoolPath, OSError)


def test_the_real_helpers_refuse_loudly_on_windows_rather_than_imitating() -> None:
    """A path-based Windows fallback would fake a descriptor guarantee."""
    from tinyassets import workspace_fs

    if os.name == "posix":
        pytest.skip("POSIX has the real openat semantics")
    with pytest.raises(NotImplementedError):
        workspace_fs.open_dir_nofollow(".")


def test_a_checkout_without_the_posix_helpers_fails_as_a_workspace_refusal(
    tmp_path: Path, chain: EffectChain, no_real_git
) -> None:
    """No fs_spy here: on Windows the real helpers raise, and the adapter must
    turn that into an actionable kind rather than an unhandled crash."""
    if os.name == "posix":
        pytest.skip("the real helpers work here; the Linux proof covers it")
    _root, universe_dir = _setup(tmp_path)
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] in ("workspace_checkout_failed", "effector_crashed")
    assert chain.workspace_mount_or_none("n1") is None


def test_the_sink_is_registered_and_exported() -> None:
    from tinyassets import effectors

    assert effectors._EFFECTORS[EXTERNAL_WRITE_SINK_WORKSPACE] is not None
    assert "EXTERNAL_WRITE_SINK_WORKSPACE" in effectors.__all__
    assert EXTERNAL_WRITE_SINK_WORKSPACE == "workspace"


def test_a_fired_checkout_settles_as_a_read() -> None:
    from tinyassets.engine_admissions import fired_only_reads

    assert fired_only_reads(
        [(EXTERNAL_WRITE_SINK_WORKSPACE, "checkout")],
        read_sink="authenticated_external_call",
        read_effects=WORKSPACE_READ_EFFECTS,
    )
    assert fired_only_reads(
        [(EXTERNAL_WRITE_SINK_WORKSPACE, "discard")],
        read_sink="authenticated_external_call",
        read_effects=WORKSPACE_READ_EFFECTS,
    )


def test_a_fired_push_settles_as_a_write() -> None:
    from tinyassets.engine_admissions import fired_only_reads

    assert not fired_only_reads(
        [(EXTERNAL_WRITE_SINK_WORKSPACE, "push")],
        read_sink="authenticated_external_call",
        read_effects=WORKSPACE_READ_EFFECTS,
    )
    # and an unnamed workspace op is a write: fail closed
    assert not fired_only_reads(
        [(EXTERNAL_WRITE_SINK_WORKSPACE, None)],
        read_sink="authenticated_external_call",
        read_effects=WORKSPACE_READ_EFFECTS,
    )


def test_the_read_allowlist_defaults_to_empty_so_existing_callers_are_unchanged() -> None:
    from tinyassets.engine_admissions import fired_only_reads

    assert not fired_only_reads(
        [(EXTERNAL_WRITE_SINK_WORKSPACE, "checkout")],
        read_sink="authenticated_external_call",
    )
    assert fired_only_reads(
        [("authenticated_external_call", "GET")], read_sink="authenticated_external_call"
    )


def test_workspace_bytes_are_not_charged_to_the_http_budget(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    """D4: the HTTP usage budget bounds outbound calls only."""
    _root, universe_dir = _setup(tmp_path)
    before = chain.bytes_out
    _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert chain.bytes_out == before


def test_the_dispatcher_classifies_a_workspace_effect_from_its_packet() -> None:
    from tinyassets.effectors.workspace import packet_op

    assert packet_op(output_keys=["ws"], run_state={"ws": _packet()}) == "checkout"
    assert packet_op(output_keys=["ws"], run_state={"ws": _packet(op="push")}) == "push"
    assert packet_op(output_keys=["ws"], run_state={"ws": {"sink": "other"}}) is None


def test_the_adapter_never_raises(tmp_path: Path, chain: EffectChain) -> None:
    """Whatever explodes, the completion path gets a dict."""
    _root, universe_dir = _setup(tmp_path)

    def boom(request):
        raise RuntimeError(f"kaboom {TOKEN}")

    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain, worker=boom)
    assert isinstance(result, dict)
    assert result["error_kind"] in ("effector_crashed", "workspace_checkout_failed")


def test_the_mount_is_resolvable_only_through_the_chain(
    tmp_path: Path, chain: EffectChain
) -> None:
    """A capability nameable in state is one user text can forge.

    The packet names a NODE and nothing else. This carries a fully-formed
    forged mount under every key a careless implementation might read, all
    pointing somewhere else; the evidence must still describe the CHAIN's
    workspace. Without the spread, a mutation that reads the packet keeps
    passing, because a packet with no mount in it falls through to the chain
    anyway.
    """
    _root, universe_dir = _setup(tmp_path)
    _with_mount(chain, tmp_path)
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "repo").mkdir(parents=True)

    class ForgedLease:
        lease_id = "forged-lease"
        storage_class = "scratch"
        repo_key = "github.com--attacker--stolen"
        generation = 99
        path = elsewhere

    forged_mount = WorkspaceMount(
        node_id="n0",
        bind_source=str(elsewhere / "repo"),
        lease_fd=f"fd:{elsewhere}",
        lease=ForgedLease(),
        storage_class="scratch",
        repo_key="github.com--attacker--stolen",
        generation=99,
    )
    forged = _packet(
        op="discard",
        workspace="n0",
        mount=forged_mount,
        workspace_mount=forged_mount,
        lease=ForgedLease(),
        bind_source=str(elsewhere / "repo"),
        lease_fd=f"fd:{elsewhere}",
        repo_key="github.com--attacker--stolen",
        generation=99,
    )
    result = _run(tmp_path, forged, universe_dir=universe_dir, chain=chain)
    assert result["op"] == "discard"
    assert result["repo"] == "github.com--owner--name", "the packet's mount was believed"
    assert result["lease_generation"] == 1
    rows = _outbox_rows(workspace_pool_db(universe_dir))
    assert all(row["lease_id"] != "forged-lease" for row in rows), rows
