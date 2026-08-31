"""Tests for the workspace bwrap oracle's HARNESS.

The six checks themselves need Linux, bwrap, git and this image's libcurl, so
they run on the droplet after deploy -- that is the whole reason the script
exists. What is testable anywhere is everything around them: the argument
parsing, the check registry, selection, how a raising check is scored, the
rendering, the exit code, and the preflight that refuses to run somewhere the
answers would be meaningless.

The one thing these tests must NOT do is let a broken harness look healthy: a
check that crashes has to score as a FAIL with the exception visible, and a
`--only` naming something unknown has to be an error rather than a silent
empty run that exits 0.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "workspace_bwrap_oracle.py"


def _load():
    spec = importlib.util.spec_from_file_location("workspace_bwrap_oracle", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["workspace_bwrap_oracle"] = module
    spec.loader.exec_module(module)
    return module


oracle = _load()


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #


def test_the_registry_names_the_claims_the_suite_cannot_prove() -> None:
    assert oracle.check_names() == [
        "bind_survives_a_rename",
        "jail_kill_reaps_a_double_fork",
        "jail_has_no_network_no_data_no_escape",
        "ws_bundle_imports_under_fsck",
        "run_git_timeout_reaps_a_descendant",
        "libcurl_multi_resolve_is_honoured",
        "full_route",
    ]


def test_every_check_is_callable_and_described() -> None:
    for check in oracle.CHECKS:
        assert callable(check.run), check.name
        assert check.summary.strip(), check.name
        assert check.run.__doc__, f"{check.name} must say what it proves"


def test_check_names_are_unique() -> None:
    names = oracle.check_names()
    assert len(names) == len(set(names))


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #


def test_no_selection_runs_everything() -> None:
    assert oracle.select_checks(None) == list(oracle.CHECKS)
    assert oracle.select_checks([]) == list(oracle.CHECKS)


def test_a_selection_runs_exactly_what_it_names() -> None:
    chosen = oracle.select_checks(["ws_bundle_imports_under_fsck"])
    assert [c.name for c in chosen] == ["ws_bundle_imports_under_fsck"]


def test_an_unknown_check_is_an_error_not_an_empty_run() -> None:
    """A typo that silently runs nothing and exits 0 is the worst outcome."""
    with pytest.raises(KeyError) as caught:
        oracle.select_checks(["bind_survives_a_renme"])
    assert "bind_survives_a_renme" in str(caught.value)
    assert "bind_survives_a_rename" in str(caught.value), "it should say what IS known"


def test_a_partly_unknown_selection_is_still_an_error() -> None:
    with pytest.raises(KeyError):
        oracle.select_checks(["ws_bundle_imports_under_fsck", "nope"])


# --------------------------------------------------------------------------- #
# Running and scoring
# --------------------------------------------------------------------------- #


def _check(name: str, fn) -> object:
    return oracle.Check(name, "a summary", fn)


def test_a_passing_and_a_failing_check_are_scored_and_ordered(tmp_path: Path) -> None:
    checks = [
        _check("good", lambda ctx: oracle.Outcome(True, "it held")),
        _check("bad", lambda ctx: oracle.Outcome(False, "it did not")),
    ]
    results = oracle.run_checks(checks, oracle.Context(root=tmp_path))
    assert [r.name for r in results] == ["good", "bad"]
    assert [r.outcome.status for r in results] == ["PASS", "FAIL"]
    assert oracle.exit_code_for(results) == 1


def test_a_check_that_raises_is_a_failure_carrying_the_exception(tmp_path: Path) -> None:
    """A crash is a failed proof, never an error that stops the report."""

    def explode(ctx):
        raise RuntimeError("bwrap went missing")

    results = oracle.run_checks([_check("boom", explode)], oracle.Context(root=tmp_path))
    assert results[0].outcome.ok is False
    assert "RuntimeError" in results[0].outcome.evidence
    assert "bwrap went missing" in results[0].outcome.evidence
    assert oracle.exit_code_for(results) == 1


def test_a_raising_check_does_not_stop_the_ones_after_it(tmp_path: Path) -> None:
    order: list[str] = []

    def explode(ctx):
        order.append("boom")
        raise ValueError("x")

    def later(ctx):
        order.append("later")
        return oracle.Outcome(True, "ran anyway")

    results = oracle.run_checks(
        [_check("boom", explode), _check("later", later)], oracle.Context(root=tmp_path)
    )
    assert order == ["boom", "later"]
    assert [r.outcome.ok for r in results] == [False, True]


def test_all_passing_exits_zero(tmp_path: Path) -> None:
    results = oracle.run_checks(
        [_check("good", lambda ctx: oracle.Outcome(True, "held"))],
        oracle.Context(root=tmp_path),
    )
    assert oracle.exit_code_for(results) == 0


def test_a_skip_is_not_a_pass_but_does_not_fail_the_run(tmp_path: Path) -> None:
    results = oracle.run_checks(
        [_check("s", lambda ctx: oracle.Outcome(False, "no curl", skipped=True))],
        oracle.Context(root=tmp_path),
    )
    assert results[0].outcome.status == "SKIP"
    assert oracle.exit_code_for(results) == 0


def test_each_result_records_how_long_its_check_took(tmp_path: Path) -> None:
    results = oracle.run_checks(
        [_check("good", lambda ctx: oracle.Outcome(True, "held"))],
        oracle.Context(root=tmp_path),
    )
    assert results[0].seconds >= 0.0


# --------------------------------------------------------------------------- #
# The context
# --------------------------------------------------------------------------- #


def test_scratch_directories_are_fresh_numbered_and_under_the_root(tmp_path: Path) -> None:
    context = oracle.Context(root=tmp_path)
    first = context.scratch("alpha")
    second = context.scratch("alpha")
    assert first != second, "a re-used name must not collide"
    for made in (first, second):
        assert made.is_dir()
        assert made.parent == tmp_path
        assert not any(made.iterdir()), "each check starts empty"


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def test_a_rendered_line_leads_with_the_status_and_names_the_check() -> None:
    line = oracle.render(
        oracle.Result("bind_survives_a_rename", "s", oracle.Outcome(True, "read the original"))
    )
    assert line.startswith("PASS ")
    assert "bind_survives_a_rename" in line
    assert "read the original" in line


def test_a_rendered_line_is_one_line_however_ugly_the_evidence() -> None:
    """git stderr is multi-line; a report that wraps is a report nobody greps."""
    messy = "fatal: unable to access\n  'https://example.invalid/'\n\n\tConnection refused"
    line = oracle.render(oracle.Result("x", "s", oracle.Outcome(False, messy)))
    assert "\n" not in line
    assert "\t" not in line
    assert "Connection refused" in line


def test_very_long_evidence_is_bounded() -> None:
    line = oracle.render(oracle.Result("x", "s", oracle.Outcome(False, "y" * 5000)))
    assert len(line) < 320
    assert line.endswith("...")


# --------------------------------------------------------------------------- #
# Preflight and main
# --------------------------------------------------------------------------- #


def test_preflight_refuses_a_temp_parent_under_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The daemon's /data is never a scratch root, whatever else is true."""
    problems = oracle.preflight("/data")
    assert any("/data" in problem for problem in problems)


def test_preflight_names_every_missing_prerequisite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(oracle.sys, "platform", "win32")
    monkeypatch.setattr(oracle.shutil, "which", lambda name: None)
    problems = oracle.preflight(str(tmp_path))
    joined = " ".join(problems)
    assert "Linux" in joined
    assert "bwrap" in joined
    assert "git" in joined


def test_preflight_is_clean_on_a_host_that_has_everything(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The guard must not be one that always fires."""
    monkeypatch.setattr(oracle.sys, "platform", "linux")
    monkeypatch.setattr(oracle.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert oracle.preflight(str(tmp_path)) == []


def test_list_prints_every_check_and_exits_zero(capsys: pytest.CaptureFixture) -> None:
    assert oracle.main(["--list"]) == 0
    printed = capsys.readouterr().out
    for name in oracle.check_names():
        assert name in printed


def test_an_unknown_only_exits_two_without_running_anything(
    capsys: pytest.CaptureFixture,
) -> None:
    assert oracle.main(["--only", "nope"]) == 2
    assert "unknown check" in capsys.readouterr().err


def test_a_host_that_cannot_answer_exits_two_rather_than_reporting_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Exit 2, not 0: 'nothing ran' must never read as 'everything held'."""
    monkeypatch.setattr(oracle, "preflight", lambda parent: ["bwrap is not on PATH"])
    assert oracle.main([]) == 2
    err = capsys.readouterr().err
    assert "bwrap is not on PATH" in err
    assert "deployed container" in err


def test_the_parser_defaults_to_tmp_and_keeps_nothing() -> None:
    args = oracle.build_parser().parse_args([])
    assert args.temp_parent == "/tmp"
    assert args.keep is False
    assert args.only is None
    assert args.list is False


def test_only_is_repeatable() -> None:
    args = oracle.build_parser().parse_args(
        ["--only", "ws_bundle_imports_under_fsck", "--only", "bind_survives_a_rename"]
    )
    assert args.only == ["ws_bundle_imports_under_fsck", "bind_survives_a_rename"]


def test_main_runs_the_selected_checks_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(oracle, "preflight", lambda parent: [])
    seen: list[str] = []

    def fake(ctx):
        seen.append(str(ctx.root))
        return oracle.Outcome(True, "held")

    monkeypatch.setattr(oracle, "CHECKS", (oracle.Check("only_one", "s", fake),))
    assert oracle.main(["--temp-parent", str(tmp_path)]) == 0
    printed = capsys.readouterr().out
    assert "PASS only_one" in printed
    assert "1/1 passed" in printed
    assert seen, "the check never ran"
    assert not Path(seen[0]).exists(), "the temp root must be removed"


def test_main_keeps_the_temp_root_when_asked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(oracle, "preflight", lambda parent: [])
    seen: list[str] = []
    monkeypatch.setattr(
        oracle,
        "CHECKS",
        (
            oracle.Check(
                "one",
                "s",
                lambda ctx: (
                    seen.append(str(ctx.root)),
                    oracle.Outcome(True, "x"),
                )[1],
            ),
        ),
    )
    assert oracle.main(["--temp-parent", str(tmp_path), "--keep"]) == 0
    assert Path(seen[0]).exists()
    assert "kept" in capsys.readouterr().out


def test_main_exits_one_when_a_check_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(oracle, "preflight", lambda parent: [])
    monkeypatch.setattr(
        oracle,
        "CHECKS",
        (oracle.Check("bad", "s", lambda ctx: oracle.Outcome(False, "it did not hold")),),
    )
    assert oracle.main(["--temp-parent", str(tmp_path)]) == 1
    assert "FAIL bad" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# What the script must never do
# --------------------------------------------------------------------------- #


def test_the_script_never_aims_a_filesystem_call_at_data() -> None:
    """It runs on a LIVE box; the daemon's /data is not its scratch space.

    Asserted by what would do the damage -- a write call pointed at /data --
    rather than by an allowlist of acceptable mentions, which would need
    updating every time the refusal is reworded.
    """
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "refusing to write under /data" in source, "the refusal must exist"
    writes = ("mkdir", "mkdtemp", "write_text", "write_bytes", "rmtree", "open(", "rename")
    for number, line in enumerate(source.splitlines(), start=1):
        if "/data" not in line:
            continue
        for call in writes:
            assert call not in line, f"line {number} aims {call} at /data: {line.strip()}"


def test_the_temp_root_default_is_tmp_not_data() -> None:
    assert oracle.TEMP_PARENT == "/tmp"
    assert not oracle.TEMP_PARENT.startswith("/data")


def test_the_script_imports_tinyassets_lazily() -> None:
    """It must import cleanly off the droplet so the harness stays testable."""
    source = _SCRIPT.read_text(encoding="utf-8")
    head = source.split("def ", 1)[0]
    assert "import tinyassets" not in head
    assert "from tinyassets" not in head


def test_the_checks_only_reach_the_network_through_loopback() -> None:
    source = _SCRIPT.read_text(encoding="utf-8")
    # 1.1.1.1 appears only inside the jail probe, which EXPECTS to fail
    assert source.count("1.1.1.1") == 1
    assert "127.0.0.1" in source, "the curloptResolve pin is loopback"
    assert "example.invalid" in source, "and the pinned name is reserved"


# --------------------------------------------------------------------------- #
# The libcurl version: read from the library git links, never from a binary
# --------------------------------------------------------------------------- #


class _FakeCurlLib:
    """A loaded shared library that answers ``curl_version()``."""

    def __init__(self, text: bytes) -> None:
        self._text = text

    @property
    def curl_version(self):
        holder = self

        class _Fn:
            restype = None

            def __call__(_self):
                return holder._text

        return _Fn()


def test_the_libcurl_version_comes_from_the_library_and_names_which_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production image has no curl binary; the library must answer."""
    import ctypes

    def _cdll(name: str, *args, **kwargs):
        if name != "libcurl-gnutls.so.4":
            raise OSError(f"no {name}")
        return _FakeCurlLib(b"libcurl/8.14.1 GnuTLS/3.8.3 zlib/1.3")

    monkeypatch.setattr(ctypes, "CDLL", _cdll)
    monkeypatch.setattr(oracle.shutil, "which", lambda _name, **_kw: None)

    text, source = oracle._libcurl_version_and_source()

    assert "libcurl/8.14.1" in text
    assert source == "libcurl-gnutls.so.4", "the library git links must be named"


def test_the_libcurl_source_names_the_binary_when_no_library_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ctypes
    import subprocess

    monkeypatch.setattr(
        ctypes, "CDLL", lambda name, *a, **k: (_ for _ in ()).throw(OSError(name))
    )
    monkeypatch.setattr(oracle.shutil, "which", lambda name, **_kw: "/usr/bin/curl")

    class _Probe:
        stdout = b"curl 8.5.0 (x86_64) libcurl/8.5.0 OpenSSL/3.0.13"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Probe())

    text, source = oracle._libcurl_version_and_source()

    assert "libcurl/8.5.0" in text
    assert source == "/usr/bin/curl", "a binary answer must not be reported as a library"


def test_a_library_that_loads_but_cannot_answer_is_not_reported_as_the_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A loaded-but-silent libcurl must not be credited with the answer."""
    import ctypes

    class _Mute:
        def __getattr__(self, _name):
            raise AttributeError("curl_version")

    def _cdll(name: str, *args, **kwargs):
        if name == "libcurl-gnutls.so.4":
            return _Mute()
        if name == "libcurl.so.4":
            return _FakeCurlLib(b"libcurl/8.14.1 OpenSSL/3.0.13")
        raise OSError(name)

    monkeypatch.setattr(ctypes, "CDLL", _cdll)
    monkeypatch.setattr(oracle.shutil, "which", lambda _name, **_kw: None)

    _text, source = oracle._libcurl_version_and_source()

    assert source == "libcurl.so.4"


def test_no_check_shells_out_to_a_curl_binary_to_read_a_version() -> None:
    """Measured on the production container 2026-08-31: there is no ``curl``.

    A binary-only probe made check 6 a permanent FAIL there for the wrong
    reason, so the whole script must read through the library-first reader.
    """
    source = _SCRIPT.read_text(encoding="utf-8")
    for shape in ('which("curl")', "which('curl')", '"curl", "-V"', "'curl', '-V'"):
        assert shape not in source, f"the script still shells out to curl: {shape}"


def test_the_multi_resolve_check_reads_through_the_shared_reader() -> None:
    import inspect

    body = inspect.getsource(oracle.check_libcurl_multi_resolve_is_honoured)
    assert "_libcurl_version_and_source()" in body
    # The discrimination that makes the check mean anything is _pin_verdict,
    # tested behaviourally below -- asserting the two phrases here passed on
    # the COMMENT that explains them, which is a guard that cannot go red.
    assert "_pin_verdict(" in body


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("fatal: unable to access ...: Could not resolve host: example.invalid", (True, False)),
        ("fatal: unable to access ...: Failed to connect to example.invalid", (False, True)),
        ("fatal: unable to access ...: Connection refused", (False, True)),
        ("fatal: something else entirely", (False, False)),
    ],
)
def test_the_pin_verdict_separates_an_ignored_pin_from_a_used_one(
    stderr: str, expected: tuple[bool, bool]
) -> None:
    """Only "failed to connect" proves libcurl took the curloptResolve entry."""
    assert oracle._pin_verdict(stderr) == expected


def test_an_unrelated_git_failure_does_not_count_as_the_pin_being_honoured() -> None:
    ignored, used = oracle._pin_verdict("fatal: repository not found")
    assert not used, "a check that accepts any failure proves nothing"
    assert not ignored


def test_the_full_route_worker_reads_a_version_through_the_same_reader() -> None:
    """Otherwise the route billed as production would not catch the reader failing.

    ``libcurl_version_text`` refusing in the image refuses every checkout, so
    the check that exists to prove the production route must exercise it.
    """
    import inspect

    body = inspect.getsource(oracle.check_full_route)
    assert "_libcurl_version_and_source()" in body
    assert "GitTransport.build(" in body, "the transport derives the binding"
    assert "transport.broker_binding()" in body
    assert (
        'request["owner_repo"] + ".git"' not in body
    ), "the wire path must be derived, not hand-spelled on both sides"
    assert "the route never read a libcurl version" in body, "and it is asserted"
