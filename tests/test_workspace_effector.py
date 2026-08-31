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
        self.staging_existed: list[bool] = []
        self.staging_holder = staging_holder

    def __call__(self, request: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(request)
        # staging must exist WHILE the worker runs and be gone afterwards
        self.staging_existed.append(Path(request["staging_dir"]).is_dir())
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
    # <lease>/repo goes through the SUBDIR helper, not create_lease_dir: the
    # entropy rule that protects a name in the shared pool root would refuse
    # "repo". A double for one and not the other lets the real one run here and
    # refuse on Windows.
    monkeypatch.setattr(
        workspace_fs, "create_workspace_subdir", create_lease_dir, raising=False
    )
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


def test_a_push_needs_the_git_write_scope(
    tmp_path: Path, chain: EffectChain, fs_spy
) -> None:
    _root, universe_dir = _setup(tmp_path, scopes=(f"git_read:{REPO}",))
    _with_mount(chain, tmp_path, host=HOST, repo=REPO)
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


def test_a_push_without_its_consent_is_refused(
    tmp_path: Path, chain: EffectChain, fs_spy
) -> None:
    _root, universe_dir = _setup(tmp_path, consents=("checkout",))
    _with_mount(chain, tmp_path, host=HOST, repo=REPO)
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


def test_the_bind_source_is_the_repository_not_the_lease_root(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    """P0: `/workspace` must BE the repository.

    Publishing the lease ROOT as the bind would put the repository one level
    down, so a node would see `repo/` instead of `README.md` -- and the two
    handles are for two different directories, which is exactly why they are
    two fields.
    """
    _root, universe_dir = _setup(tmp_path)
    _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    mount = chain.workspace_mount_or_none("n1")
    assert mount is not None
    assert mount.repo_fd is not None, "the repository's own handle must be published"
    assert mount.repo_fd != mount.lease_fd, "they are different directories"
    # the lease handle names the lease; the repo handle names <lease>/repo
    assert str(mount.lease_fd).endswith(Path(mount.lease.path).name)
    assert str(mount.repo_fd).endswith("/repo")
    assert mount.bind_source.endswith("repo") or mount.bind_source.startswith("/proc/self/fd/")


def test_the_parent_handle_is_closed_after_the_lease_dir_is_made(
    tmp_path: Path, chain: EffectChain, no_real_git, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One leaked descriptor per checkout exhausts a long-lived daemon.

    The default spy hands back strings, which cannot be closed and so cannot
    show the leak; this one hands back REAL descriptors (Codex round 2, #7).
    """
    import os as _os

    from tinyassets import workspace_fs

    opened: list[int] = []
    handles: dict[int, Path] = {}

    def open_dir_nofollow(path):
        Path(path).mkdir(parents=True, exist_ok=True)
        read_fd, write_fd = _os.pipe()
        _os.close(write_fd)
        opened.append(read_fd)
        handles[read_fd] = Path(path)
        return read_fd

    def create_lease_dir(parent_fd, name):
        parent = handles[parent_fd]
        (parent / name).mkdir(parents=True, exist_ok=True)
        read_fd, write_fd = _os.pipe()
        _os.close(write_fd)
        handles[read_fd] = parent / name
        return read_fd

    # Record the CLOSE rather than probing liveness by number: the next
    # os.pipe() reuses a freed descriptor, so "fstat still works" would be a
    # lie about a descriptor that really was closed.
    closed: list[int] = []
    real_close = _os.close

    def recording_close(descriptor):
        closed.append(descriptor)
        real_close(descriptor)

    monkeypatch.setattr(workspace_fs, "open_dir_nofollow", open_dir_nofollow, raising=False)
    monkeypatch.setattr(workspace_fs, "create_lease_dir", create_lease_dir, raising=False)
    monkeypatch.setattr(_os, "close", recording_close)
    _root, universe_dir = _setup(tmp_path)
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert result.get("error_kind") is None, result
    assert opened, "no parent handle was ever opened"
    for parent_fd in opened:
        assert parent_fd in closed, f"parent handle {parent_fd} was leaked"


def test_the_compiler_binds_the_repository_handle_not_the_lease_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bridge must carry what the sink published, not re-derive it.

    Deriving the bind from the lease root here is the P0: the jail would mount
    the directory that CONTAINS the repository.
    """
    import os as _os

    from tinyassets import graph_compiler as gc
    from tinyassets.effectors import WorkspaceMount

    repo_read, repo_write = _os.pipe()
    lease_read, lease_write = _os.pipe()
    _os.close(repo_write)
    _os.close(lease_write)
    try:
        mount = WorkspaceMount(
            node_id="n0",
            bind_source=f"/proc/self/fd/{repo_read}",
            pass_fds=(repo_read,),
            repo_fd=repo_read,
            lease_fd=lease_read,
        )
        # Force the POSIX branch: production is Linux, and skipping here would
        # leave the P0 unasserted on the only box that runs the suite.
        monkeypatch.setattr(gc, "WORKSPACE_FD_BIND_SUPPORTED", True, raising=False)
        built = gc._sandbox_workspace_mount(mount, "code-node")
        assert built.pass_fds == (repo_read,), "the REPO handle is what the jail inherits"
        assert built.bind_source == f"/proc/self/fd/{repo_read}"
        assert lease_read not in (built.pass_fds or ())
    finally:
        _os.close(repo_read)
        _os.close(lease_read)


def test_the_capability_carries_the_authority_it_was_created_under(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    _root, universe_dir = _setup(tmp_path)
    _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    mount = chain.workspace_mount_or_none("n1")
    assert (mount.host, mount.repo) == (HOST, REPO)
    assert mount.connection_id == "conn-git"
    assert mount.grant_id == "grant-git"


def test_a_mount_closes_both_handles_exactly_once() -> None:
    import os as _os

    from tinyassets.effectors import WorkspaceMount

    first, second = _os.pipe()
    mount = WorkspaceMount(node_id="n", bind_source="x", repo_fd=first, lease_fd=second)
    mount.close()
    for descriptor in (first, second):
        with pytest.raises(OSError):
            _os.fstat(descriptor)
    mount.close()  # idempotent: a second close must not touch a reused fd


def test_revoking_a_workspace_closes_its_handles(tmp_path: Path) -> None:
    import os as _os

    from tinyassets.effectors import WorkspaceMount

    chain = EffectChain(run_id="r", base_path=str(tmp_path))
    first, second = _os.pipe()
    chain.register_workspace(
        "n0", WorkspaceMount(node_id="n0", bind_source="x", repo_fd=first, lease_fd=second)
    )
    chain.revoke_workspace("n0")
    with pytest.raises(OSError):
        _os.fstat(first)


def test_settling_a_run_closes_every_workspace_it_still_holds(tmp_path: Path) -> None:
    """A run that ended without a discard must not pin the lease open."""
    import os as _os

    from tinyassets.effectors import WorkspaceMount

    chain = EffectChain(run_id="r", base_path=str(tmp_path))
    first, second = _os.pipe()
    chain.register_workspace(
        "n0", WorkspaceMount(node_id="n0", bind_source="x", repo_fd=first, lease_fd=second)
    )
    chain.settle()
    with pytest.raises(OSError):
        _os.fstat(first)
    assert chain.workspace_mount_or_none("n0") is None


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
    assert worker.staging_existed == [True], "staging must exist while the worker runs"
    # ...and be gone before the capability is published: it held the
    # credentialed clone and the bundle (Codex round 2, #5).
    assert not Path(request["staging_dir"]).exists()


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


def test_admission_and_the_creator_agree_on_one_scratch_root(tmp_path: Path) -> None:
    """The pool admits against a path and runs.py creates it; one directory.

    Two spellings means a lease admitted in one place and written in another
    (Codex round 2, P0 #1).
    """
    from tinyassets import runs as _runs

    data_root = tmp_path / "data"
    universe_dir = data_root / UNIVERSE
    universe_dir.mkdir(parents=True)
    created = _runs._ensure_scratch_root(universe_dir)
    assert created == wse.scratch_pool_root(universe_dir)
    assert created == data_root / "scratch"
    assert created.is_dir()


def test_the_universe_root_is_the_universe_not_its_workspaces_dir(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    """`universe_paths` appends `workspaces/` itself; passing it again made
    `workspaces/workspaces/...` (Codex round 2, P0 #1)."""
    from tinyassets import workspace_pool

    _root, universe_dir = _setup(tmp_path)
    assert wse.universe_workspace_root(universe_dir) == universe_dir
    result = _run(tmp_path, _packet(storage="universe"), universe_dir=universe_dir, chain=chain)
    assert result.get("error_kind") is None, result
    mount = chain.workspace_mount_or_none("n1")
    expected, _quarantine = workspace_pool.universe_paths(
        universe_dir, mount.repo_key, mount.generation
    )
    assert Path(mount.lease.path) == expected
    assert "workspaces/workspaces" not in Path(mount.lease.path).as_posix()


def test_a_barrier_that_cannot_run_refuses_instead_of_admitting(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail CLOSED: admitting past a barrier that did not run admits on top of
    whatever an earlier process left owed (Codex round 2, #2)."""
    from tinyassets import runs as _runs
    from tinyassets import workspace_pool

    _root, universe_dir = _setup(tmp_path)
    admitted: list[str] = []
    real_admit = workspace_pool.admit

    def spy_admit(*args, **kwargs):
        admitted.append("admit")
        return real_admit(*args, **kwargs)

    def broken(base_path, **kwargs):
        raise OSError("the runs db is locked")

    monkeypatch.setattr(_runs, "ensure_workspace_reconciled", broken)
    monkeypatch.setattr(workspace_pool, "admit", spy_admit)
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "workspace_pool_busy"
    assert "startup reconciliation failed" in result["error"]
    assert admitted == [], "nothing may be admitted past a barrier that did not run"


def test_a_provision_request_is_refused_without_pretending_it_ran(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    """Nothing installs from the manifest yet; say that, not 'grant a consent'.

    A hint naming a consent implies granting it would make provisioning work
    (Codex round 2, #3).
    """
    _root, universe_dir = _setup(tmp_path)
    result = _run(
        tmp_path,
        _packet(provision={"python": ["x==1.0"]}),
        universe_dir=universe_dir,
        chain=chain,
    )
    assert result.get("error_kind") is None, "the checkout itself still completes"
    assert result["provision"] == "workspace_provision_refused"
    assert result["provision_detail"] == (
        "provisioning is not available in this release (admission only)"
    )
    assert "consent" not in result["provision_detail"]
    assert "provision_hint" not in result


def test_staging_is_gone_before_the_capability_is_published(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    _root, universe_dir = _setup(tmp_path)
    worker = FakeWorker()
    _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain, worker=worker)
    staging = Path(worker.requests[0]["staging_dir"])
    assert not staging.exists(), "staging held the clone and the bundle"


def test_a_checkout_whose_staging_survives_publishes_nothing(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A SILENT partial removal is the case that matters (Codex round 2, #5).

    An rmtree that raises is caught either way; ``ignore_errors=True`` is
    dangerous precisely because it does NOT raise -- it leaves the credentialed
    clone and the bundle sitting there and says nothing. So the stand-in here
    returns normally and leaves the directory, and the existence CHECK is what
    has to catch it.
    """
    _root, universe_dir = _setup(tmp_path)
    monkeypatch.setattr(wse.shutil, "rmtree", lambda path, **kw: None)
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "workspace_checkout_failed"
    assert "staging could not be removed" in result["error"]
    assert chain.workspace_mount_or_none("n1") is None, "nothing may be published"
    rows = _outbox_rows(workspace_pool_db(universe_dir))
    assert any(row["action"] == "wipe_scratch" for row in rows), rows


def test_staging_is_already_gone_at_the_moment_of_publication(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ORDER, not just the end state: gone AFTERWARDS is true either way.

    The capability is what makes the workspace reachable, so staging must
    already be gone when it is published -- not merely by the time the adapter
    returns.
    """
    _root, universe_dir = _setup(tmp_path)
    worker = FakeWorker()
    existed_at_publish: list[bool] = []
    real_register = chain.register_workspace

    def spy(node_id, mount):
        staging = Path(worker.requests[0]["staging_dir"])
        existed_at_publish.append(staging.exists())
        return real_register(node_id, mount)

    monkeypatch.setattr(chain, "register_workspace", spy)
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain, worker=worker)
    assert result.get("error_kind") is None, result
    assert existed_at_publish == [False], "staging outlived the capability's publication"


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


def _with_mount(
    chain: EffectChain,
    tmp_path: Path,
    *,
    node_id: str = "n0",
    host: str = "",
    repo: str = "",
) -> Path:
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
            host=host,
            repo=repo,
            connection_id="conn-git" if repo else "",
            grant_id="grant-git" if repo else "",
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


def test_a_push_derives_its_destination_from_the_capability(
    tmp_path: Path, chain: EffectChain, fs_spy
) -> None:
    """The checkout is what was consented to; the packet does not get to
    redirect the credential (Codex round 2, #6)."""
    _root, universe_dir = _setup(tmp_path)
    _with_mount(chain, tmp_path, host=HOST, repo=REPO)
    worker = FakeWorker({"ok": True, "bytes": 11, "resolved_sha": SHA})
    result = _run(
        tmp_path,
        _packet(op="push", commit_sha=SHA, branch_slug="slug", workspace="n0"),
        universe_dir=universe_dir,
        chain=chain,
        worker=worker,
    )
    assert result.get("error_kind") is None, result
    assert worker.requests[0]["owner_repo"] == REPO
    assert worker.requests[0]["host"] == HOST


@pytest.mark.parametrize(
    "contradiction",
    [{"repo": "someone/else"}, {"connection_id": "conn-other"}],
)
def test_a_packet_that_contradicts_the_capability_is_refused(
    tmp_path: Path, chain: EffectChain, fs_spy, contradiction: dict
) -> None:
    _root, universe_dir = _setup(tmp_path)
    _with_mount(chain, tmp_path, host=HOST, repo=REPO)
    worker = FakeWorker()
    result = _run(
        tmp_path,
        _packet(
            op="push", commit_sha=SHA, branch_slug="slug", workspace="n0", **contradiction
        ),
        universe_dir=universe_dir,
        chain=chain,
        worker=worker,
    )
    assert result["error_kind"] == "invalid_packet"
    assert worker.requests == [], "nothing may be sent on a contradicted capability"


def test_a_workspace_from_a_non_ancestor_node_is_not_reachable(
    tmp_path: Path, chain: EffectChain, fs_spy
) -> None:
    """The chain is run-global; the graph relation is what authorises.

    Without this a node on a parallel branch could push a workspace it has no
    relationship to (Codex round 2, #6).
    """
    _root, universe_dir = _setup(tmp_path)
    _with_mount(chain, tmp_path, host=HOST, repo=REPO)
    worker = FakeWorker()
    result = run_workspace_effector(
        node_id="n1",
        output_keys=["ws"],
        run_state={
            "ws": _packet(op="push", commit_sha=SHA, branch_slug="slug", workspace="n0")
        },
        base_path=universe_dir,
        run_id="run-1",
        chain=chain,
        execute=worker,
        prior_effects={"someone-else": {}},  # n0 is NOT an ancestor
    )
    assert result["error_kind"] == "no_matching_packet"
    assert "graph ancestors" in result["error"]
    assert worker.requests == []


def test_an_ancestor_workspace_is_reachable(
    tmp_path: Path, chain: EffectChain, fs_spy
) -> None:
    """The guard must not be one that always fires."""
    _root, universe_dir = _setup(tmp_path)
    _with_mount(chain, tmp_path, host=HOST, repo=REPO)
    result = run_workspace_effector(
        node_id="n1",
        output_keys=["ws"],
        run_state={
            "ws": _packet(op="push", commit_sha=SHA, branch_slug="slug", workspace="n0")
        },
        base_path=universe_dir,
        run_id="run-1",
        chain=chain,
        execute=FakeWorker({"ok": True, "bytes": 4, "resolved_sha": SHA}),
        prior_effects={"n0": {}},
    )
    assert result.get("error_kind") is None, result
    assert result["op"] == "push"


def test_a_push_journals_its_intent_before_the_wire_and_settles_it(
    tmp_path: Path, chain: EffectChain, fs_spy
) -> None:
    """A crash between sending and recording must leave something to ask about."""
    from tinyassets.workspace_intents import open_intents

    _root, universe_dir = _setup(tmp_path)
    _with_mount(chain, tmp_path, host=HOST, repo=REPO)
    seen_open: list[int] = []

    class RecordingWorker(FakeWorker):
        def __call__(self, request):
            # the intent must already be durable at the moment of the wire
            seen_open.append(len(open_intents(universe_dir)))
            return super().__call__(request)

    worker = RecordingWorker({"ok": True, "bytes": 9, "resolved_sha": SHA})
    result = _run(
        tmp_path,
        _packet(op="push", commit_sha=SHA, branch_slug="slug", workspace="n0"),
        universe_dir=universe_dir,
        chain=chain,
        worker=worker,
    )
    assert result.get("error_kind") is None, result
    assert seen_open == [1], "the intent is written BEFORE the push is sent"
    assert open_intents(universe_dir) == [], "and settled after"


def test_a_failed_push_settles_its_intent_as_failed(
    tmp_path: Path, chain: EffectChain, fs_spy
) -> None:
    import sqlite3

    from tinyassets.workspace_intents import open_intents

    _root, universe_dir = _setup(tmp_path)
    _with_mount(chain, tmp_path, host=HOST, repo=REPO)
    _run(
        tmp_path,
        _packet(op="push", commit_sha=SHA, branch_slug="slug", workspace="n0"),
        universe_dir=universe_dir,
        chain=chain,
        worker=FakeWorker({"ok": False, "error": "refused", "stderr_class": "protected"}),
    )
    assert open_intents(universe_dir) == []
    conn = sqlite3.connect(workspace_pool_db(universe_dir))
    try:
        states = [row[0] for row in conn.execute("SELECT state FROM workspace_push_intents")]
    finally:
        conn.close()
    assert states == ["failed"]


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


def test_a_fired_discard_settles_as_a_write() -> None:
    """A discard destroys a generation and owes an irreversible wipe.

    It touches no network, but the settlement asks whether the run could have
    CHANGED anything, and this changes something (Codex round 2, #12).
    """
    from tinyassets.engine_admissions import fired_only_reads

    assert (EXTERNAL_WRITE_SINK_WORKSPACE, "discard") not in WORKSPACE_READ_EFFECTS
    assert not fired_only_reads(
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
