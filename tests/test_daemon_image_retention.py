"""No real registry, Docker host, image removal, or production access."""

import hashlib
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts import daemon_image_retention as retention


def identity(number):
    return "sha256:" + f"{number:064x}"


def reference(number):
    return retention.REPOSITORY + "@" + identity(number)


@pytest.fixture
def inventory():
    images = [
        dict(
            Id=identity(n),
            Created=f"2026-09-{n:02}T00:00:00Z",
            RepoDigests=[reference(n)],
            RepoTags=[],
        )
        for n in range(1, 11)
    ]
    daemon = dict(Name="/tinyassets-daemon", Image=identity(9), State={"Running": True})
    return images, [daemon], daemon, {"rollback_target": ""}


def select(inventory, configured=reference(9)):
    images, containers, daemon, receipt = inventory
    return retention.candidates(images, containers, daemon, configured, receipt)


def test_protects_current_two_older_newer_and_container_references(inventory):
    inventory[1].append(dict(Image=identity(1), State={"Running": False}))
    inventory[3]["rollback_target"] = reference(2)
    rows, protected = select(inventory, reference(3))
    assert [r["ref"] for r in rows] == [reference(n) for n in (4, 5, 6)]
    assert set(protected) == {identity(n) for n in (1, 2, 3, 7, 8, 9, 10)}


@pytest.mark.parametrize("mutation", ["tag", "foreign", "multi"])
def test_aliases_exclude_candidate(inventory, mutation):
    row = inventory[0][0]
    if mutation == "tag":
        row["RepoTags"] = [retention.REPOSITORY + ":old"]
    elif mutation == "foreign":
        row["RepoDigests"] = ["other.example/image@" + identity(1)]
    else:
        row["RepoDigests"].append(reference(11))
    assert reference(1) not in [r["ref"] for r in select(inventory)[0]]


@pytest.mark.parametrize("mutation", ["timestamp", "current", "container", "rollback"])
def test_incomplete_protection_refuses(inventory, mutation):
    if mutation == "timestamp":
        inventory[0][0]["Created"] = "invalid"
    elif mutation == "current":
        inventory[2]["Image"] = identity(99)
    elif mutation == "container":
        inventory[1].append(dict(Image=identity(99)))
    else:
        inventory[3]["rollback_target"] = reference(99)
    with pytest.raises(retention.Refusal):
        select(inventory)


@pytest.mark.parametrize("configured", ["", "not-in-inventory", None])
def test_missing_configured_reference_refuses(inventory, configured):
    with pytest.raises(retention.Refusal):
        select(inventory, configured)


@pytest.mark.parametrize("total,free,expected", [(100, 19, 81), (100, 0, 100), (100, 100, 0)])
def test_pressure_uses_available(total, free, expected):
    assert retention.pressure(
        "unused", lambda p: SimpleNamespace(total=total, free=free)
    ) == pytest.approx(expected)


@pytest.mark.parametrize(
    "total,free", [(0, 0), (100, -1), (100, 101), (float("inf"), 1), (100, float("nan"))]
)
def test_bad_pressure_refuses(total, free):
    with pytest.raises(retention.Refusal):
        retention.pressure("unused", lambda p: SimpleNamespace(total=total, free=free))


def test_store_mapping_requires_evidence(tmp_path):
    info = dict(Driver="overlay2", DockerRootDir=str(tmp_path))
    assert retention.storage_path(info) == str(tmp_path)
    info.update(Driver="overlayfs", DriverStatus=[["driver-type", "io.containerd.snapshotter.v1"]])
    with pytest.raises(retention.Refusal, match="filesystem"):
        retention.storage_path(info)
    assert retention.storage_path(info, str(tmp_path)) == str(tmp_path)
    with pytest.raises(retention.Refusal, match="unknown_image_store"):
        retention.storage_path(dict(Driver="unknown"), str(tmp_path))


class FakeDocker:
    def __init__(self, inventory, root):
        self.data = inventory
        self.calls = []
        self.deadline = float("inf")
        self.before_inventory = lambda: None
        self.root = root

    def json(self, *args):
        return dict(
            Driver="overlay2", DockerRootDir=str(self.root), OSType="linux", Architecture="x86_64"
        )

    def inventory(self):
        self.before_inventory()
        return deepcopy(self.data[:2])

    def command(self, *args):
        assert args[:2] == ("image", "rm")
        assert len(args) == 3 and retention.immutable(args[2])
        self.calls.append(args)
        self.data[0][:] = [row for row in self.data[0] if args[2] not in row["RepoDigests"]]


def runner(inventory, tmp_path, **kwargs):
    docker = FakeDocker(inventory, tmp_path)
    state = dict(locked=False, verified=[])

    @contextmanager
    def locker():
        state["locked"] = True
        try:
            yield
        finally:
            state["locked"] = False

    def verify(choice, platform):
        assert not state["locked"]
        assert platform == ("linux", "amd64")
        state["verified"].append(choice)

    options = dict(
        dry_run=False,
        environ={"TINYASSETS_IMAGE": reference(9)},
        docker=docker,
        registry=SimpleNamespace(verify=verify),
        locker=locker,
        receipt_reader=lambda d, c: (inventory[2], inventory[3]),
        config_reader=lambda: reference(9),
        measure=lambda p: 90,
    )
    options.update(kwargs)
    return docker, state, options


def test_no_more_than_four_nonforce_immutable_removals(inventory, tmp_path):
    docker, state, options = runner(inventory, tmp_path)
    report = retention.retain(**options)
    assert len(docker.calls) == 4
    assert report["status"] == "pressure_unmet"
    assert len(state["verified"]) == 4


def test_low_watermark_stops_after_first_removal(inventory, tmp_path):
    readings = iter([90, 90, 74, 74])
    docker, _, options = runner(inventory, tmp_path, measure=lambda p: next(readings))
    report = retention.retain(**options)
    assert len(docker.calls) == 1
    assert report["status"] == "pressure_relieved"


def test_dry_run_never_removes(inventory, tmp_path):
    docker, _, options = runner(inventory, tmp_path, dry_run=True)
    assert retention.retain(**options)["status"] == "dry_run"
    assert docker.calls == []


def test_below_threshold_does_not_verify_or_lock(inventory, tmp_path):
    docker, state, options = runner(inventory, tmp_path, measure=lambda p: 84.9)
    assert retention.retain(**options)["status"] == "below_threshold"
    assert not docker.calls and not state["verified"]


def test_new_stopped_reference_is_rechecked(inventory, tmp_path):
    docker, state, options = runner(inventory, tmp_path)

    def race():
        if state["locked"]:
            inventory[1].append(dict(Image=identity(1)))

    docker.before_inventory = race
    report = retention.retain(**options)
    assert reference(1) not in report["removed"]


def test_registry_failure_causes_zero_removal(inventory, tmp_path):
    docker, _, options = runner(inventory, tmp_path)

    def unavailable(*args):
        raise retention.Refusal("registry_unavailable")

    options["registry"] = SimpleNamespace(verify=unavailable)
    with pytest.raises(retention.Refusal):
        retention.retain(**options)
    assert not docker.calls


def test_locked_deadline_is_at_most_sixty_seconds(inventory, tmp_path):
    clock = [0]
    docker, state, options = runner(inventory, tmp_path, clock=lambda: clock[0])

    def stalled():
        if state["locked"]:
            assert docker.deadline == 60
            clock[0] = 61
            raise retention.Refusal("budget_expired")

    docker.before_inventory = stalled
    with pytest.raises(retention.Refusal):
        retention.retain(**options)
    assert not docker.calls and not state["locked"]


@pytest.mark.skipif(os.name != "posix", reason="real advisory lock needs Linux oracle")
@pytest.mark.parametrize("which", [0, 1])
def test_real_other_process_lock_blocks_retention(tmp_path, which):
    paths = [tmp_path / "fence.lock", tmp_path / "mutation.lock"]
    source = (
        "import fcntl,sys; f=open(sys.argv[1],'w'); fcntl.flock(f,fcntl.LOCK_EX); "
        "print('ready',flush=True); sys.stdin.read()"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", source, str(paths[which])],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout.readline().strip() == "ready"
        with pytest.raises(retention.Refusal, match="busy"):
            with retention.locks(paths, tmp_path / "state"):
                pytest.fail("entered locked section")
    finally:
        child.communicate("", timeout=5)


@pytest.mark.skipif(os.name != "posix", reason="real advisory lock needs Linux oracle")
def test_any_fence_state_refuses(tmp_path):
    state = tmp_path / "state"
    state.write_text('{"phase":"restored"}')
    with pytest.raises(retention.Refusal, match="fence_present"):
        with retention.locks([tmp_path / "one", tmp_path / "two"], state):
            pytest.fail("entered fenced section")


def registry_fixture(index=True):
    config = json.dumps(dict(os="linux", architecture="amd64")).encode()

    def digest(raw):
        return "sha256:" + hashlib.sha256(raw).hexdigest()

    config_id = digest(config)
    layer = identity(42)
    manifest = json.dumps(dict(config=dict(digest=config_id), layers=[dict(digest=layer)])).encode()
    manifest_id = digest(manifest)
    root = (
        json.dumps(
            dict(
                manifests=[
                    dict(digest=manifest_id, platform=dict(os="linux", architecture="amd64"))
                ]
            )
        ).encode()
        if index
        else manifest
    )
    root_id = digest(root)
    registry = retention.Registry(999999999)
    blobs = {root_id: root, manifest_id: manifest, config_id: config, layer: b"layer"}
    calls = []

    def request(url, **kwargs):
        key = url.rsplit("/", 1)[1]
        calls.append((key, kwargs.get("head", False)))
        if key not in blobs:
            raise retention.Refusal("registry_unavailable")
        return blobs[key]

    registry.request = request
    candidate = dict(ref=retention.REPOSITORY + "@" + root_id, image_id=config_id)
    return registry, candidate, blobs, calls


@pytest.mark.parametrize("index", [True, False])
@pytest.mark.parametrize("id_kind", ["config", "root"])
def test_registry_verifies_hashes_platform_and_every_blob(index, id_kind):
    registry, candidate, _, calls = registry_fixture(index)
    if id_kind == "root":
        candidate["image_id"] = candidate["ref"].split("@")[1]
    registry.verify(candidate, ("linux", "amd64"))
    assert (identity(42), True) in calls


@pytest.mark.parametrize("failure", ["hash", "missing", "local", "platform"])
def test_registry_negative_evidence_refuses(failure):
    registry, candidate, blobs, _ = registry_fixture()
    if failure == "hash":
        blobs[candidate["ref"].split("@")[1]] += b" "
    elif failure == "missing":
        del blobs[identity(42)]
    elif failure == "local":
        candidate["image_id"] = identity(99)
    platform = ("linux", "arm64") if failure == "platform" else ("linux", "amd64")
    with pytest.raises(retention.Refusal):
        registry.verify(candidate, platform)


def test_registry_redirect_never_sends_bearer_to_cdn():
    import urllib.request

    req = urllib.request.Request("https://ghcr.io/blob", headers={"Authorization": "Bearer SECRET"})
    redirect = retention.SafeRedirect()
    target = redirect.redirect_request(
        req, None, 302, "", {}, "https://pkg-containers.githubusercontent.com/blob"
    )
    assert not target.has_header("Authorization")
    with pytest.raises(retention.Refusal):
        redirect.redirect_request(req, None, 302, "", {}, "https://evil.example/blob")


def test_configuration_is_reread_under_lock(inventory, tmp_path):
    docker, state, options = runner(inventory, tmp_path)
    options["config_reader"] = lambda: reference(1) if state["locked"] else reference(9)
    result = retention.retain(**options)
    assert reference(1) not in result["removed"]
    assert all(choice["ref"] != reference(1) for choice in result["selected"])


@pytest.mark.skipif(os.name != "posix", reason="production nofollow file reads require Linux")
@pytest.mark.parametrize(
    "value", [reference(9), "'" + reference(9) + "'", '"' + reference(9) + '"']
)
def test_configuration_reader_extracts_only_exact_key(tmp_path, value):
    path = tmp_path / "env"
    path.write_text("PRIVATE_TOKEN=secret\nTINYASSETS_IMAGE=" + value + "\n")
    assert retention.read_configured_image(path) == reference(9)


@pytest.mark.skipif(os.name != "posix", reason="production nofollow file reads require Linux")
@pytest.mark.parametrize(
    "contents", ["", "TINYASSETS_IMAGE=\n", "TINYASSETS_IMAGE=x\nTINYASSETS_IMAGE=y\n"]
)
def test_missing_duplicate_empty_config_refuses(tmp_path, contents):
    path = tmp_path / "env"
    path.write_text(contents)
    with pytest.raises(retention.Refusal):
        retention.read_configured_image(path)


@pytest.mark.skipif(os.name != "posix", reason="production nofollow file reads require Linux")
def test_symlink_fifo_and_oversized_files_are_refused(tmp_path):
    path = tmp_path / "real"
    path.write_text("large")
    with pytest.raises(retention.Refusal, match="oversize"):
        retention.read_regular(path, 1)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(OSError):
        retention.read_regular(link, 10)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(retention.Refusal, match="not_regular"):
        retention.read_regular(fifo, 10)


@pytest.mark.skipif(os.name != "posix", reason="production nofollow file reads require Linux")
@pytest.mark.parametrize(
    "fault", ["none", "missing", "invalid", "rollback_missing", "override", "mount"]
)
def test_receipt_has_one_authoritative_volume_location(tmp_path, fault):
    path = tmp_path / "release-state.json"
    path.write_text(json.dumps(dict(rollback_target="")))
    daemon = dict(
        Name="/tinyassets-daemon",
        State={"Running": True},
        Config={"Env": []},
        Mounts=[
            dict(Destination="/data", Type="volume", Name="tinyassets-data", Source=str(tmp_path))
        ],
    )
    if fault == "missing":
        path.unlink()
    elif fault == "invalid":
        path.write_text("invalid")
    elif fault == "rollback_missing":
        path.write_text("{}")
    elif fault == "override":
        daemon["Config"]["Env"] = ["TINYASSETS_RELEASE_STATE_PATH=/other"]
    elif fault == "mount":
        daemon["Mounts"][0]["Name"] = "other"
    docker = SimpleNamespace(json=lambda *args: [dict(Mountpoint=str(tmp_path))])
    if fault == "none":
        assert retention.read_receipt(docker, [daemon])[1] == dict(rollback_target="")
    else:
        with pytest.raises(retention.Refusal):
            retention.read_receipt(docker, [daemon])


def test_docker_deadline_never_starts_an_expired_command():
    calls = []
    docker = retention.Docker(1, clock=lambda: 2, runner=lambda *a, **k: calls.append(a))
    with pytest.raises(retention.Refusal, match="budget_expired"):
        docker.command("image", "rm", reference(1))
    assert not calls


def test_docker_timeout_is_bounded_by_remaining_budget():
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs["timeout"]))
        return SimpleNamespace(returncode=0, stdout="")

    docker = retention.Docker(5, clock=lambda: 2, runner=run)
    docker.command("image", "rm", reference(1))
    assert calls == [(["docker", "image", "rm", reference(1)], 3)]


def test_cli_unknown_error_never_echoes_credentials(monkeypatch, capsys):
    def fail(**kwargs):
        raise OSError("SECRET")

    monkeypatch.setattr(retention, "retain", fail)
    assert retention.main([]) == 2
    assert "SECRET" not in capsys.readouterr().out
