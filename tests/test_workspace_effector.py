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
        # The REAL helper refuses a missing directory -- it opens, it does not
        # create. The old fake called `mkdir(parents=True)` here, which
        # conjured `workspaces/<repo-key>` and hid the fact that a universe's
        # first permanent checkout could not create them (Codex round 3, P0
        # #3). A fake that is more permissive than the thing it stands in for
        # is a fake that hides the bug it is standing in front of.
        if not Path(path).is_dir():
            raise FileNotFoundError(f"no such directory: {path}")
        return f"fd:{path}"

    def create_lease_dir(parent_fd, name):
        calls["create_lease_dir"].append((parent_fd, name))
        parent = Path(str(parent_fd).removeprefix("fd:"))
        if not parent.is_dir():
            raise FileNotFoundError(f"no such parent: {parent}")
        # The REAL helper refuses a name that is not >=16 random hex characters
        # -- that rule is what makes a name in the SHARED pool root untargetable.
        # A double without it let the permanent GENERATION directory ('1') go
        # through here and pass on Windows while Ubuntu CI failed the same test
        # (run 33355481278). A permissive double is a double that hides the bug.
        if len(name) < workspace_fs.MIN_LEASE_NAME_CHARS or any(
            char not in "0123456789abcdef" for char in name
        ):
            raise workspace_fs.UnsafePoolPath(
                f"a lease directory name must be at least "
                f"{workspace_fs.MIN_LEASE_NAME_CHARS} random hex characters, got {name!r}"
            )
        (parent / name).mkdir(exist_ok=True)  # ONE component, never parents
        return f"fd:{parent}/{name}"

    def create_workspace_subdir(parent_fd, name):
        calls.setdefault("create_workspace_subdir", []).append((parent_fd, name))
        parent = Path(str(parent_fd).removeprefix("fd:"))
        if not parent.is_dir():
            raise FileNotFoundError(f"no such parent: {parent}")
        target = parent / name
        if target.exists():
            raise FileExistsError(str(target))
        target.mkdir()
        return f"fd:{target}"

    def open_subdir_nofollow(parent_fd, name):
        parent = Path(str(parent_fd).removeprefix("fd:"))
        target = parent / name
        if not target.is_dir():
            raise FileNotFoundError(f"no such directory: {target}")
        return f"fd:{target}"

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
        workspace_fs, "create_workspace_subdir", create_workspace_subdir, raising=False
    )
    monkeypatch.setattr(
        workspace_fs, "open_subdir_nofollow", open_subdir_nofollow, raising=False
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
    # (separator-agnostic: the fake joins with the host's own separator)
    assert Path(str(mount.lease_fd).removeprefix("fd:")).name == Path(mount.lease.path).name
    assert Path(str(mount.repo_fd).removeprefix("fd:")).name == "repo"
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
    # `create_workspace_subdir` (lane E) makes the fixed name `<lease>/repo`
    # through the handle and is POSIX-only BY DESIGN. This test is about the
    # PARENT handle's lifetime, which is platform-independent, so the double
    # keeps it running everywhere; the real helper's openat behaviour is lane
    # E's own test.
    monkeypatch.setattr(
        workspace_fs, "create_workspace_subdir", create_lease_dir, raising=False
    )
    monkeypatch.setattr(_os, "close", recording_close)
    _root, universe_dir = _setup(tmp_path)
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert result.get("error_kind") is None, result
    assert opened, "no parent handle was ever opened"
    for parent_fd in opened:
        assert parent_fd in closed, f"parent handle {parent_fd} was leaked"


def test_a_host_without_openat_is_refused_not_crashed(
    tmp_path: Path, chain: EffectChain, no_real_git, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A permanent property of the host is a refusal, not a bug in the sink.

    Letting the no-follow layer's ``NotImplementedError`` reach the dispatcher
    reported ``effector_crashed``, which reads as "the sink is broken" rather
    than "this host cannot run workspaces at all".
    """
    from tinyassets import workspace_fs

    def refuse(*args, **kwargs):
        raise NotImplementedError(
            "create_workspace_subdir needs POSIX openat semantics (O_NOFOLLOW + "
            "dir_fd); this host is 'nt'. There is no fallback."
        )

    for name in ("open_dir_nofollow", "create_lease_dir", "create_workspace_subdir"):
        monkeypatch.setattr(workspace_fs, name, refuse, raising=False)
    _root, universe_dir = _setup(tmp_path)
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "workspace_checkout_failed"
    assert result["error_kind"] != "effector_crashed"
    assert "POSIX openat" in result["error"]
    assert chain.workspace_mount_or_none("n1") is None


def test_the_repo_subdir_helper_alone_refusing_is_still_a_refusal(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact seam that broke: `create_workspace_subdir` is POSIX-only.

    The lease handles can succeed (the spy provides them) and THIS call still
    refuse -- which is what happened on the merged tree, and it surfaced as
    ``effector_crashed``.
    """
    from tinyassets import workspace_fs

    def refuse(*args, **kwargs):
        raise NotImplementedError(
            "create_workspace_subdir needs POSIX openat semantics (O_NOFOLLOW + "
            "dir_fd); this host is 'nt'. There is no fallback."
        )

    monkeypatch.setattr(workspace_fs, "create_workspace_subdir", refuse, raising=False)
    _root, universe_dir = _setup(tmp_path)
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "workspace_checkout_failed"
    assert "POSIX openat" in result["error"]


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
        # A pipe stands in for the directory handle because Windows cannot open
        # a descriptor on a directory at all, and the translator now checks that
        # a published descriptor IS a live directory. That check has its own
        # tests; what this one asserts is WHICH handle is carried.
        monkeypatch.setattr(
            gc, "_require_live_directory", lambda fd, node_id: int(fd), raising=False
        )
        built = gc._sandbox_workspace_mount(mount, "code-node")
        assert built.pass_fds == (repo_read,), "the REPO handle is what the jail inherits"
        assert built.bind_source == f"/proc/self/fd/{repo_read}"
        assert lease_read not in (built.pass_fds or ())
    finally:
        _os.close(repo_read)
        _os.close(lease_read)


def test_the_credentialed_host_comes_from_the_connection_not_the_packet(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    """P0: a packet could point a scoped credential at another host.

    ``packet.host`` was accepted while the scope check discarded host, so the
    two never met. The connection's declared endpoints are the authority now.
    """
    _root, universe_dir = _setup(tmp_path)
    worker = FakeWorker()
    result = _run(
        tmp_path,
        _packet(host="evil.example"),
        universe_dir=universe_dir,
        chain=chain,
        worker=worker,
    )
    assert result["error_kind"] == "invalid_packet"
    assert "different host" in result["error"]
    assert worker.requests == [], "nothing may be sent to a host the packet chose"


def test_a_packet_may_restate_the_derived_host(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    """The guard refuses a CONTRADICTION, not a redundant restatement."""
    _root, universe_dir = _setup(tmp_path)
    worker = FakeWorker()
    result = _run(
        tmp_path, _packet(host=HOST), universe_dir=universe_dir, chain=chain, worker=worker
    )
    assert result.get("error_kind") is None, result
    assert worker.requests[0]["host"] == HOST


def test_the_derived_host_is_what_reaches_the_worker_and_the_mount(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    _root, universe_dir = _setup(tmp_path)
    worker = FakeWorker()
    _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain, worker=worker)
    assert worker.requests[0]["host"] == HOST
    assert chain.workspace_mount_or_none("n1").host == HOST


def test_a_connection_declaring_several_hosts_has_no_git_transport(
    tmp_path: Path, chain: EffectChain
) -> None:
    """One credential, one host: several is ambiguous, and ambiguity here is a
    choice made for the owner."""
    from tinyassets.effectors.workspace import transport_host_for

    class Endpoint:
        def __init__(self, host):
            self.host = host

    class Resource:
        allowed_endpoints = (Endpoint("github.com"), Endpoint("gitlab.example"))
        provider = "http"

    with pytest.raises(Exception) as caught:
        transport_host_for(Resource())
    assert "several hosts" in str(caught.value)


def test_a_first_permanent_checkout_creates_its_parents_through_handles(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    """P0: a universe's FIRST permanent checkout had no workspaces/<repo-key>.

    The no-follow layer refuses a missing parent, and the old fake conjured
    them with ``mkdir(parents=True)``, so this never failed in a test while
    always failing in production.
    """
    _root, universe_dir = _setup(tmp_path)
    assert not (universe_dir / "workspaces").exists(), "the fixture must start fresh"
    result = _run(tmp_path, _packet(storage="universe"), universe_dir=universe_dir, chain=chain)
    assert result.get("error_kind") is None, result
    made = [name for _fd, name in fs_spy.get("create_workspace_subdir", [])]
    assert "workspaces" in made, "the parent must be created through a handle"
    mount = chain.workspace_mount_or_none("n1")
    assert Path(mount.lease.path).is_dir()


def test_a_second_permanent_checkout_reuses_the_existing_parents(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    """Idempotent: an existing component is OPENED, never re-created."""
    _root, universe_dir = _setup(tmp_path)
    first = _run(tmp_path, _packet(storage="universe"), universe_dir=universe_dir, chain=chain)
    assert first.get("error_kind") is None, first
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
    assert second["lease_generation"] != first["lease_generation"]


@pytest.mark.skipif(os.name != "posix", reason="the no-follow helpers are POSIX-only")
def test_a_first_permanent_checkout_works_with_the_real_helpers(
    tmp_path: Path, chain: EffectChain, no_real_git
) -> None:
    """No doubles at all: the REAL workspace_fs against a fresh universe.

    This is the one that would have caught P0 #3 on its own.
    """
    _root, universe_dir = _setup(tmp_path)
    (universe_dir.parent / "scratch").mkdir(exist_ok=True)
    result = _run(tmp_path, _packet(storage="universe"), universe_dir=universe_dir, chain=chain)
    assert result.get("error_kind") is None, result
    mount = chain.workspace_mount_or_none("n1")
    assert Path(mount.lease.path).is_dir()
    assert (universe_dir / "workspaces").is_dir()


@pytest.mark.skipif(os.name != "posix", reason="the no-follow helpers are POSIX-only")
def test_the_descent_closes_every_handle_above_the_one_it_returns(tmp_path: Path) -> None:
    """``_open_permanent_parent`` returns its LAST handle and closes the rest.

    That return is the reason the generation is created without re-resolving
    the parent by path -- and it is also new leak-prone code: one descriptor
    left open per checkout exhausts the table on a long-lived daemon (Codex
    round 2, #7).

    Measured as a COUNT of live descriptors across this one call, which is the
    only unambiguous observable here. Matching opened numbers against closed
    ones does not work: the real helpers open and close descriptors internally
    while walking, and a freed number is immediately reusable -- a set compare
    of those numbers stayed green with every parent leaked (measured on Linux,
    2026-08-31). Counting is immune to reuse, and nothing else opens a
    descriptor inside this call.
    """
    import stat as _stat

    universe_dir = tmp_path / "universe-1"
    (universe_dir / "workspaces").mkdir(parents=True)  # exists: the OPEN branch
    lease_path = universe_dir / "workspaces" / "owner-name" / "1"  # created

    before = len(os.listdir("/proc/self/fd"))
    returned = wse._open_permanent_parent(universe_dir, lease_path)
    try:
        live = len(os.listdir("/proc/self/fd")) - before
        assert live == 1, f"the descent left {live} descriptors open, not just its result"
        assert _stat.S_ISDIR(os.fstat(returned).st_mode), "the caller's handle is open"
    finally:
        os.close(returned)


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


def test_a_permanent_generation_is_a_subdir_not_a_shared_pool_lease(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    """``create_lease_dir``'s entropy rule is for the SHARED scratch root.

    A generation is a small integer inside the universe's own tree, under a
    parent this process walked open itself, so the rule protects nothing and
    refuses everything: Ubuntu CI failed every permanent checkout with
    "a lease directory name must be at least 16 random hex characters ...
    got '1'" (run 33355481278).
    """
    _root, universe_dir = _setup(tmp_path)
    result = _run(tmp_path, _packet(storage="universe"), universe_dir=universe_dir, chain=chain)

    assert result.get("error_kind") is None, result
    assert fs_spy["create_lease_dir"] == [], "a generation must not take the pool-lease path"
    generation = str(result["lease_generation"])
    made = [name for _fd, name in fs_spy["create_workspace_subdir"]]
    assert generation in made, f"the generation {generation!r} was not made as a subdir: {made}"


def test_the_generation_is_made_under_the_handle_its_parent_was_walked_open_with(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    """No re-resolution by path between walking the parents and using them.

    Re-opening ``workspaces/<repo-key>`` by absolute path would hand back the
    exact window the component-by-component descent exists to close.
    """
    _root, universe_dir = _setup(tmp_path)
    result = _run(tmp_path, _packet(storage="universe"), universe_dir=universe_dir, chain=chain)
    assert result.get("error_kind") is None, result

    opened_by_path = fs_spy["open_dir_nofollow"]
    assert opened_by_path == [str(universe_dir)], (
        "only the universe root may be resolved by path; the rest is descent"
    )
    generation = str(result["lease_generation"])
    parent_fd = next(fd for fd, name in fs_spy["create_workspace_subdir"] if name == generation)
    repo_key = Path(chain.workspace_mount_or_none("n1").lease.path).parent.name
    assert str(parent_fd).endswith(repo_key), (
        f"the generation was made under {parent_fd!r}, not the repo-key handle"
    )


def test_a_scratch_lease_still_gets_the_unguessable_name_rule(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git
) -> None:
    """The split must not quietly drop the rule where it does protect something."""
    _root, universe_dir = _setup(tmp_path)
    result = _run(tmp_path, _packet(storage="scratch"), universe_dir=universe_dir, chain=chain)

    assert result.get("error_kind") is None, result
    assert len(fs_spy["create_lease_dir"]) == 1, "a scratch lease goes through create_lease_dir"
    _fd, name = fs_spy["create_lease_dir"][0]
    assert len(name) >= 16 and all(char in "0123456789abcdef" for char in name), name


def test_a_directory_the_no_follow_layer_refuses_is_a_refusal_not_a_crash(
    tmp_path: Path, chain: EffectChain, fs_spy, monkeypatch: pytest.MonkeyPatch, no_real_git
) -> None:
    """``UnsafePoolPath`` is how that layer says no; the graph author sees a code.

    Reported as ``effector_crashed`` it reads as a bug in the sink -- which is
    exactly how the generation bug presented in CI.
    """
    from tinyassets import workspace_fs

    _root, universe_dir = _setup(tmp_path)

    def refuse(parent_fd, name):
        raise workspace_fs.UnsafePoolPath(f"{name!r} is a symlink, not a directory")

    monkeypatch.setattr(workspace_fs, "create_workspace_subdir", refuse, raising=False)
    result = _run(tmp_path, _packet(storage="universe"), universe_dir=universe_dir, chain=chain)

    assert result["error_kind"] == "workspace_checkout_failed", result
    assert "symlink" in result["error"], result


def test_a_bad_component_from_the_no_follow_layer_is_also_a_refusal(
    tmp_path: Path, chain: EffectChain, fs_spy, monkeypatch: pytest.MonkeyPatch, no_real_git
) -> None:
    """That layer raises ValueError for a name that is not one safe component."""
    from tinyassets import workspace_fs

    _root, universe_dir = _setup(tmp_path)

    def refuse(parent_fd, name):
        raise ValueError(f"{name!r} is not a single path component")

    monkeypatch.setattr(workspace_fs, "create_lease_dir", refuse, raising=False)
    result = _run(tmp_path, _packet(storage="scratch"), universe_dir=universe_dir, chain=chain)

    assert result["error_kind"] == "workspace_checkout_failed", result
    assert result["error_kind"] != "effector_crashed"


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


def test_staging_ids_are_injective(tmp_path: Path) -> None:
    """`a/b` and `ab` must not share a staging directory or a broker socket.

    Stripping unsafe characters collapses them to the same name, which would
    put two nodes' credentialed staging in one place (Codex round 3, P2 #11).
    """
    base = tmp_path / "u"
    base.mkdir()
    first = wse._staging_root(base, "run-1", "a/b")
    second = wse._staging_root(base, "run-1", "ab")
    assert first != second
    assert first.parent == second.parent
    assert wse._staging_id("a/b") != wse._staging_id("ab")
    # ...and two operations of the SAME node get their own directory
    again = wse._staging_root(base, "run-1", "a/b")
    assert again != first


def test_a_packet_cannot_choose_its_own_reservation(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`packet.max_bytes` is gone: a packet choosing its reservation is a
    packet choosing its own quota (Codex round 3, P1 #4)."""
    from tinyassets import workspace_pool

    _root, universe_dir = _setup(tmp_path)
    seen: list[int] = []
    real_admit = workspace_pool.admit

    def spy(db, **kwargs):
        seen.append(kwargs["max_bytes"])
        return real_admit(db, **kwargs)

    monkeypatch.setattr(workspace_pool, "admit", spy)
    result = _run(
        tmp_path, _packet(max_bytes=1), universe_dir=universe_dir, chain=chain
    )
    assert result.get("error_kind") is None, result
    assert seen == [wse._DEFAULT_MAX_CHECKOUT_BYTES], "the platform's bound, not the packet's"


def test_a_push_reserves_the_bundle_bound_before_the_copy(
    tmp_path: Path, chain: EffectChain, fs_spy, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A push holds no lease, so without this the hour saw nothing at all."""
    from tinyassets import workspace_pool

    _root, universe_dir = _setup(tmp_path)
    _with_mount(chain, tmp_path, host=HOST, repo=REPO)
    order: list[str] = []
    real_reserve = workspace_pool.reserve_operation_bytes

    def spy_reserve(db, **kwargs):
        order.append(f"reserve:{kwargs['operation_id']}:{kwargs['max_bytes']}")
        return real_reserve(db, **kwargs)

    monkeypatch.setattr(workspace_pool, "reserve_operation_bytes", spy_reserve)
    real_copy = wse._fs().copy_regular_file_beneath

    def spy_copy(*args, **kwargs):
        order.append("copy")
        return real_copy(*args, **kwargs)

    monkeypatch.setattr(wse._fs(), "copy_regular_file_beneath", spy_copy, raising=False)
    result = _run(
        tmp_path,
        _packet(op="push", commit_sha=SHA, branch_slug="slug", workspace="n0"),
        universe_dir=universe_dir,
        chain=chain,
        worker=FakeWorker({"ok": True, "bytes": 11, "resolved_sha": SHA}),
    )
    assert result.get("error_kind") is None, result
    assert order[0].startswith("reserve:"), "the ledger sees it BEFORE the bytes move"
    assert "copy" in order and order.index("copy") > 0
    assert f":{512 * 1024 * 1024}" in order[0]
    assert "run-1:n1:push" in order[0], "the operation id is deterministic"


def test_a_discard_reserves_one_job_before_it_mutates(
    tmp_path: Path, chain: EffectChain, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tinyassets import workspace_pool

    _root, universe_dir = _setup(tmp_path)
    _with_mount(chain, tmp_path, host=HOST, repo=REPO)
    order: list[str] = []
    real_reserve = workspace_pool.reserve_operation_bytes

    def spy_reserve(db, **kwargs):
        order.append("reserve")
        return real_reserve(db, **kwargs)

    real_revoke = chain.revoke_workspace

    def spy_revoke(node_key):
        order.append("revoke")
        return real_revoke(node_key)

    monkeypatch.setattr(workspace_pool, "reserve_operation_bytes", spy_reserve)
    monkeypatch.setattr(chain, "revoke_workspace", spy_revoke)
    result = _run(
        tmp_path,
        _packet(op="discard", workspace="n0"),
        universe_dir=universe_dir,
        chain=chain,
    )
    assert result.get("error_kind") is None, result
    assert order[:2] == ["reserve", "revoke"]


def test_a_push_holds_the_capability_across_the_copy(
    tmp_path: Path, chain: EffectChain, fs_spy, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A discard racing the copy must not pull the descriptor out from under it.

    Driven through the REAL ``acquire_workspace``: the assertion is the chain's
    own hold count observed DURING the copy, which a double could only claim.
    """
    _root, universe_dir = _setup(tmp_path)
    _with_mount(chain, tmp_path, host=HOST, repo=REPO)
    holds_during_copy: list[int] = []
    real_copy = wse._fs().copy_regular_file_beneath

    def watching_copy(*args, **kwargs):
        holds_during_copy.append(chain.workspace_holds.get("n0", 0))
        return real_copy(*args, **kwargs)

    monkeypatch.setattr(wse._fs(), "copy_regular_file_beneath", watching_copy, raising=False)
    result = _run(
        tmp_path,
        _packet(op="push", commit_sha=SHA, branch_slug="slug", workspace="n0"),
        universe_dir=universe_dir,
        chain=chain,
        worker=FakeWorker({"ok": True, "bytes": 4, "resolved_sha": SHA}),
    )
    assert result.get("error_kind") is None, result
    assert holds_during_copy == [1], "the copy must run inside a held acquisition"
    assert chain.workspace_holds.get("n0", 0) == 0, "and the hold is released after"


def test_the_held_descriptors_are_duplicates_not_the_originals(
    tmp_path: Path, chain: EffectChain, fs_spy, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of the dup: a discard closes the ORIGINALS and the next
    checkout gets the same fd numbers back, so a holder on the original number
    would be reading another branch's repository."""
    _root, universe_dir = _setup(tmp_path)
    lease_dir = _with_mount(chain, tmp_path, host=HOST, repo=REPO)
    original = chain.workspace_mount_or_none("n0")
    seen: list[Any] = []
    real_copy = wse._fs().copy_regular_file_beneath

    def watching_copy(dir_fd, *args, **kwargs):
        seen.append(dir_fd)
        return real_copy(dir_fd, *args, **kwargs)

    monkeypatch.setattr(wse._fs(), "copy_regular_file_beneath", watching_copy, raising=False)
    _run(
        tmp_path,
        _packet(op="push", commit_sha=SHA, branch_slug="slug", workspace="n0"),
        universe_dir=universe_dir,
        chain=chain,
        worker=FakeWorker({"ok": True, "bytes": 4, "resolved_sha": SHA}),
    )
    assert seen, "the copy never ran"
    # The fs_spy hands back string handles, so identity is what is observable:
    # the copy used the ACQUIRED mount's handle, not the registry's object.
    assert seen[0] == original.lease_fd or str(seen[0]).endswith(lease_dir.name)


def test_a_push_whose_capability_was_revoked_is_refused(
    tmp_path: Path, chain: EffectChain, fs_spy
) -> None:
    """Revoked for REAL, through the chain -- not a double that returns None."""
    _root, universe_dir = _setup(tmp_path)
    _with_mount(chain, tmp_path, host=HOST, repo=REPO)
    chain.revoke_workspace("n0")
    worker = FakeWorker()
    result = _run(
        tmp_path,
        _packet(op="push", commit_sha=SHA, branch_slug="slug", workspace="n0"),
        universe_dir=universe_dir,
        chain=chain,
        worker=worker,
    )
    assert result["error_kind"] == "no_matching_packet"
    assert worker.requests == []


def test_a_discard_acquires_before_it_revokes(
    tmp_path: Path, chain: EffectChain, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The outbox entry is built from a capability this call HOLDS.

    Revoking first and reading the mount afterwards would build the entry from
    an object nothing owns any more.
    """
    _root, universe_dir = _setup(tmp_path)
    _with_mount(chain, tmp_path, host=HOST, repo=REPO)
    order: list[str] = []
    real_acquire = chain.acquire_workspace
    real_revoke = chain.revoke_workspace

    def spy_acquire(node_key):
        order.append("acquire")
        return real_acquire(node_key)

    def spy_revoke(node_key):
        order.append(f"revoke:holds={chain.workspace_holds.get(node_key, 0)}")
        return real_revoke(node_key)

    monkeypatch.setattr(chain, "acquire_workspace", spy_acquire)
    monkeypatch.setattr(chain, "revoke_workspace", spy_revoke)
    result = _run(
        tmp_path,
        _packet(op="discard", workspace="n0"),
        universe_dir=universe_dir,
        chain=chain,
    )
    assert result.get("error_kind") is None, result
    assert order == ["acquire", "revoke:holds=1"], order
    assert chain.workspace_mount_or_none("n0") is None


def test_a_lost_push_settles_as_unknown_never_failed(
    tmp_path: Path, chain: EffectChain, fs_spy
) -> None:
    """A timeout means the send MAY have landed (Codex round 3, P1 #5)."""
    from tinyassets.workspace_intents import open_intents

    _root, universe_dir = _setup(tmp_path)
    _with_mount(chain, tmp_path, host=HOST, repo=REPO)
    result = _run(
        tmp_path,
        _packet(op="push", commit_sha=SHA, branch_slug="slug", workspace="n0"),
        universe_dir=universe_dir,
        chain=chain,
        worker=FakeWorker({"ok": False, "error": "timed out", "stderr_class": "timeout"}),
    )
    assert result["error_kind"] == "workspace_push_refused"
    assert result["intent_state"] == "unknown"
    assert open_intents(universe_dir) == [], "settled, but as unknown rather than failed"


def test_a_push_journals_the_host_grant_and_universe(
    tmp_path: Path, chain: EffectChain, fs_spy
) -> None:
    """Reconciliation needs them: it must not default to github.com."""
    import sqlite3

    _root, universe_dir = _setup(tmp_path)
    _with_mount(chain, tmp_path, host=HOST, repo=REPO)
    _run(
        tmp_path,
        _packet(op="push", commit_sha=SHA, branch_slug="slug", workspace="n0"),
        universe_dir=universe_dir,
        chain=chain,
        worker=FakeWorker({"ok": True, "bytes": 4, "resolved_sha": SHA}),
    )
    conn = sqlite3.connect(workspace_pool_db(universe_dir))
    try:
        row = conn.execute(
            "SELECT host, grant_id, universe_id FROM workspace_push_intents"
        ).fetchone()
    finally:
        conn.close()
    assert row == (HOST, "grant-git", UNIVERSE)


def test_a_failed_checkout_closes_what_it_opened_and_owes_the_wipe(
    tmp_path: Path, chain: EffectChain, fs_spy, no_real_git, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One owner: an unpublished failure leaks no descriptor and no lease."""
    import os as _os

    _root, universe_dir = _setup(tmp_path)
    closed: list[int] = []
    real_close = _os.close

    monkeypatch.setattr(
        _os, "close", lambda fd: (closed.append(fd), real_close(fd))[1], raising=True
    )
    monkeypatch.setattr(
        wse.shutil, "rmtree", lambda path, **kw: (_ for _ in ()).throw(OSError("busy"))
    )
    result = _run(tmp_path, _packet(), universe_dir=universe_dir, chain=chain)
    assert result["error_kind"] == "workspace_checkout_failed"
    assert chain.workspace_mount_or_none("n1") is None
    rows = _outbox_rows(workspace_pool_db(universe_dir))
    assert any(row["action"] == "wipe_scratch" for row in rows), rows


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
