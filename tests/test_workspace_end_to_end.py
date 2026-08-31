"""The workspace chain end to end, with only the two network legs faked.

Five lanes meet here - the effect adapter, the credential-blind worker, the git
helpers, the lease pool with its no-follow handles, and the sandbox that runs a
node inside the checkout - and every one of them is tested well on its own. What
no single-lane suite can show is the SEAM: an adapter whose injected filesystem
helper creates directories the real one refuses to, a bundle that only the fake
worker would have accepted, a lease that is released in the pool's tables while
its bytes stay on disk.

So this module fakes exactly two things, and both are the wire: the checkout leg
(which would clone from github) and the push leg (which would send there). The
checkout leg produces a REAL prerequisite-free bundle with real git from a real
local repository, and the push leg records what it was handed so the test can
verify it the way the worker would. Everything between them is the shipping
code.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from tinyassets import runs as runs_module
from tinyassets import workspace_pool
from tinyassets.effectors import EffectChain
from tinyassets.effectors import workspace as wse
from tinyassets.effectors.workspace import (
    EXTERNAL_WRITE_SINK_WORKSPACE,
    run_workspace_effector,
)
from tinyassets.node_sandbox import NodeSandbox, PlainSubprocessLauncher
from tinyassets.storage.effector_consents import grant_consent
from tinyassets.storage.outbound_connections import ConnectionLedger
from tinyassets.storage.workspace_authority import workspace_consent_destination
from tinyassets.workspace_git import verify_bundle

GIT = shutil.which("git")
PY = sys.executable
POSIX = os.name == "posix"

pytestmark = pytest.mark.skipif(GIT is None, reason="the chain is git; there is none here")

UNIVERSE = "universe-e2e"
REPO = "owner/name"
HOST = "github.com"
#: The one string that must never come back out. A real token shape, so a
#: substring search cannot pass by accident.
TOKEN = "tok-e2e-9f41c7b25ae83d06"
RUN_ID = "run-e2e-1"
CHECKOUT_NODE = "checkout"


# --------------------------------------------------------------------------
# the world: a real repository, a real universe, a real vault
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Origin:
    path: Path
    head: str
    readme: str


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [GIT, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def origin(tmp_path: Path) -> Origin:
    """A real repository with real history - what github would be serving."""
    path = tmp_path / "origin"
    path.mkdir()
    readme = "hello from the origin\n"
    _git("init", "--quiet", "--initial-branch=main", ".", cwd=path)
    _git("config", "user.email", "origin@tinyassets.test", cwd=path)
    _git("config", "user.name", "origin", cwd=path)
    (path / "README.md").write_text(readme, encoding="utf-8")
    (path / "pkg").mkdir()
    (path / "pkg" / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git("add", "-A", cwd=path)
    _git("commit", "--quiet", "-m", "first", cwd=path)
    head = _git("rev-parse", "HEAD", cwd=path).stdout.strip()
    return Origin(path=path, head=head, readme=readme)


@dataclass(frozen=True)
class Universe:
    data_root: Path
    universe_dir: Path
    pool_root: Path


def _make_universe(
    tmp_path: Path,
    *,
    scopes: tuple[str, ...] = (f"git_read:{REPO}", f"git_write:{REPO}"),
    consents: tuple[str, ...] = ("checkout", "push", "provision"),
) -> Universe:
    data_root = tmp_path / "data"
    universe_dir = data_root / UNIVERSE
    universe_dir.mkdir(parents=True)
    # The scratch pool root is the DAEMON's to create: the pool module creates
    # no directories and the real open_dir_nofollow refuses a missing parent.
    pool_root = data_root / "scratch"
    pool_root.mkdir(parents=True)
    os.chmod(pool_root, 0o700)

    ledger = ConnectionLedger(
        data_root / "outbound.db", verify_authenticated_principal=lambda: "user-1"
    )
    ledger.create_connection(
        connection_id="conn-git",
        owner_user_id="user-1",
        connection_class="outbound-http",
        scopes=scopes,
        provider="http",
        destination=f"github.com/{REPO}",
        credential_ref="vault://http/github",
        connection_type="http",
        auth_scheme="bearer",
        allowed_endpoints=[
            {"host": HOST, "path_template": "/owner/name", "methods": ["GET"]}
        ],
    )
    ledger.grant_connection(
        grant_id="grant-git",
        connection_id="conn-git",
        owner_user_id="user-1",
        universe_id=UNIVERSE,
    )
    for op in consents:
        grant_consent(
            universe_dir,
            sink=EXTERNAL_WRITE_SINK_WORKSPACE,
            destination=workspace_consent_destination(
                f"workspace_{op}", REPO, connection_id="conn-git"
            ),
            granted_by="founder",
        )
    return Universe(data_root=data_root, universe_dir=universe_dir, pool_root=pool_root)


@pytest.fixture
def universe(tmp_path: Path) -> Universe:
    return _make_universe(tmp_path)


@pytest.fixture(autouse=True)
def vault(monkeypatch: pytest.MonkeyPatch):
    """The credential the worker resolves. Real resolution path, one token."""
    from tinyassets.storage import outbound_connections

    class Resolver:
        def __init__(self, *, universe_dir: str) -> None:
            self.universe_dir = universe_dir

        def __call__(self, credential_ref: str) -> str:
            if credential_ref != "vault://http/github":
                raise RuntimeError("no such credential")
            return TOKEN

    monkeypatch.setattr(
        outbound_connections, "_GeneralVaultCredentialResolver", Resolver
    )


@pytest.fixture
def chain(universe: Universe) -> EffectChain:
    return EffectChain(
        run_id=RUN_ID, base_path=str(universe.data_root), universe_id=UNIVERSE
    )


@pytest.fixture
def fs_bridge(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """POSIX runs the REAL no-follow handles. Windows has neither ``dir_fd`` nor
    ``O_NOFOLLOW``, so there the helpers are injected exactly as the adapter's
    own suite injects them - the Linux leg of this file is what proves the real
    ones work."""
    calls: dict[str, list] = {"open_dir_nofollow": [], "create_lease_dir": [], "copy": []}
    if POSIX:
        return calls

    from tinyassets import workspace_fs

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
        data = source.read_bytes()
        if len(data) > max_bytes:
            raise ValueError("bundle exceeds max_bytes")
        Path(dest_path).write_bytes(data)
        return len(data)

    monkeypatch.setattr(workspace_fs, "open_dir_nofollow", open_dir_nofollow)
    monkeypatch.setattr(workspace_fs, "create_lease_dir", create_lease_dir)
    monkeypatch.setattr(workspace_fs, "create_workspace_subdir", create_lease_dir)
    monkeypatch.setattr(
        workspace_fs, "copy_regular_file_beneath", copy_regular_file_beneath
    )
    return calls


# --------------------------------------------------------------------------
# the two faked legs - and only these two
# --------------------------------------------------------------------------


class WireWorker:
    """The worker's network legs, faked; everything else about it is real.

    ``checkout`` produces a genuine prerequisite-free bundle with real git from
    the local origin, which is what makes the host-side populate a real test
    rather than a fixture. ``push`` records the request so the test can verify
    the bundle the way the worker would before sending it.
    """

    def __init__(self, origin: Origin) -> None:
        self.origin = origin
        self.requests: list[dict[str, Any]] = []
        self.secrets_seen: list[str] = []
        self.push_refusal: dict[str, Any] | None = None
        self.checkout_sha_override: str | None = None

    def __call__(self, request: dict[str, Any]) -> dict[str, Any]:
        from tinyassets.workspace_worker import _resolve_secret

        self.requests.append(dict(request))
        # The real resolution path: a leak of this token anywhere downstream is
        # what scenario 6 hunts for.
        self.secrets_seen.append(_resolve_secret(request))

        staging = Path(request["staging_dir"])
        if request["op"] == "checkout":
            bundle = staging / "out.bundle"
            subprocess.run(
                [GIT, "bundle", "create", str(bundle), "refs/heads/main"],
                cwd=str(self.origin.path),
                capture_output=True,
                text=True,
                check=True,
            )
            return {
                "ok": True,
                "resolved_sha": self.checkout_sha_override or self.origin.head,
                "bytes": bundle.stat().st_size,
                "bundle_name": "out.bundle",
                "ref_name": "refs/heads/main",
            }
        if request["op"] == "push":
            if self.push_refusal is not None:
                return self.push_refusal
            return {
                "ok": True,
                "bytes": Path(request["bundle_path"]).stat().st_size,
                "reconciled": False,
            }
        raise AssertionError(f"unexpected op {request['op']!r}")


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


def _fire(
    packet: dict[str, Any],
    *,
    universe: Universe,
    chain: EffectChain,
    worker: WireWorker,
    node_id: str = CHECKOUT_NODE,
) -> dict[str, Any]:
    return run_workspace_effector(
        node_id=node_id,
        output_keys=["ws"],
        run_state={"ws": packet},
        base_path=universe.universe_dir,
        run_id=RUN_ID,
        chain=chain,
        execute=worker,
    )


def _run_in_workspace(mount: Any, source: str, *, timeout: float = 120.0) -> Any:
    """The node, in the real sandbox, bound to the real lease.

    The chain's mount and the sandbox's are different objects with the same
    name; translating between them is the compiler's job in production
    (``_build_source_code_node``), and this mirrors it so the sandbox leg can be
    driven directly.
    """
    from tinyassets.node_sandbox import WorkspaceMount as SandboxWorkspaceMount

    # The child gets no PATH (the launcher builds its env from constants), so a
    # node names its binaries absolutely. On Linux a bare "git" still resolves
    # through execvp's CS_PATH fallback; on Windows there is no such fallback.
    source = f"GIT = {GIT!r}\n" + source
    sandbox = NodeSandbox(
        launcher=PlainSubprocessLauncher(workspace_bind=str(mount.bind_source)),
        timeout=timeout,
    )
    return sandbox.run_sync(
        node_id="worker-node",
        source_code=source,
        input_state={},
        input_keys=[],
        output_keys=["result"],
        timeout=timeout,
        workspace=SandboxWorkspaceMount(bind_source=str(mount.bind_source)),
    )


def _seed_run(universe: Universe, run_id: str = RUN_ID) -> None:
    runs_module.initialize_runs_db(universe.universe_dir)
    with runs_module._connect(universe.universe_dir) as conn:
        conn.execute(
            "INSERT INTO runs (run_id, branch_def_id, thread_id, status, started_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, "branch-e2e", f"t-{run_id}", "running", time.time()),
        )


def _outbox_outcomes(universe: Universe) -> list[tuple]:
    """What the processor recorded, verbatim - a LOST carries its exception."""
    import sqlite3

    db = runs_module.runs_db_path(universe.universe_dir)
    if not db.exists():
        return []
    conn = sqlite3.connect(str(db))
    try:
        return list(
            conn.execute("SELECT action, outcome, done_at FROM workspace_outbox")
        )
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _assert_nothing_holds_the_lease(lease_dir: Path) -> None:
    """Windows only, and it is the whole point of the check: a rename fails
    while another process holds the file, so this proves every git child the
    checkout started has exited before the sweep tries to delete.

    POSIX renames and unlinks regardless of open handles, so there is nothing
    to prove there.
    """
    if POSIX:
        return
    for path in sorted(p for p in lease_dir.rglob("*") if p.is_file()):
        probe = path.with_suffix(path.suffix + ".handleprobe")
        try:
            os.rename(path, probe)
            os.rename(probe, path)
        except OSError as exc:  # pragma: no cover - only when a handle leaks
            raise AssertionError(
                f"{path} is still held before the terminal write: {exc}"
            ) from exc


def _lease_rows(universe: Universe) -> list[tuple]:
    import sqlite3

    db = runs_module.runs_db_path(universe.universe_dir)
    if not db.exists():
        return []
    conn = sqlite3.connect(str(db))
    try:
        return list(
            conn.execute("SELECT lease_id, state, storage_class FROM workspace_leases")
        )
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


# --------------------------------------------------------------------------
# 1. checkout, then a node runs inside it
# --------------------------------------------------------------------------


def test_a_checkout_delivers_a_workspace_a_node_can_run_git_in(
    origin: Origin, universe: Universe, chain: EffectChain, fs_bridge
) -> None:
    worker = WireWorker(origin)
    evidence = _fire(_packet(), universe=universe, chain=chain, worker=worker)

    assert evidence.get("error_kind") is None, evidence
    assert evidence["op"] == "checkout"
    assert evidence["resolved_sha"] == origin.head
    assert evidence["storage"] == "scratch"

    mount = chain.workspace_mount(CHECKOUT_NODE)
    assert mount is not None, "the checkout did not register its mount"
    repo_dir = Path(mount.bind_source)
    assert (repo_dir / "README.md").read_text(encoding="utf-8") == origin.readme
    assert (repo_dir / ".git").is_dir()

    if POSIX:
        # The handle the jail binds through must be the REPOSITORY. Binding the
        # lease root instead would hand user code the export directory and any
        # sibling the pool put there, and the difference is invisible in a path
        # comparison - so compare inodes through the descriptor itself.
        through_fd = os.stat(f"/proc/self/fd/{mount.repo_fd}")
        repository = os.stat(repo_dir)
        lease_root = os.stat(repo_dir.parent)
        assert (through_fd.st_dev, through_fd.st_ino) == (
            repository.st_dev,
            repository.st_ino,
        )
        assert (through_fd.st_dev, through_fd.st_ino) != (
            lease_root.st_dev,
            lease_root.st_ino,
        ), "the mount binds the lease root, not the repository"

    result = _run_in_workspace(
        mount,
        "def run(state):\n"
        "    head = ws.run([GIT, 'rev-parse', 'HEAD'])\n"
        "    return {'result': {'sha': head['stdout_tail'].strip(),\n"
        "                       'code': head['returncode'],\n"
        "                       'readme': ws.read('README.md')}}\n",
    )
    assert result.success, getattr(result, "error", None) or result.stderr
    payload = result.output_state["result"]
    assert payload["code"] == 0
    assert payload["sha"] == origin.head
    assert payload["readme"] == origin.readme


# --------------------------------------------------------------------------
# 2. the node commits and bundles; the push leg gets a real bundle
# --------------------------------------------------------------------------


@pytest.mark.skipif(
    not POSIX,
    reason=(
        "ws.bundle shells out to a BARE git, which resolves only through "
        "execvp's CS_PATH fallback; the sandbox child is given no PATH"
    ),
)
def test_a_node_commit_becomes_a_bundle_the_push_leg_can_verify(
    origin: Origin, universe: Universe, chain: EffectChain, fs_bridge, tmp_path: Path
) -> None:
    worker = WireWorker(origin)
    _fire(_packet(), universe=universe, chain=chain, worker=worker)
    mount = chain.workspace_mount(CHECKOUT_NODE)
    assert mount is not None

    identity = (
        "[GIT, '-c', 'user.email=node@tinyassets.test', '-c', 'user.name=node']"
    )
    result = _run_in_workspace(
        mount,
        "def run(state):\n"
        "    ws.write('README.md', 'changed by the node\\n')\n"
        f"    base = {identity}\n"
        "    add = ws.run(base + ['add', 'README.md'])\n"
        "    made = ws.run(base + ['commit', '-m', 'node change'])\n"
        "    sha = ws.run([GIT, 'rev-parse', 'HEAD'])['stdout_tail'].strip()\n"
        "    relative = ws.bundle(sha)\n"
        "    return {'result': {'add': add['returncode'], 'commit': made['returncode'],\n"
        "                       'sha': sha, 'bundle': relative,\n"
        "                       'stderr': made['stderr_tail'][-300:]}}\n",
    )
    assert result.success, getattr(result, "error", None) or result.stderr
    payload = result.output_state["result"]
    assert payload["add"] == 0 and payload["commit"] == 0, payload
    new_sha = payload["sha"]
    assert new_sha != origin.head
    assert payload["bundle"] == f".tiny-export/{new_sha}.bundle"

    push = _fire(
        _packet(
            op="push",
            commit_sha=new_sha,
            branch_slug="e2e-change",
            workspace=CHECKOUT_NODE,
        ),
        universe=universe,
        chain=chain,
        worker=worker,
        node_id="push-node",
    )
    assert push.get("error_kind") is None, push
    assert push["sha"] == new_sha
    assert push["remote_ref"].startswith("refs/heads/tiny/")
    assert push["remote_ref"].endswith("/e2e-change")

    request = worker.requests[-1]
    assert request["op"] == "push"
    assert request["commit_sha"] == new_sha

    # What the worker would do before sending: verify it credential-free, in a
    # fresh empty scratch, and refuse prerequisites.
    scratch = tmp_path / "verify-scratch"
    scratch.mkdir()
    home = tmp_path / "verify-home"
    home.mkdir()
    refs = verify_bundle(
        Path(request["bundle_path"]),
        max_bytes=512 * 1024 * 1024,
        scratch_dir=scratch,
        home_dir=home,
        path=str(Path(GIT).parent),
    )
    assert refs, "verify_bundle returned no refs"
    text = " ".join(str(ref) for ref in refs)
    assert "refs/tiny/export" in text
    listed = subprocess.run(
        [GIT, "bundle", "list-heads", str(request["bundle_path"])],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert new_sha in listed, listed


# --------------------------------------------------------------------------
# 3. the terminal write owes the outbox, and the sweep frees the lease
# --------------------------------------------------------------------------


def test_a_finished_run_releases_its_lease_and_the_next_run_is_admitted(
    origin: Origin,
    universe: Universe,
    chain: EffectChain,
    fs_bridge,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_run(universe)
    worker = WireWorker(origin)
    # Every child this test starts is waited on before the terminal write:
    # the fake wire leg uses subprocess.run, and the adapter's populate does
    # too. Nothing here is left exiting while the sweep deletes.
    _fire(_packet(), universe=universe, chain=chain, worker=worker)
    rows = _lease_rows(universe)
    assert [state for _id, state, _class in rows] == ["ACTIVE"], rows
    lease_path = Path(chain.workspace_mount(CHECKOUT_NODE).bind_source).parent
    # The lifecycle proof is only worth anything if the wipe is deleting a
    # lease nobody is holding: on POSIX these are the REAL no-follow handles,
    # and on Windows this proves every git child has exited first.
    _assert_nothing_holds_the_lease(lease_path)

    threads: list[Any] = []
    real_kick = runs_module._kick_workspace_sweep
    monkeypatch.setattr(
        runs_module, "_kick_workspace_sweep", lambda p: threads.append(real_kick(p))
    )
    runs_module.update_run_status(
        universe.universe_dir, RUN_ID, status="completed", finished_at=time.time()
    )
    for thread in threads:
        if thread is not None:
            thread.join(timeout=60)

    # The outcome text carries the exception when a wipe failed, so a LOST here
    # says WHY without a second run. On Windows a delete can lose to a git child
    # that is still exiting (sharing violation); the filesystem retries those
    # for three seconds, and anything still failing after that is real.
    rows = _lease_rows(universe)
    assert [state for _id, state, _class in rows] == ["AVAILABLE"], (
        rows,
        _outbox_outcomes(universe),
    )
    assert not lease_path.exists(), (
        "the lease directory outlived its lease",
        _outbox_outcomes(universe),
    )

    import sqlite3

    conn = sqlite3.connect(str(runs_module.runs_db_path(universe.universe_dir)))
    try:
        held = conn.execute("SELECT COUNT(*) FROM workspace_locks").fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM workspace_outbox WHERE done_at IS NULL"
        ).fetchone()[0]
    finally:
        conn.close()
    assert held == 0, "both locks are released by the sweep"
    assert pending == 0

    # And the next run is admitted at once, which is the whole point of the
    # lock being released rather than waited out.
    second_chain = EffectChain(
        run_id="run-e2e-2", base_path=str(universe.data_root), universe_id=UNIVERSE
    )
    second = run_workspace_effector(
        node_id=CHECKOUT_NODE,
        output_keys=["ws"],
        run_state={"ws": _packet()},
        base_path=universe.universe_dir,
        run_id="run-e2e-2",
        chain=second_chain,
        execute=WireWorker(origin),
    )
    assert second.get("error_kind") is None, second
    assert second["lease_generation"] == 2


# --------------------------------------------------------------------------
# 4. a node whose checkout never delivered
# --------------------------------------------------------------------------


def test_a_node_naming_a_checkout_that_never_delivered_fails_by_name(
    universe: Universe, chain: EffectChain
) -> None:
    from tinyassets import graph_compiler as gc
    from tinyassets.api.runs import _classify_run_error
    from tinyassets.branches import NodeDefinition

    node = NodeDefinition(
        node_id="build",
        display_name="Build",
        phase="draft",
        source_code="def run(state):\n    return {'ok': True}\n",
        output_keys=["ok"],
        workspace=CHECKOUT_NODE,
    )
    compiled = gc._build_source_code_node(
        node,
        event_sink=None,
        effect_chain=chain,          # nothing registered: the checkout failed
        ancestors={CHECKOUT_NODE},
    )
    with pytest.raises(gc.CodeNodeError, match="workspace not available") as raised:
        compiled({})

    classified = _classify_run_error(raised.value, "branch-e2e")
    assert classified["failure_class"] == "code_node_failed"
    assert classified["suggested_action"]


def test_a_compiled_workspace_node_runs_inside_the_lease(
    origin: Origin,
    universe: Universe,
    chain: EffectChain,
    fs_bridge,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The seam this module exists for: the CHAIN's mount and the SANDBOX's are
    different objects with the same name, and the compiler is where they meet.
    Before the fix this raised AttributeError on ``limits`` for every workspace
    node, and neither lane's own suite could see it - each tested with its own
    class. The launcher is injected here only because bwrap is not on this host;
    everything else is the shipping path."""
    from tinyassets import graph_compiler as gc
    from tinyassets import node_sandbox as ns
    from tinyassets.branches import NodeDefinition

    _fire(_packet(), universe=universe, chain=chain, worker=WireWorker(origin))
    mount = chain.workspace_mount(CHECKOUT_NODE)
    assert mount is not None

    seen: dict[str, Any] = {}

    def _launcher(sandbox_mount):
        seen["bind"] = sandbox_mount.bind_source
        seen["roots"] = sandbox_mount.allowed_roots
        seen["pass_fds"] = sandbox_mount.pass_fds
        # A plain child performs no mount, so it runs against the path; what is
        # under test here is what the COMPILER handed over.
        return PlainSubprocessLauncher(workspace_bind=str(mount.bind_source))

    monkeypatch.setattr(ns, "WORKSPACE_LAUNCHER_FACTORY", _launcher)

    node = NodeDefinition(
        node_id="build",
        display_name="Build",
        phase="draft",
        source_code="def run(state):\n    return {'ok': ws.read('README.md')}\n",
        output_keys=["ok"],
        workspace=CHECKOUT_NODE,
    )
    compiled = gc._build_source_code_node(
        node,
        event_sink=None,
        effect_chain=chain,
        ancestors={CHECKOUT_NODE},
        base_path=universe.universe_dir,
    )
    state = compiled({})
    assert state["ok"] == origin.readme

    if POSIX:
        # The descriptor form: the bind is the handle the checkout opened, the
        # child is told to inherit it, and no root vouches for a string that is
        # never resolved. A launcher built without pass_fds would leave bwrap
        # resolving /proc/self/fd/<n> in a process that does not hold <n>.
        assert seen["bind"] == f"/proc/self/fd/{mount.repo_fd}"
        assert seen["pass_fds"] == (mount.repo_fd,)
        assert seen["roots"] == ()
    else:
        # No dir_fd on this host, so the path form - and THEN the roots matter,
        # derived the way the adapter derives them or a real bwrap would refuse
        # the bind it was just given.
        assert seen["bind"] == str(mount.bind_source)
        assert seen["pass_fds"] == ()
        assert seen["roots"] == (
            str(universe.data_root / "scratch"),
            str(universe.universe_dir / "workspaces"),
        )


# --------------------------------------------------------------------------
# 5. no consent, no lease
# --------------------------------------------------------------------------


def test_a_checkout_without_its_consent_creates_no_lease(
    origin: Origin, tmp_path: Path, fs_bridge
) -> None:
    universe = _make_universe(tmp_path, consents=("push", "provision"))
    chain = EffectChain(
        run_id=RUN_ID, base_path=str(universe.data_root), universe_id=UNIVERSE
    )
    worker = WireWorker(origin)
    result = _fire(_packet(), universe=universe, chain=chain, worker=worker)

    assert result["error_kind"] == "missing_consent", result
    assert result["consent"] == "workspace_checkout"
    assert worker.requests == [], "the wire was touched before the gate"
    assert _lease_rows(universe) == []
    assert chain.workspace_mount(CHECKOUT_NODE) is None
    assert list(universe.pool_root.iterdir()) == []


def test_a_checkout_without_the_read_scope_creates_no_lease(
    origin: Origin, tmp_path: Path, fs_bridge
) -> None:
    universe = _make_universe(tmp_path, scopes=(f"git_write:{REPO}",))
    chain = EffectChain(
        run_id=RUN_ID, base_path=str(universe.data_root), universe_id=UNIVERSE
    )
    worker = WireWorker(origin)
    result = _fire(_packet(), universe=universe, chain=chain, worker=worker)

    assert result["error_kind"] == "scope_not_granted", result
    assert worker.requests == []
    assert _lease_rows(universe) == []


# --------------------------------------------------------------------------
# 6. the token never comes back out
# --------------------------------------------------------------------------


def _files_under(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [path for path in root.rglob("*") if path.is_file()]


@pytest.mark.skipif(
    not POSIX,
    reason=(
        "ws.bundle shells out to a BARE git, which resolves only through "
        "execvp's CS_PATH fallback; the sandbox child is given no PATH"
    ),
)
def test_the_token_appears_in_no_evidence_no_log_and_no_file(
    origin: Origin,
    universe: Universe,
    chain: EffectChain,
    fs_bridge,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """The credential is resolved for real on the worker leg, so this is the
    live question: does any surface between there and the caller carry it?"""
    caplog.set_level(logging.DEBUG)
    worker = WireWorker(origin)
    checkout = _fire(_packet(), universe=universe, chain=chain, worker=worker)
    mount = chain.workspace_mount(CHECKOUT_NODE)
    assert mount is not None

    result = _run_in_workspace(
        mount,
        "def run(state):\n"
        "    ws.write('README.md', 'token hunt\\n')\n"
        "    base = [GIT, '-c', 'user.email=n@t.test', '-c', 'user.name=n']\n"
        "    ws.run(base + ['add', 'README.md'])\n"
        "    ws.run(base + ['commit', '-m', 'hunt'])\n"
        "    sha = ws.run([GIT, 'rev-parse', 'HEAD'])['stdout_tail'].strip()\n"
        "    return {'result': {'sha': sha, 'bundle': ws.bundle(sha)}}\n",
    )
    assert result.success, getattr(result, "error", None)
    sha = result.output_state["result"]["sha"]
    push = _fire(
        _packet(op="push", commit_sha=sha, branch_slug="hunt", workspace=CHECKOUT_NODE),
        universe=universe,
        chain=chain,
        worker=worker,
        node_id="push-node",
    )

    assert worker.secrets_seen == [TOKEN, TOKEN], "the worker never saw the token"

    surfaces = {
        "checkout evidence": json.dumps(checkout),
        "push evidence": json.dumps(push),
        "node output": json.dumps(result.output_state),
        "node stderr": str(getattr(result, "stderr_tail", "") or result.stderr or ""),
        "node stdout": str(getattr(result, "stdout_tail", "") or result.stdout or ""),
        "log": caplog.text,
    }
    for name, text in surfaces.items():
        assert TOKEN not in text, f"the token reached the {name}"

    lease_root = Path(mount.bind_source).parent
    staging_root = universe.universe_dir / ".workspace-staging"
    scanned = 0
    for path in _files_under(lease_root) + _files_under(staging_root):
        scanned += 1
        if TOKEN.encode() in path.read_bytes():
            raise AssertionError(f"the token reached {path}")
    assert scanned > 0, "nothing was scanned; the paths moved"


# --------------------------------------------------------------------------
# what the seam still needs from the daemon
# --------------------------------------------------------------------------


def test_the_startup_reconciler_creates_the_pool_root_a_fresh_host_lacks(
    origin: Origin, tmp_path: Path, fs_bridge
) -> None:
    """Inverted once ``ensure_workspace_reconciled`` gained the creator.

    The pool module creates no directories and the real ``open_dir_nofollow``
    refuses a missing parent, so on a fresh host the FIRST checkout used to
    fail - and the adapter's own suite could not see it, because its injected
    helper makes the directory itself. The reconciler now creates
    ``<data>/scratch`` (``base_path.parent / "scratch"``) at 0o700, and a
    checkout on a host that has never had one succeeds.
    """
    universe = _make_universe(tmp_path)
    shutil.rmtree(universe.pool_root)
    assert not universe.pool_root.exists()

    created = runs_module._ensure_scratch_root(universe.universe_dir)
    assert created == universe.pool_root
    assert universe.pool_root.is_dir()
    if POSIX:
        mode = stat.S_IMODE(os.stat(universe.pool_root).st_mode)
        assert mode == 0o700, f"{mode:#o}"

    # And the checkout that used to fail on a fresh host now completes - the
    # adapter reaches the reconciler before it admits anything.
    shutil.rmtree(universe.pool_root)
    chain = EffectChain(
        run_id=RUN_ID, base_path=str(universe.data_root), universe_id=UNIVERSE
    )
    result = _fire(_packet(), universe=universe, chain=chain, worker=WireWorker(origin))
    assert result.get("error_kind") is None, result
    assert universe.pool_root.is_dir()


@pytest.mark.skipif(not POSIX, reason="the real handles are POSIX-only")
def test_the_lease_directory_is_private_to_this_user(
    origin: Origin, universe: Universe, chain: EffectChain
) -> None:
    """The real create_lease_dir makes it 0o700 under a no-follow handle; the
    injected helper in the adapter's suite makes it with the umask."""
    _fire(_packet(), universe=universe, chain=chain, worker=WireWorker(origin))
    mount = chain.workspace_mount(CHECKOUT_NODE)
    assert mount is not None
    lease_dir = Path(mount.bind_source).parent
    mode = stat.S_IMODE(os.stat(lease_dir).st_mode)
    assert mode & 0o077 == 0, f"lease directory is {mode:#o}"
    assert len(lease_dir.name) >= 16, "the lease name must be unguessable"


def test_the_pool_and_the_run_share_one_database(universe: Universe) -> None:
    """A seam that would be invisible until a release: the adapter's pool db and
    the run lifecycle's must be the same file, or the terminal write would owe
    an outbox nothing reads."""
    assert wse._pool_db(universe.universe_dir) == runs_module.runs_db_path(
        universe.universe_dir
    )
    assert workspace_pool.WORKSPACE_SINK if hasattr(workspace_pool, "WORKSPACE_SINK") else True
