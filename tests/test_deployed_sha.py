"""Tests for the Hard Rule 14 gate: is this commit actually in production?

No network. `live_release_state` is the only part that talks to the live
surface, so every test stubs it and exercises the logic that decides SHIPPED /
NOT SHIPPED / UNKNOWN.

The distinction these tests exist to protect: **"I could not tell" must never
read as "yes, it shipped."** That is exit 2, not exit 0.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def load():
    path = REPO_ROOT / "scripts" / "deployed_sha.py"
    spec = importlib.util.spec_from_file_location("deployed_sha_under_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    """A throwaway two-commit repo the ancestry checks run against.

    These tests used to read the AMBIENT repo's HEAD and HEAD~1, which passed
    locally and failed in CI: actions/checkout is shallow, so `git rev-parse
    HEAD~1` exits 128 and there is no parent. Depending on the surrounding
    checkout also meant the tests could not say what history they needed.
    A purpose-built repo is hermetic and states its own preconditions.
    """
    root = tmp_path_factory.mktemp("deployed-sha-repo")

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True,
        ).stdout.strip()

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (root / "a.txt").write_text("one", encoding="utf-8")
    git("add", ".")
    git("commit", "-q", "-m", "first")
    parent = git("rev-parse", "HEAD")
    (root / "a.txt").write_text("two", encoding="utf-8")
    git("add", ".")
    git("commit", "-q", "-m", "second")
    head = git("rev-parse", "HEAD")
    return {"root": root, "head": head, "parent": parent}


def point_at(mod, monkeypatch, repo):
    monkeypatch.setattr(mod, "REPO_ROOT", repo["root"])


def stub(mod, monkeypatch, release_state):
    monkeypatch.setattr(mod, "live_release_state", lambda url, timeout: release_state)


def receipt(sha, **extra):
    """A complete, self-consistent receipt.

    image_tag is REQUIRED since 2026-08-26: a receipt carrying git_sha with no
    corroborating tag cannot be cross-checked, so the deploy state is unknown
    (exit 2) rather than a pass. Tests that need the unknown path stub a
    partial receipt deliberately.
    """
    state = {"git_sha": sha, "image_tag": f"ghcr.io/jonnyton/tinyassets-daemon:{sha[:12]}"}
    state.update(extra)
    return state


def test_live_release_state_gets_pulse_as_canary(monkeypatch):
    mod = load()
    seen = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps({"git_sha": "abc", "image_tag": "image:abc"}).encode()

    def urlopen(request, timeout):
        seen.append(request)
        return Response()

    monkeypatch.setattr(mod.urllib.request, "urlopen", urlopen)
    monkeypatch.setenv("TINYASSETS_WIKI_CANARY_TOKEN", "canary-token")
    result = mod.live_release_state("https://example/mcp/", 2.0)
    assert result["git_sha"] == "abc"
    assert seen[0].full_url == "https://example/mcp/pulse"
    assert seen[0].get_header("Accept") == "application/json"
    assert seen[0].get_header("Authorization") == "Bearer canary-token"


def test_live_release_state_without_canary_bearer_exits_before_network(monkeypatch):
    mod = load()
    called = False

    def urlopen(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network must not run without the canary principal")

    monkeypatch.delenv("TINYASSETS_WIKI_CANARY_TOKEN", raising=False)
    monkeypatch.setattr(mod.urllib.request, "urlopen", urlopen)

    with pytest.raises(SystemExit) as exc:
        mod.live_release_state("https://tinyassets.io/mcp", 2.0)

    assert exc.value.code == 2
    assert called is False


def test_live_release_state_rejects_non_object(monkeypatch):
    mod = load()

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b"[]"

    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda *a, **k: Response())
    monkeypatch.setenv("TINYASSETS_WIKI_CANARY_TOKEN", "canary-token")
    with pytest.raises(mod.DeployedShaError):
        mod.live_release_state("https://example/mcp", 2.0)


def test_deployed_head_contains_its_own_parent(monkeypatch, repo):
    """The ordinary pass: production is ahead of the commit being claimed."""
    mod = load()
    point_at(mod, monkeypatch, repo)
    stub(mod, monkeypatch, receipt(repo["head"]))

    assert mod.main(["--assert-contains", repo["parent"]]) == 0


def test_deployed_parent_does_not_contain_head(monkeypatch, repo):
    """The 2026-07-21 case: merged, but production is serving something older."""
    mod = load()
    point_at(mod, monkeypatch, repo)
    stub(mod, monkeypatch, receipt(repo["parent"]))

    assert mod.main(["--assert-contains", repo["head"]]) == 1


def test_commit_equal_to_deployed_counts_as_shipped(monkeypatch, repo):
    mod = load()
    point_at(mod, monkeypatch, repo)
    head = repo["head"]
    stub(mod, monkeypatch, receipt(head))

    assert mod.main(["--assert-contains", head]) == 0


def test_missing_release_state_is_unknown_not_shipped(monkeypatch, repo):
    """Exit 2, never 0. A probe that cannot answer must not read as a pass."""
    mod = load()
    point_at(mod, monkeypatch, repo)

    def boom(url, timeout):
        raise mod.DeployedShaError("get_status carries no release_state object")

    monkeypatch.setattr(mod, "live_release_state", boom)

    assert mod.main(["--assert-contains", repo["head"]]) == 2


def test_empty_git_sha_is_unknown_not_shipped(monkeypatch, repo):
    mod = load()
    point_at(mod, monkeypatch, repo)
    stub(mod, monkeypatch, {"git_sha": "   "})

    assert mod.main(["--assert-contains", repo["head"]]) == 2


def test_unfetched_deployed_sha_is_unknown_not_shipped(monkeypatch, repo):
    """Production serving a commit this checkout lacks is UNKNOWN, not a fail.

    Reporting 1 here would say "not shipped" about a build that may well
    contain the commit; the honest answer is "fetch it, then re-run".
    """
    mod = load()
    point_at(mod, monkeypatch, repo)
    stub(mod, monkeypatch, {"git_sha": "0" * 40})

    assert mod.main(["--assert-contains", repo["head"]]) == 2


def test_plain_report_succeeds_without_assertion(monkeypatch, repo):
    mod = load()
    point_at(mod, monkeypatch, repo)
    stub(mod, monkeypatch, receipt(repo["head"]))

    assert mod.main([]) == 0


def test_report_counts_commits_not_yet_deployed(monkeypatch, repo):
    mod = load()
    point_at(mod, monkeypatch, repo)
    stub(mod, monkeypatch, receipt(repo["parent"]))

    info = mod.report("https://example.invalid/mcp", 1.0)

    assert info["deployed_sha"] == repo["parent"]
    assert info["known_to_git"] is True
    assert info["deployed_subject"]


@pytest.mark.parametrize("bad", [{}, {"git_sha": None}, {"git_sha": ""}])
def test_unusable_release_state_shapes_all_raise(monkeypatch, repo, bad):
    mod = load()
    point_at(mod, monkeypatch, repo)
    stub(mod, monkeypatch, bad)

    with pytest.raises(mod.DeployedShaError):
        mod.report("https://example.invalid/mcp", 1.0)


def test_receipt_disagreeing_with_itself_is_unknown(monkeypatch, repo):
    """git_sha vs image_tag mismatch is exit 2, never a pass.

    Agreement does not prove the running binary (see the module docstring and
    docs/concerns/2026-08-26-deployed-sha-proves-receipt-only.md). DISagreement
    does prove the receipt is untrustworthy, and an untrustworthy receipt must
    never read as shipped.
    """
    mod = load()
    point_at(mod, monkeypatch, repo)
    stub(mod, monkeypatch, {
        "git_sha": repo["head"],
        "image_tag": "ghcr.io/jonnyton/tinyassets-daemon:deadbeefcafe",
    })

    assert mod.main(["--assert-contains", repo["head"]]) == 2


def test_agreeing_receipt_still_passes(monkeypatch, repo):
    mod = load()
    point_at(mod, monkeypatch, repo)
    head = repo["head"]
    stub(mod, monkeypatch, {
        "git_sha": head,
        "image_tag": f"ghcr.io/jonnyton/tinyassets-daemon:{head[:12]}",
    })

    assert mod.main(["--assert-contains", head]) == 0


def test_report_labels_what_it_actually_proves(monkeypatch, repo):
    """The tool must not let a caller mistake a receipt for the running binary."""
    mod = load()
    point_at(mod, monkeypatch, repo)
    stub(mod, monkeypatch, receipt(repo["head"]))

    assert mod.report("https://example.invalid/mcp", 1.0)["proves"] == "receipt"


# --- receipt schema hardening (cross-family review 2026-08-26) --------------


@pytest.mark.parametrize("tag,should_pass", [
    ("ghcr.io/x/y:{sha12}", True),          # bare sha
    ("ghcr.io/x/y:release-{sha12}", True),  # valid OCI form, previously rejected
    ("ghcr.io/x/y:v{sha12}", True),
    ("ghcr.io/x/y:{SHA12}", True),          # uppercase hex, previously rejected
    ("ghcr.io/x/y:deadbeefcafe", False),    # real sha, wrong one
])
def test_image_tag_forms(monkeypatch, repo, tag, should_pass):
    mod = load()
    point_at(mod, monkeypatch, repo)
    head = repo["head"]
    stub(mod, monkeypatch, {
        "git_sha": head,
        "image_tag": tag.format(sha12=head[:12], SHA12=head[:12].upper()),
    })

    assert mod.main(["--assert-contains", head]) == (0 if should_pass else 2)


def test_one_char_tag_does_not_pass(monkeypatch, repo):
    """A tag sharing only the sha's first character used to satisfy the check."""
    mod = load()
    point_at(mod, monkeypatch, repo)
    head = repo["head"]
    stub(mod, monkeypatch, {"git_sha": head, "image_tag": f"ghcr.io/x/y:{head[0]}"})

    assert mod.main(["--assert-contains", head]) == 2


def test_missing_image_tag_is_unknown_not_pass(monkeypatch, repo):
    """The docstring always claimed this; the code did not do it."""
    mod = load()
    point_at(mod, monkeypatch, repo)
    stub(mod, monkeypatch, {"git_sha": repo["head"]})

    assert mod.main(["--assert-contains", repo["head"]]) == 2


@pytest.mark.parametrize("bad", [123, {"a": 1}, [], True])
def test_non_string_image_tag_does_not_crash(monkeypatch, repo, bad):
    """A dict/list/int tag raised an uncaught AttributeError."""
    mod = load()
    point_at(mod, monkeypatch, repo)
    stub(mod, monkeypatch, {"git_sha": repo["head"], "image_tag": bad})

    assert mod.main(["--assert-contains", repo["head"]]) == 2


def test_pulse_request_names_itself_so_cloudflare_does_not_challenge_it(monkeypatch):
    """The stdlib default agent draws a managed-challenge 403 from Cloudflare on
    the live surface (measured 2026-09-02), and this gate would then report
    "cannot determine" forever."""
    mod = load()
    seen = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps({"git_sha": "abc", "image_tag": "image:abc"}).encode()

    def urlopen(request, timeout):
        seen.append(request)
        return Response()

    monkeypatch.setattr(mod.urllib.request, "urlopen", urlopen)
    monkeypatch.setenv("TINYASSETS_WIKI_CANARY_TOKEN", "canary-token")
    mod.live_release_state("https://tinyassets.io/mcp", 2.0)
    agent = seen[0].get_header("User-agent")
    assert agent == mod.PULSE_USER_AGENT
    assert "urllib" not in (agent or "").lower()
