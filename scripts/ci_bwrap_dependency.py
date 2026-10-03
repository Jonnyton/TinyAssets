#!/usr/bin/env python3
"""Deliver only audited, unprivileged bwrap bytes; never install its package.

Ubuntu's package postinst applies a sysctl. CI must not execute that script or
install its policy files. Download through apt's authenticated indexes, check
the audited archive hash, and copy only its ordinary executable into a fresh
job-owned directory. Existing host policy remains authoritative: a failed
namespace probe stops setup without publishing the directory on PATH.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

PACKAGE = "bubblewrap=0.9.0-1ubuntu0.3"
PACKAGE_SHA256 = "2461f1beee9cb04c8942739fe1a2b37e7b7c2a3d518f0779dc75f9245baa3094"


def executable_bytes(archive: bytes) -> bytes:
    """Read one regular 0755 executable; do not extract any archive paths."""
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as package:
        entries = [m for m in package.getmembers()
                   if m.name in ("./usr/bin/bwrap", "usr/bin/bwrap")]
        if len(entries) != 1:
            raise ValueError("package must contain exactly one bwrap executable")
        entry = entries[0]
        if not entry.isfile() or entry.mode != 0o755 or entry.pax_headers:
            raise ValueError("bwrap must be a plain 0755 file without extra attributes")
        source = package.extractfile(entry)
        if source is None:
            raise ValueError("bwrap executable is missing")
        return source.read()


def prepare(runner_temp: Path) -> Path:
    """Return a PATH directory only after unchanged host policy permits bwrap."""
    runner_temp = runner_temp.resolve(strict=True)
    destination = Path(tempfile.mkdtemp(prefix="ta-bwrap-bin-", dir=runner_temp))
    try:
        with tempfile.TemporaryDirectory(prefix="ta-bwrap-download-", dir=runner_temp) as download:
            subprocess.run(
                ["apt-get", "-o", "APT::Get::AllowUnauthenticated=false",
                 "-o", "Acquire::AllowInsecureRepositories=false", "download", PACKAGE],
                cwd=download, check=True, capture_output=True, timeout=120,
            )
            packages = list(Path(download).glob("*.deb"))
            if len(packages) != 1:
                raise ValueError("apt did not deliver exactly one package")
            package = packages[0]
            if hashlib.sha256(package.read_bytes()).hexdigest() != PACKAGE_SHA256:
                raise ValueError("bubblewrap package differs from the audited archive")
            archive = subprocess.run(
                ["dpkg-deb", "--fsys-tarfile", str(package)],
                check=True, capture_output=True, timeout=30,
            ).stdout
            binary = destination / "bwrap"
            with binary.open("xb") as output:
                output.write(executable_bytes(archive))
            binary.chmod(0o755)
        # Same unprivileged PID-namespace probe as the preview containment tests.
        # No sudo, profile loading, capabilities, or security-setting fallback.
        subprocess.run(
            [str(binary), "--unshare-pid", "--bind", "/", "/", "--", "true"],
            check=True, capture_output=True, timeout=10,
        )
        return destination
    except BaseException:
        shutil.rmtree(destination)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-temp", type=Path, required=True)
    args = parser.parse_args()
    try:
        directory = prepare(args.runner_temp)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", None) or getattr(exc, "stdout", None) or str(exc)
        if isinstance(detail, bytes):
            detail = detail.decode(errors="replace")
        parser.exit(1, f"bwrap dependency setup failed; host policy unchanged: {detail}\n")
    # The workflow appends stdout to GITHUB_PATH; never emit a path on failure.
    print(os.fspath(directory))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
