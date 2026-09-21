"""Behavioural red/green for the drop-first exec gate.

Each RED case is a form that exists (or existed) in this repo, so the gate is
proven to fire on real shapes rather than on invented ones. Each GREEN case is
the migrated form of the same callsite.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.check_drop_first_exec import load_modes, main, scan_text

REPO = Path(__file__).resolve().parent.parent
MODES = load_modes()


def violations(text: str) -> list[str]:
    return [reason for _lineno, reason in scan_text(text, MODES)]


# --- RED ---------------------------------------------------------------

@pytest.mark.parametrize(
    "snippet",
    [
        # the pre-migration keepalive, sudo-prefixed, inside single quotes
        "'sudo docker exec -e CLAUDE_CONFIG_DIR=/data/.claude "
        'tinyassets-daemon claude -p "Reply with OK." >/dev/null' + "'",
        # the pre-migration loopback canary
        "docker exec tinyassets-daemon python /app/scripts/mcp_public_canary.py --url http://127.0.0.1:8001/mcp",
        # the pre-migration fail-open env read, container behind a variable
        'live="$(docker exec "$DAEMON_CONTAINER" printenv "$1" 2>/dev/null || true)"',
        # compose exec against the service alias
        "docker compose exec daemon python -c 'import os'",
        "docker-compose exec daemon python -m tinyassets.universe_server",
        # brace form of the container variable
        'docker exec "${DAEMON_CONTAINER}" printenv KEY',
    ],
)
def test_red_bare_privileged_surface_exec(snippet):
    assert violations(snippet), f"gate failed to fire on: {snippet[:60]}"


def test_red_backslash_continuation_variant():
    text = (
        "docker exec tinyassets-daemon " + chr(92) + "\n"
        "    python scripts/mcp_public_canary.py " + chr(92) + "\n"
        "        --url http://127.0.0.1:8001/mcp --verbose\n"
    )
    assert violations(text)


def test_red_yaml_block_scalar_run_step():
    text = (
        "      - name: probe\n"
        "        run: |\n"
        "          set -euo pipefail\n"
        "          sudo docker exec tinyassets-daemon python /app/scripts/x.py\n"
    )
    assert violations(text)


def test_red_wrapped_but_unknown_mode():
    reasons = violations("docker exec tinyassets-daemon /usr/local/libexec/ta-op shell")
    assert any("unknown ta-op mode" in r for r in reasons), reasons


def test_red_wrapped_known_mode_with_wrong_arity():
    reasons = violations(
        "docker exec tinyassets-daemon /usr/local/libexec/ta-op pulse extra-arg"
    )
    assert any("argc" in r for r in reasons), reasons
    reasons = violations("docker exec tinyassets-daemon /usr/local/libexec/ta-op printenv")
    assert any("argc" in r for r in reasons), reasons


def test_red_wrapper_named_with_no_mode():
    reasons = violations("docker exec tinyassets-daemon /usr/local/libexec/ta-op")
    assert any("no mode" in r for r in reasons), reasons


# --- GREEN -------------------------------------------------------------

@pytest.mark.parametrize(
    "snippet",
    [
        "docker exec tinyassets-daemon /usr/local/libexec/ta-op canary",
        "docker exec tinyassets-daemon /usr/local/libexec/ta-op env-summary",
        'docker exec "$DAEMON_CONTAINER" "$TA_OP" printenv "$1"',
        "sudo docker exec -e CODEX_HOME=/data/.codex tinyassets-daemon "
        "/usr/local/libexec/ta-op codex-keepalive >/dev/null",
        "docker exec tinyassets-daemon /usr/local/libexec/ta-op printenv "
        "TINYASSETS_SOME_FLAG   # confirm it took",
    ],
)
def test_green_migrated_forms(snippet):
    assert violations(snippet) == []


@pytest.mark.parametrize(
    "snippet",
    [
        # the pre-correction carve-out: the documented interactive login
        "sudo docker exec -it -e CLAUDE_CONFIG_DIR=/data/.claude tinyassets-daemon "
        "/opt/claude-code-install/node_modules/.bin/claude auth login --claudeai",
        # a TTY does not launder any other argv either
        "docker exec -it tinyassets-daemon bash",
        "docker exec -t tinyassets-daemon sh -c 'cat /data/.claude/.credentials.json'",
        "docker exec -ti tinyassets-daemon /usr/bin/printenv",
        "sudo docker exec --interactive --tty tinyassets-daemon /bin/sh",
    ],
)
def test_a_tty_is_not_an_exemption(snippet):
    """A `-t`/`-it` exec is a violation like any other bare exec.

    The earlier revision reported these as notes on the reasoning that no
    automation can allocate a TTY. A TTY is a property of the invocation, not
    proof that the command is unreachable, and the exemption admitted arbitrary
    repo-authored argv. There is no second, softer tier any more.
    """
    assert violations(snippet), "a TTY exec must fail the gate, not be noted"


def test_the_migrated_interactive_login_is_green():
    text = ("sudo docker exec -it -e CLAUDE_CONFIG_DIR=/data/.claude tinyassets-daemon "
            "/usr/local/libexec/ta-op claude-login")
    assert violations(text) == []


def test_claude_login_is_a_declared_fixed_mode_with_no_operand():
    spec = MODES["claude-login"]
    assert spec["argc"] == 2, "the callsite supplies no operand"
    assert spec["argv"] == ["/usr/local/bin/claude", "auth", "login", "--claudeai"]
    # ... and passing one is still a violation.
    assert violations(
        "docker exec -it tinyassets-daemon /usr/local/libexec/ta-op claude-login --extra"
    )


def test_the_gate_exposes_no_note_channel():
    """Regression: the softer tier is gone, not merely unused.

    `scan_text` returning a second list is how an exemption comes back — a
    caller can keep matching shapes out of the violation count while still
    "reporting" them.
    """
    result = scan_text("docker exec -it tinyassets-daemon bash", MODES)
    assert isinstance(result, list)
    assert all(isinstance(item, tuple) and len(item) == 2 for item in result)
    source = (REPO / "scripts" / "check_drop_first_exec.py").read_text(encoding="utf-8")
    assert "notes" not in source, "no note channel may exist in the gate"


# --- the gate against the real tree, and against the pre-migration tree ---

def test_gate_is_green_on_the_working_tree():
    assert main([]) == 0


def test_gate_would_have_been_red_before_this_change():
    """Proven red by replaying the pre-migration content of a real callsite.

    Without this, a gate that can never go red on this repo's own history is
    decoration. `git show <base>:<path>` is the unmigrated file.
    """
    base = "e4c921820d8c834e974c89435e5031f0e82c60d4"
    checked = 0
    for rel in (
        ".github/workflows/claude-auth-keepalive.yml",
        ".github/workflows/codex-auth-keepalive.yml",
        "scripts/droplet.py",
        "deploy/apply-daemon-env-remote.sh",
        "deploy/compose.yml",
    ):
        proc = subprocess.run(
            ["git", "show", f"{base}:{rel}"], cwd=REPO,
            capture_output=True, text=True,
        )
        if proc.returncode != 0:  # base object not present in a shallow clone
            pytest.skip(f"base object {base} unavailable: {proc.stderr.strip()}")
        if rel == "deploy/compose.yml":
            # the healthcheck is a compose `test:` list, not a docker exec line;
            # assert the migration instead of expecting the exec scanner to fire
            assert "/usr/local/libexec/ta-op" not in proc.stdout
            checked += 1
            continue
        assert violations(proc.stdout), f"gate did not fire on pre-migration {rel}"
        checked += 1
    assert checked == 5
