"""Dependency delivery tests; no package is installed or namespace executed."""

import hashlib
import io
import os
import stat
import subprocess
import tarfile
from pathlib import Path

import pytest

from scripts import ci_bwrap_dependency as delivery


def archive(*, mode=0o755, kind=tarfile.REGTYPE, pax=None, copies=1):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode="w") as package:
        for _ in range(copies):
            member = tarfile.TarInfo("./usr/bin/bwrap")
            member.mode, member.type = mode, kind
            member.pax_headers = pax or {}
            if member.isfile():
                member.size = 6
                package.addfile(member, io.BytesIO(b"binary"))
            else:
                member.linkname = "/bin/sh"
                package.addfile(member)
        # Package policy and an attempted traversal must never be extracted.
        for name in ("./usr/lib/sysctl.d/50-bubblewrap.conf", "../../outside", "postinst"):
            member = tarfile.TarInfo(name)
            member.size = 6
            package.addfile(member, io.BytesIO(b"policy"))
    return result.getvalue()


@pytest.mark.parametrize("kwargs", [
    {"mode": 0o4755}, {"mode": 0o2755}, {"mode": 0o777},
    {"kind": tarfile.SYMTYPE}, {"kind": tarfile.LNKTYPE},
    {"kind": tarfile.DIRTYPE}, {"pax": {"SCHILY.xattr.security.capability": "x"}},
    {"copies": 0}, {"copies": 2},
])
def test_nonordinary_executable_is_refused(kwargs):
    with pytest.raises(ValueError):
        delivery.executable_bytes(archive(**kwargs))


def fake_commands(monkeypatch, *, wrong_hash=False, probe_error=False):
    package_bytes = b"authenticated test package"
    monkeypatch.setattr(delivery, "PACKAGE_SHA256", hashlib.sha256(package_bytes).hexdigest())
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[0] == "apt-get":
            Path(kwargs["cwd"]).joinpath("bubblewrap.deb").write_bytes(
                b"wrong" if wrong_hash else package_bytes,
            )
            return subprocess.CompletedProcess(argv, 0)
        if argv[:2] == ["dpkg-deb", "--fsys-tarfile"]:
            return subprocess.CompletedProcess(argv, 0, stdout=archive())
        assert Path(argv[0]).name == "bwrap"
        if probe_error:
            raise subprocess.CalledProcessError(1, argv, stderr=b"namespace denied")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(delivery.subprocess, "run", run)
    return calls


def test_only_plain_binary_delivered_without_install_or_host_policy_actions(tmp_path, monkeypatch):
    calls = fake_commands(monkeypatch)
    directory = delivery.prepare(tmp_path)
    binary = directory / "bwrap"
    assert list(tmp_path.iterdir()) == [directory]
    assert list(directory.iterdir()) == [binary]
    assert binary.read_bytes() == b"binary"
    assert stat.S_IMODE(binary.stat().st_mode) == 0o755
    assert binary.stat().st_uid == os.getuid()
    assert calls[0][0] == [
        "apt-get", "-o", "APT::Get::AllowUnauthenticated=false",
        "-o", "Acquire::AllowInsecureRepositories=false", "download", delivery.PACKAGE,
    ]
    assert calls[1][0][:2] == ["dpkg-deb", "--fsys-tarfile"]
    assert calls[2][0] == [str(binary), "--unshare-pid", "--bind", "/", "/", "--", "true"]
    assert len(calls) == 3
    assert all(kwargs["check"] is True and kwargs["timeout"] > 0 for _, kwargs in calls)


def test_unaudited_archive_never_reaches_extraction_or_probe(tmp_path, monkeypatch):
    calls = fake_commands(monkeypatch, wrong_hash=True)
    with pytest.raises(ValueError, match="audited archive"):
        delivery.prepare(tmp_path)
    assert len(calls) == 1
    assert list(tmp_path.iterdir()) == []


def test_denied_probe_removes_binary_and_never_publishes_path(tmp_path, monkeypatch, capsys):
    calls = fake_commands(monkeypatch, probe_error=True)
    monkeypatch.setattr("sys.argv", ["ci_bwrap_dependency", "--runner-temp", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        delivery.main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "namespace denied" in output.err
    assert list(tmp_path.iterdir()) == []
    assert len(calls) == 3, "no privileged fallback after the existing policy denies the probe"


def test_download_failure_is_terminal(tmp_path, monkeypatch):
    def fail(argv, **kwargs):
        raise subprocess.CalledProcessError(100, argv, stderr=b"package unavailable")

    monkeypatch.setattr(delivery.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        delivery.prepare(tmp_path)
    assert list(tmp_path.iterdir()) == []
