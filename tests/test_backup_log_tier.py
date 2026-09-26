"""Tests for the nightly log tier: scripts/backup_log_tier.py + redact_log_bundle.py.

The bundle these build leaves the droplet (GitHub release assets, see
deploy/backup.sh section 5), so the load-bearing assertion is the negative one:
a token-shaped string present in the journal is absent from the tarball.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import backup_log_tier  # noqa: E402
from redact_log_bundle import MAX_LINE_CHARS, REDACTED, redact_line  # noqa: E402

LOG_TIER_PY = REPO / "scripts" / "backup_log_tier.py"
REDACT_PY = REPO / "scripts" / "redact_log_bundle.py"


# ---------------------------------------------------------------------------
# redact_log_bundle — shape coverage
# ---------------------------------------------------------------------------


def _shaped(prefix: str, *parts: str) -> str:
    """Assemble a token-shaped string at runtime.

    These are invented values, but a convincing fake is exactly what a secret
    scanner is built to catch: GitHub push protection rejected this file on its
    first push over the Slack literal below. Joining the pieces here keeps the
    shape the redactor must match without putting a matching literal in the
    source -- and whitelisting a fake through the unblock URL would train the
    next reader to click it for a real one.
    """
    return prefix + "".join(parts)


_GH_FAKE = _shaped("ghp", "_AAAABBBBCCCCDDDD", "EEEEFFFFGGGG1234")


@pytest.mark.parametrize(
    "secret",
    [
        _shaped("sk-", "ant-api03-", "AAAABBBBCCCCDDDD", "EEEEFFFF"),
        _shaped("sk-", "or-v1-0123456789abcdef", "0123456789abcdef"),
        _shaped("ghp", "_AAAABBBBCCCCDDDD", "EEEEFFFFGGGG1234"),
        _shaped("gho", "_AAAABBBBCCCCDDDD", "EEEEFFFFGGGG1234"),
        _shaped("ghs", "_AAAABBBBCCCCDDDD", "EEEEFFFFGGGG1234"),
        _shaped("github", "_pat_11ABCDEFG0", "AAAABBBBCCCCDDDD_EEEEFFFF"),
        _shaped("xox", "b-1234567890-1234567890123-", "AbCdEfGhIjKlMnOpQrStUvWx"),
        _shaped("xapp", "-1-A012BCDEFGH-1234567890123-", "abcdef0123456789"),
        _shaped("eyJ", "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.", "eyJzdWIiOiIxIn0.sig"),
        _shaped("AKIA", "IOSFODNN7", "EXAMPLE"),
    ],
)
def test_redacts_every_token_shape(secret):
    line = f"2026-09-26T01:08:00.123456+0000 daemon: using {secret} for the turn"
    scrubbed = redact_line(line)
    assert secret not in scrubbed, f"{secret!r} survived redaction"
    assert REDACTED in scrubbed
    # Context has to survive, or the bundle is useless for the investigation it
    # exists to serve.
    assert "daemon: using" in scrubbed
    assert "2026-09-26T01:08:00.123456+0000" in scrubbed


@pytest.mark.parametrize(
    "line",
    [
        "Authorization: Bearer abc123def456",
        "authorization:Token qwertyuiopasdfgh",
        "git clone https://user:" + _GH_FAKE + "@github.com/x/y",
        'CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoiYiJ9ZZZZZZZZZZ',
        'BETTERSTACK_SOURCE_TOKEN="s3cr3tvalue12345"',
        "{\"api_key\": \"abcdefghijklmnop\", \"model\": \"opus\"}",
        "password = hunter2hunter2",
        "GH_TOKEN=" + _GH_FAKE,
    ],
)
def test_redacts_credential_carrying_constructs(line):
    scrubbed = redact_line(line)
    assert REDACTED in scrubbed, f"nothing redacted in {line!r}"
    for token in ("abc123def456", "qwertyuiopasdfgh", "s3cr3tvalue12345",
                  "abcdefghijklmnop", "hunter2hunter2"):
        assert token not in scrubbed


def test_redaction_is_idempotent():
    once = redact_line("Authorization: Bearer abc123def456xyz")
    assert redact_line(once) == once


def test_ordinary_lines_are_untouched():
    """A redactor that eats normal lines destroys the evidence instead of the
    secret. These are real shapes from the daemon's own output."""
    for line in (
        "2026-09-26T01:08:00.123456+0000 converse: learning 3 facts",
        "latency_ms=1841 attempt=2 provider=openrouter",
        "graph_id=g-0193ac model=claude-opus-5 rounds=4",
        "GET /mcp 200 in 41ms",
        "sha256:7a81fdd62e056321055a9e4bdec4073d752ecf68f4c192e676b85001721523c2",
    ):
        assert redact_line(line) == line, line


def test_covers_the_canonical_secret_shapes():
    """This filter must be a SUPERSET of the in-process redactors.

    Two definitions of "what a secret looks like" already exist
    (``tinyassets.workspace_git.scrub_text`` and
    ``tinyassets.providers.codex_provider._SECRET_SHAPES``). This is a third
    copy, which is only safe while it is strictly stricter -- so assert that,
    rather than trusting three files to be edited together.
    """
    from tinyassets.providers.codex_provider import _SECRET_SHAPES
    from tinyassets.workspace_git import scrub_text

    # (probe, the substring that must NOT survive). Asserting on the VALUE and
    # not merely that the line CHANGED is the whole point: the first version of
    # this test accepted any change, so `password=alpha,beta` passing as
    # `password=[redacted],beta` looked redacted while disclosing `beta`
    # (cross-family review, output/codex-log-durability-review.md §4).
    probes = [
        ("https://u:secretpw@github.com/x/y", "secretpw"),
        ("Authorization: Bearer zzzzzzzzzzzz", "zzzzzzzzzzzz"),
        (_GH_FAKE, _GH_FAKE),
        (
            _shaped("github", "_pat_11ABCDEFG0", "AAAABBBBCCCCDDDD_EEEEFFFF"),
            _shaped("github", "_pat_11ABCDEFG0", "AAAABBBBCCCCDDDD_EEEEFFFF"),
        ),
        ("sk-abcdefghijkl", "sk-abcdefghijkl"),
        ("eyJhbGciOiJIUzI1NiJ9.payload.sig", "eyJhbGciOiJIUzI1NiJ9"),
        ("bearer sometokenvalue", "sometokenvalue"),
        ("token: abcdefghijklmnop", "abcdefghijklmnop"),
        ("api_key=abcdefghijklmnop", "abcdefghijklmnop"),
        ("secret = abcdefghijklmnop", "abcdefghijklmnop"),
        ("password:abcdefghijklmnop", "abcdefghijklmnop"),
    ]
    for probe, secret in probes:
        canonical_changed = (
            scrub_text(probe) != probe or _SECRET_SHAPES.sub("[redacted]", probe) != probe
        )
        assert canonical_changed, f"probe {probe!r} is not a canonical secret shape"
        scrubbed = redact_line(probe)
        assert secret not in scrubbed, (
            f"{secret!r} survives the log-bundle filter in {probe!r} -> "
            f"{scrubbed!r}; the in-process filters redact it"
        )


@pytest.mark.parametrize(
    "line, secret",
    [
        # The real collection path: Vector's console sink is `codec: json`
        # (deploy/vector.yaml), so a daemon line reaches the journal as an
        # ESCAPED JSON string. A pattern expecting a bare quote never fires.
        (
            '{"log": "{\\"api_key\\": \\"opaquevalue123456\\"}", "role":"daemon"}',
            "opaquevalue123456",
        ),
        # A comma-bearing value must go WHOLE. Stopping at the comma left
        # `password=[redacted],beta;gamma` -- redacted-looking, still disclosing.
        ("password=alpha,beta;gamma&delta", "beta"),
        # `_` is a word character, so a leading \b never matched here and the
        # whole key survived.
        ("prefix_sk-abcdefghijkl", "sk-abcdefghijkl"),
        # argv style, no separator at all.
        ("--password opaquevalue123456", "opaquevalue123456"),
        ("--api-key opaquevalue123456", "opaquevalue123456"),
        # Unescaped JSON, for completeness.
        ('{"api_key": "opaquevalue123456", "model": "opus"}', "opaquevalue123456"),
    ],
)
def test_the_four_reproduced_bypasses_stay_closed(line, secret):
    """Regression cover for the leaks a cross-family review reproduced.

    Every one of these passed the original test suite, because the planted
    fixtures were bare token shapes that a standalone rule catches, and nothing
    exercised a labelled value inside escaped JSON.
    """
    scrubbed = redact_line(line)
    assert secret not in scrubbed, f"{secret!r} survives in {scrubbed!r}"


@pytest.mark.parametrize(
    "line",
    [
        '{"log":"GET /mcp 200 in 41ms","role":"daemon"}',
        "latency_ms=1841 attempt=2 provider=openrouter",
        "graph_id=g-0193ac model=claude-opus-5 rounds=4",
        "2026-09-26T01:08:00.123456+0000 converse: learning 3 facts",
        "sha256:7a81fdd62e056321055a9e4bdec4073d752ecf68f4c192e676b85001721523c2",
    ],
)
def test_widening_the_value_terminator_did_not_start_eating_evidence(line):
    """The fix consumes more per match, so the opposite failure is now the risk:
    a redactor that swallows the context is as useless as one that leaks."""
    assert redact_line(line) == line


def test_long_line_is_truncated_not_dropped():
    line = "x" * (MAX_LINE_CHARS + 500)
    out = redact_line(line)
    assert len(out) < len(line)
    assert out.startswith("x" * 100)
    assert "truncated" in out


def test_redactor_runs_as_a_stdin_filter():
    proc = subprocess.run(
        [sys.executable, str(REDACT_PY)],
        input="keep me\nAuthorization: Bearer leakme123456\n",
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "keep me" in proc.stdout
    assert "leakme123456" not in proc.stdout


# ---------------------------------------------------------------------------
# backup_log_tier — bundle construction
# ---------------------------------------------------------------------------


class _FakeJournal:
    """Stands in for journalctl. Records the argv it was asked to run."""

    def __init__(self, output: str = "", returncode: int = 0, stderr: str = ""):
        self.output = output
        self.returncode = returncode
        self.stderr = stderr
        self.calls: list[list[str]] = []
        self.kwargs: list[dict] = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        self.kwargs.append(dict(kwargs))
        return subprocess.CompletedProcess(
            argv, self.returncode, self.output, self.stderr
        )


def _members(path: Path) -> dict[str, str]:
    with tarfile.open(path, "r:gz") as archive:
        out = {}
        for name in archive.getnames():
            handle = archive.extractfile(name)
            out[name] = handle.read().decode("utf-8") if handle else ""
        return out


def test_bundle_contains_redacted_lines_and_a_manifest(tmp_path):
    planted = "sk-ant-api03-PLANTEDSECRETVALUE0123456789"
    journal = _FakeJournal(
        output=(
            f"2026-09-26T01:08:00.123456+0000 daemon: key={planted}\n"
            "2026-09-26T01:08:01.000000+0000 daemon: latency_ms=1841\n"
        )
    )
    out = tmp_path / "tinyassets-logs-2026-09-26T03-00-00Z.tar.gz"

    code, report = backup_log_tier.build_bundle(
        out,
        sources=("container:tinyassets-logs",),
        since="3 days ago",
        binary=sys.executable,  # an existing binary, so the which() gate passes
        runner=journal,
    )

    assert code == 0, report
    members = _members(out)
    assert set(members) == {"manifest.tsv", "container-tinyassets-logs.log"}
    body = members["container-tinyassets-logs.log"]
    assert planted not in body, "planted token reached the shipped bundle"
    assert "latency_ms=1841" in body
    assert "2026-09-26T01:08:00.123456+0000" in body
    manifest = members["manifest.tsv"]
    assert "container:tinyassets-logs\tcontainer-tinyassets-logs.log\t2\tok" in manifest


def test_planted_token_is_absent_from_the_compressed_bytes(tmp_path):
    """Read the tarball as BYTES, not through the redactor's own view.

    A test that only inspects extracted text would still pass if the token
    leaked through a path the extraction does not cover (a file name, the
    manifest, an error message quoted from journalctl's stderr).
    """
    planted = _shaped("ghp", "_PLANTEDAAAABBBB", "CCCCDDDDEEEE1234")
    journal = _FakeJournal(output=f"daemon: cloning with {planted}\n")
    out = tmp_path / "bundle.tar.gz"

    code, _ = backup_log_tier.build_bundle(
        out,
        sources=("container:tinyassets-logs",),
        binary=sys.executable,
        runner=journal,
    )
    assert code == 0
    with tarfile.open(out, "r:gz") as archive:
        raw = b"".join(
            archive.extractfile(name).read()
            for name in archive.getnames()
            if archive.extractfile(name) is not None
        )
        raw += b"".join(name.encode() for name in archive.getnames())
    assert planted.encode() not in raw


def test_journalctl_stderr_is_redacted_into_the_manifest(tmp_path):
    planted = "sk-ant-api03-STDERRLEAK0123456789abcd"
    journal = _FakeJournal(returncode=1, stderr=f"failed match {planted}\n")
    out = tmp_path / "bundle.tar.gz"

    code, report = backup_log_tier.build_bundle(
        out,
        sources=("container:tinyassets-logs", "unit:tinyassets-daemon.service"),
        binary=sys.executable,
        runner=journal,
    )

    # Every source errored -> skipped tier, not a written bundle.
    assert code == 3
    assert planted not in "\n".join(report)
    assert not out.exists()


def test_container_source_matches_on_container_name(tmp_path):
    """CONTAINER_NAME is the match that spans past container recreates, which is
    the entire reason the journal is the durable home."""
    journal = _FakeJournal(output="line\n")
    backup_log_tier.build_bundle(
        tmp_path / "b.tar.gz",
        sources=("container:tinyassets-logs",),
        since="3 days ago",
        binary=sys.executable,
        runner=journal,
    )
    argv = journal.calls[0]
    assert "CONTAINER_NAME=tinyassets-logs" in argv
    assert "--since" in argv and "3 days ago" in argv
    # Microsecond timestamps: the 2026-09-26 investigation needed per-attempt
    # latency, which second-granularity output cannot supply.
    assert "--output=short-iso-precise" in argv
    assert "--no-pager" in argv


def test_unit_source_uses_the_unit_flag(tmp_path):
    journal = _FakeJournal(output="line\n")
    backup_log_tier.build_bundle(
        tmp_path / "b.tar.gz",
        sources=("unit:tinyassets-daemon.service",),
        binary=sys.executable,
        runner=journal,
    )
    argv = journal.calls[0]
    assert argv[-2:] == ["-u", "tinyassets-daemon.service"]


def test_missing_journalctl_is_a_skipped_tier_not_a_failure(tmp_path):
    code, report = backup_log_tier.build_bundle(
        tmp_path / "b.tar.gz",
        sources=("container:tinyassets-logs",),
        binary="journalctl-that-does-not-exist",
    )
    assert code == 3, report
    assert "journalctl not found" in " ".join(report)
    assert not (tmp_path / "b.tar.gz").exists()


def test_one_failing_source_still_ships_the_others(tmp_path):
    class Mixed(_FakeJournal):
        def __call__(self, argv, **kwargs):
            self.calls.append(list(argv))
            self.kwargs.append(dict(kwargs))
            if "-u" in argv:
                return subprocess.CompletedProcess(argv, 1, "", "no such unit")
            return subprocess.CompletedProcess(argv, 0, "kept line\n", "")

    out = tmp_path / "b.tar.gz"
    code, _ = backup_log_tier.build_bundle(
        out,
        sources=("container:tinyassets-logs", "unit:gone.service"),
        binary=sys.executable,
        runner=Mixed(),
    )
    assert code == 0
    members = _members(out)
    assert "kept line" in members["container-tinyassets-logs.log"]
    assert re.search(r"unit:gone\.service\t\S+\t0\terror:", members["manifest.tsv"])


def test_no_lines_anywhere_is_a_loud_skip_not_an_empty_bundle(tmp_path):
    """An empty bundle shipped nightly is indistinguishable from success, which
    is the failure the retired ship-logs timer had in the other direction."""
    out = tmp_path / "b.tar.gz"
    code, report = backup_log_tier.build_bundle(
        out,
        sources=("container:tinyassets-logs",),
        binary=sys.executable,
        runner=_FakeJournal(output=""),
    )
    assert code == 3
    assert "no log source produced any lines" in " ".join(report)
    assert not out.exists()


@pytest.mark.parametrize("sentinel", ["-- No entries --", "-- no entries --"])
def test_journalctl_no_entries_marker_is_not_data(tmp_path, sentinel):
    """journalctl writes `-- No entries --` to STDOUT and exits 0.

    Counted as a line it makes an empty journal report as a healthy source.
    Found by running against a real journalctl (WSL, 2026-09-26); a stubbed one
    returns clean output and never exposes it.
    """
    code, report = backup_log_tier.build_bundle(
        tmp_path / "b.tar.gz",
        sources=("container:tinyassets-logs",),
        binary=sys.executable,
        runner=_FakeJournal(output=sentinel + "\n"),
    )
    assert code == 3, f"sentinel counted as data: {report}"


def test_one_empty_source_is_recorded_beside_a_live_one(tmp_path):
    class Mixed(_FakeJournal):
        def __call__(self, argv, **kwargs):
            self.calls.append(list(argv))
            self.kwargs.append(dict(kwargs))
            payload = "-- No entries --\n" if "-u" in argv else "daemon: real line\n"
            return subprocess.CompletedProcess(argv, 0, payload, "")

    out = tmp_path / "b.tar.gz"
    code, _ = backup_log_tier.build_bundle(
        out,
        sources=("container:tinyassets-logs", "unit:quiet.service"),
        binary=sys.executable,
        runner=Mixed(),
    )
    assert code == 0
    manifest = _members(out)["manifest.tsv"]
    assert "unit:quiet.service\tunit-quiet.service.log\t0\tempty" in manifest
    assert "container:tinyassets-logs\tcontainer-tinyassets-logs.log\t1\tok" in manifest
    # The sentinel itself must not be in the shipped file.
    assert "No entries" not in _members(out)["unit-quiet.service.log"]


def test_boot_markers_are_kept_but_are_not_evidence(tmp_path):
    """`-- Reboot --` is context worth keeping; it is not a log line, so a
    bundle containing only markers is still an empty one."""
    code, _ = backup_log_tier.build_bundle(
        tmp_path / "b.tar.gz",
        sources=("container:tinyassets-logs",),
        binary=sys.executable,
        runner=_FakeJournal(output="-- Reboot --\n"),
    )
    assert code == 3

    out = tmp_path / "with-data.tar.gz"
    code, _ = backup_log_tier.build_bundle(
        out,
        sources=("container:tinyassets-logs",),
        binary=sys.executable,
        runner=_FakeJournal(output="-- Reboot --\ndaemon: real line\n"),
    )
    assert code == 0
    body = _members(out)["container-tinyassets-logs.log"]
    assert "-- Reboot --" in body
    assert "\t1\tok" in _members(out)["manifest.tsv"]


def test_max_bytes_keeps_the_newest_lines_and_says_so(tmp_path):
    """Which END the budget keeps decides whether the bundle is usable.

    journalctl emits oldest-first, so a head-first budget discards the most
    recent evidence — the lines an incident actually needs. Found by a
    cross-family review (output/codex-log-durability-review.md, closing note).
    """
    out = tmp_path / "b.tar.gz"
    journal = _FakeJournal(output="".join(f"line {i}\n" for i in range(5000)))
    code, _ = backup_log_tier.build_bundle(
        out,
        sources=("container:tinyassets-logs",),
        binary=sys.executable,
        max_bytes=200,
        runner=journal,
    )
    assert code == 0
    members = _members(out)
    body = members["container-tinyassets-logs.log"]
    assert "older lines dropped at 200 bytes" in body
    assert "\ttruncated" in members["manifest.tsv"]
    # The newest line is present and the oldest is gone — not the reverse.
    assert "line 4999" in body
    assert "line 0\n" not in body
    # And the kept lines are still in chronological order, not reversed.
    kept = [ln for ln in body.splitlines() if ln.startswith("line ")]
    assert kept == sorted(kept, key=lambda ln: int(ln.split()[1]))


def test_journalctl_is_bounded_in_lines_and_wall_clock(tmp_path):
    """This tier is the least valuable thing in a unit with TimeoutStartSec=30min,
    so it must not be able to spend that budget or that much memory."""
    journal = _FakeJournal(output="line\n")
    backup_log_tier.build_bundle(
        tmp_path / "b.tar.gz",
        sources=("container:tinyassets-logs",),
        binary=sys.executable,
        runner=journal,
    )
    argv = journal.calls[0]
    assert "--lines" in argv, "journalctl output is unbounded -> unbounded memory"
    assert argv[argv.index("--lines") + 1] == str(backup_log_tier.DEFAULT_MAX_LINES)
    assert journal.kwargs[0].get("timeout") == backup_log_tier.DEFAULT_TIMEOUT_SECONDS
    assert backup_log_tier.DEFAULT_TIMEOUT_SECONDS < 30 * 60


def test_a_hung_journalctl_is_a_skipped_tier_not_a_killed_backup(tmp_path):
    class Hanging(_FakeJournal):
        def __call__(self, argv, **kwargs):
            self.calls.append(list(argv))
            self.kwargs.append(dict(kwargs))
            raise subprocess.TimeoutExpired(argv, kwargs.get("timeout", 0))

    code, report = backup_log_tier.build_bundle(
        tmp_path / "b.tar.gz",
        sources=("container:tinyassets-logs",),
        binary=sys.executable,
        runner=Hanging(),
    )
    assert code == 3, report
    assert any("timeout" in line for line in report)
    assert not (tmp_path / "b.tar.gz").exists()


def test_unknown_source_kind_is_an_argument_error(tmp_path):
    code, report = backup_log_tier.build_bundle(
        tmp_path / "b.tar.gz",
        sources=("file:/var/log/syslog",),
        binary=sys.executable,
        runner=_FakeJournal(output=""),
    )
    assert code == 1
    assert "unknown source kind" in " ".join(report)


def test_default_sources_cover_the_vector_container(tmp_path):
    """The daemon's own lines reach the journal through the Vector sidecar's
    stdout, so `container:tinyassets-logs` is the source that carries them."""
    assert "container:tinyassets-logs" in backup_log_tier.DEFAULT_SOURCES
    assert backup_log_tier.DEFAULT_SINCE == "3 days ago"


def test_cli_writes_a_bundle(tmp_path):
    """End to end through argv, with a stub journalctl on disk."""
    stub = tmp_path / ("journalctl.bat" if sys.platform == "win32" else "journalctl")
    if sys.platform == "win32":
        stub.write_text("@echo daemon: latency_ms=1841\r\n", encoding="utf-8")
    else:
        stub.write_text(
            "#!/usr/bin/env bash\necho 'daemon: latency_ms=1841'\n", encoding="utf-8"
        )
        stub.chmod(0o755)
    out = tmp_path / "bundle.tar.gz"
    proc = subprocess.run(
        [
            sys.executable, str(LOG_TIER_PY),
            "--out", str(out),
            "--since", "3 days ago",
            "--source", "container:tinyassets-logs",
            "--journalctl", str(stub),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "latency_ms=1841" in _members(out)["container-tinyassets-logs.log"]


@pytest.mark.parametrize(
    "planted",
    [
        _shaped("gho", "_PLANTEDAAAABBBB", "CCCCDDDDEEEE1234"),
        _shaped("github", "_pat_11PLANTED0", "AAAABBBBCCCCDDDD_EEEEFFFF"),
        _shaped("sk-", "ant-api03-PLANTED", "AAAABBBBCCCCDDDDEEEE"),
        _shaped("sk-", "or-v1-planted0123456789", "abcdef0123456789"),
        _shaped("xox", "b-1111111111-2222222222222-", "PlantedSlackTokenValue00"),
    ],
)
def test_a_secret_in_the_journal_never_reaches_the_shipped_bundle(tmp_path, planted):
    """The load-bearing negative: a secret-shaped value present in the journal
    window is absent from the bundle that leaves the droplet.

    Asserted against the tarball's BYTES — every member's content plus every
    member name — rather than against the redactor's own view, so a leak through
    a file name or the manifest fails too. The bundle ships to GitHub release
    assets (deploy/backup.sh section 5), so this boundary is the trust boundary.

    Red-driven: with the loop in redact_log_bundle.redact_line disabled, each
    parameter of this test fails.
    """
    journal = _FakeJournal(
        output=(
            "2026-09-26T01:08:00.123456+0000 daemon: latency_ms=1841\n"
            f"2026-09-26T01:08:01.000000+0000 daemon: authorizing with {planted}\n"
        )
    )
    out = tmp_path / "tinyassets-logs-2026-09-26T03-00-00Z.tar.gz"

    code, report = backup_log_tier.build_bundle(
        out,
        sources=("container:tinyassets-logs",),
        since="3 days ago",
        binary=sys.executable,
        runner=journal,
    )
    assert code == 0, report

    with tarfile.open(out, "r:gz") as archive:
        names = archive.getnames()
        blob = b"".join(
            archive.extractfile(name).read()
            for name in names
            if archive.extractfile(name) is not None
        )
    blob += "".join(names).encode("utf-8")

    assert planted.encode("utf-8") not in blob, (
        f"{planted!r} reached the shipped bundle"
    )
    # The bundle still has to be worth shipping: the surrounding evidence and the
    # redaction marker survive, so this cannot pass by shipping nothing.
    assert b"latency_ms=1841" in blob
    assert REDACTED.encode("utf-8") in blob
