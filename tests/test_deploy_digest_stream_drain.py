"""Digest resolution must drain the whole ``imagetools inspect`` stream.

Deploy run 35947947560 (2026-09-24 02:37Z) died in ``Resolve image tag ->
immutable digest`` with exit 255 and no output. The reproducible hazard on
that line is ``awk '/^Digest:/ {print $2; exit}'``: awk exits on the first
match and closes the pipe, so a producer that is still writing gets EPIPE /
SIGPIPE. Under ``set -euo pipefail`` the kill propagates into the ``$(...)``
assignment and the step aborts before the fail-closed digest check runs.

The fix keeps the first match but drains the stream:
``awk '/^Digest:/ && !seen {print $2; seen=1}'``.

These tests run the REAL awk program extracted from each workflow through a
real bash pipeline with a producer far larger than any pipe buffer, and keep
the old program in the suite as the executable spec of the hazard.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_WORKFLOWS = _REPO / ".github" / "workflows"
_SITES = {
    "deploy-prod": _WORKFLOWS / "deploy-prod.yml",
    "recovery-retag-image": _WORKFLOWS / "recovery-retag-image.yml",
}

OLD_PROGRAM = "/^Digest:/ {print $2; exit}"
NEW_PROGRAM = "/^Digest:/ && !seen {print $2; seen=1}"

FIRST_DIGEST = "sha256:" + "a" * 64
SECOND_DIGEST = "sha256:" + "b" * 64

# Roughly 2.8 MB across ~20k writes: far past the 64 KiB pipe buffer, so the
# producer cannot finish before the reader has consumed the Digest line.
_TRAILER_LINES = 20_000

_PRODUCER_FN = r"""
producer() {
  printf 'Name:      ghcr.io/x/tinyassets-daemon:tag\n'
  printf 'MediaType: application/vnd.oci.image.index.v1+json\n'
  printf 'Digest:    %s\n\n' "${FIRST_DIGEST}"
  # Give the reader time to exit before the bulk arrives (deterministic race).
  sleep 0.2
  printf 'Manifests:\n'
  i=0
  while [ "$i" -lt "${TRAILER_LINES}" ]; do
    printf '  Name:        ghcr.io/x/tinyassets-daemon:tag@sha256:%064d\n' "$i"
    printf '  MediaType:   application/vnd.oci.image.manifest.v1+json\n'
    printf '  Platform:    linux/amd64\n\n'
    i=$((i + 1))
  done
  echo "producer-finished" >&2
}
"""


def _bash() -> str:
    bash = None
    if sys.platform == "win32":
        git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
        if git_bash.exists():
            bash = str(git_bash)
    if bash is None:
        bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is unavailable")
    if sys.platform == "win32" and "system32" in bash.lower():
        # C:\Windows\System32\bash.exe is the WSL launcher, not a POSIX shell.
        pytest.skip("only the WSL launcher bash was found")
    return bash


def _run_bash(script: str, tmp_path: Path, **env: str) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "harness.sh"
    path.write_text(script, encoding="utf-8", newline="\n")
    merged = {
        **os.environ,
        "FIRST_DIGEST": FIRST_DIGEST,
        "SECOND_DIGEST": SECOND_DIGEST,
        "TRAILER_LINES": str(_TRAILER_LINES),
        **env,
    }
    return subprocess.run(
        [_bash(), path.as_posix()],
        text=True,
        capture_output=True,
        check=False,
        env=merged,
        timeout=120,
    )


def _digest_program(site: str) -> str:
    """The awk program each site pipes ``imagetools inspect`` into."""
    text = _SITES[site].read_text(encoding="utf-8")
    matches = re.findall(
        r"docker buildx imagetools inspect \"\$\{image\}:[^\"]+\"\s*\|\s*awk '([^']+)'",
        text,
    )
    assert len(matches) == 1, (
        f"{site}: expected exactly one digest-resolution awk site, found {matches!r}"
    )
    return matches[0]


# ---------------------------------------------------------------------------
# Both workflow sites carry the draining program and no early exit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("site", sorted(_SITES))
def test_site_uses_first_match_drain_program(site: str) -> None:
    assert _digest_program(site) == NEW_PROGRAM


@pytest.mark.parametrize("site", sorted(_SITES))
def test_site_has_no_early_exit_awk(site: str) -> None:
    text = _SITES[site].read_text(encoding="utf-8")
    assert OLD_PROGRAM not in text
    # No other awk program in the file may close a pipe early either.
    for program in re.findall(r"awk (?:-F\S+ )?'([^']+)'", text):
        assert not re.search(r"\bexit\b", program), f"{site}: early-exit awk program {program!r}"


# ---------------------------------------------------------------------------
# Real pipeline: old program kills the producer, new program drains it
# ---------------------------------------------------------------------------


def test_old_program_closes_pipe_and_kills_producer(tmp_path: Path) -> None:
    """Executable spec of the hazard. If this stops failing on a host, that
    host does not deliver SIGPIPE/EPIPE the way ubuntu runners do."""
    script = (
        "set -euo pipefail\n"
        + _PRODUCER_FN
        + f"digest=\"$(producer | awk '{OLD_PROGRAM}')\"\n"
        + 'echo "digest=${digest}"\n'
    )
    result = _run_bash(script, tmp_path)
    assert result.returncode != 0, result
    assert "producer-finished" not in result.stderr, result
    # set -e aborted the assignment: the digest never reached the validator.
    assert "digest=" not in result.stdout, result


@pytest.mark.parametrize("site", sorted(_SITES))
def test_new_program_drains_stream_and_returns_first_digest(site: str, tmp_path: Path) -> None:
    program = _digest_program(site)
    script = (
        "set -euo pipefail\n"
        + _PRODUCER_FN
        + f"digest=\"$(producer | awk '{program}')\"\n"
        + 'echo "digest=${digest}"\n'
    )
    result = _run_bash(script, tmp_path)
    assert result.returncode == 0, result
    assert "producer-finished" in result.stderr, result
    assert result.stdout.strip() == f"digest={FIRST_DIGEST}", result


def test_new_program_prints_only_the_first_top_level_digest(tmp_path: Path) -> None:
    """Two top-level Digest lines plus an indented one: exactly one line out,
    the first, so ``image_ref=${image}@${digest}`` can never carry two digests."""
    program = _digest_program("deploy-prod")
    script = (
        "set -euo pipefail\n"
        "stream() {\n"
        "  printf 'Name:      ghcr.io/x/tinyassets-daemon:tag\\n'\n"
        "  printf 'Digest:    %s\\n' \"${FIRST_DIGEST}\"\n"
        "  printf 'Manifests:\\n'\n"
        "  printf '  Digest:    %s\\n' \"${SECOND_DIGEST}\"\n"
        "  printf 'Digest:    %s\\n' \"${SECOND_DIGEST}\"\n"
        "}\n"
        f"stream | awk '{program}'\n"
    )
    result = _run_bash(script, tmp_path)
    assert result.returncode == 0, result
    assert result.stdout.splitlines() == [FIRST_DIGEST], result


# ---------------------------------------------------------------------------
# Fail-closed validation is preserved and still rejects bad digests
# ---------------------------------------------------------------------------

_VALIDATION_RE = re.compile(
    r'(if \[\[ ! "\$\{digest\}" =~ \^sha256:\[0-9a-f\]\{64\}\$ \]\]; then\n'
    r'\s*echo "::error::non-canonical image digest for \$\{image\}:\$\{tag\}"; exit 1\n'
    r"\s*fi\n)"
)


def _deploy_validation_block() -> str:
    text = _SITES["deploy-prod"].read_text(encoding="utf-8")
    match = _VALIDATION_RE.search(text)
    assert match is not None, "deploy-prod.yml lost its fail-closed digest check"
    return match.group(1)


def test_deploy_prod_validation_follows_digest_resolution() -> None:
    text = _SITES["deploy-prod"].read_text(encoding="utf-8")
    awk_at = text.index(NEW_PROGRAM)
    check_at = text.index('"${digest}" =~ ^sha256:[0-9a-f]{64}$')
    assert awk_at < check_at
    assert 'image_ref=${image}@${digest}' in text


def test_recovery_retag_still_compares_retagged_digest_to_source() -> None:
    text = _SITES["recovery-retag-image"].read_text(encoding="utf-8")
    assert '[[ "${retagged_digest}" == "${digest}" ]] ||' in text
    assert "retagged digest disagrees with immutable source" in text
    assert "--prefer-index=false" in text


@pytest.mark.parametrize(
    ("stream_lines", "expect_ok"),
    [
        pytest.param([f"Digest:    {FIRST_DIGEST}"], True, id="valid"),
        pytest.param(["Name: x", "MediaType: y"], False, id="missing-digest"),
        pytest.param(["Digest:    sha256:zz"], False, id="short-nonhex"),
        pytest.param(["Digest:    sha256:" + "A" * 64], False, id="uppercase-hex"),
        pytest.param(["Digest:    " + "c" * 64], False, id="no-algorithm-prefix"),
        pytest.param([f"  Digest:    {FIRST_DIGEST}"], False, id="indented-only"),
    ],
)
def test_deploy_prod_digest_check_fails_closed(
    stream_lines: list[str], expect_ok: bool, tmp_path: Path
) -> None:
    """Pipe a stream through the site's real awk program and then through the
    site's real validation block. Every non-canonical outcome must exit 1."""
    program = _digest_program("deploy-prod")
    body = "".join(f"  printf '%s\\n' '{line}'\n" for line in stream_lines)
    script = (
        "set -euo pipefail\n"
        'image="ghcr.io/x/tinyassets-daemon"; tag="deadbeefcafe"\n'
        "stream() {\n" + body + "}\n"
        f"digest=\"$(stream | awk '{program}')\"\n"
        + _deploy_validation_block()
        + 'echo "image_ref=${image}@${digest}"\n'
    )
    result = _run_bash(script, tmp_path)
    if expect_ok:
        assert result.returncode == 0, result
        assert result.stdout.strip() == f"image_ref=ghcr.io/x/tinyassets-daemon@{FIRST_DIGEST}"
    else:
        assert result.returncode == 1, result
        assert "non-canonical image digest" in result.stdout, result
        assert "image_ref=" not in result.stdout, result
