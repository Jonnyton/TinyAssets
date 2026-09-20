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
    found, _notes = scan_text(text, MODES)
    return [reason for _lineno, reason in found]


def notes(text: str) -> list[str]:
    _found, ns = scan_text(text, MODES)
    return [reason for _lineno, reason in ns]


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


def test_interactive_admin_exec_is_reported_as_a_note_not_hidden():
    text = ("sudo docker exec -it -e CLAUDE_CONFIG_DIR=/data/.claude tinyassets-daemon "
            "/opt/claude-code-install/node_modules/.bin/claude auth login --claudeai")
    assert violations(text) == []
    assert notes(text), "an out-of-gate admin exec must still be printed"


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
