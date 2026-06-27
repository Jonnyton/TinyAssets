"""Persona-replay regression scaffolding.

Companion to live user-sim. Live sim (per
`project_user_sim_continuous_competitor_parity`) catches NEW bugs by
running personas freshly through the platform; persona-replay catches
REGRESSIONS by re-running a recorded session-transcript step against
the current platform and asserting chatbot behavior still matches the
expected outcome. Host directive Q5 (2026-04-27): "if it exposes a bug
it's a real signal. if you're using it to test if our fix landed we
still want real users use." Replay supplements (does not replace) the
live-sim path.

This file is INFRASTRUCTURE only. It defines the fixture shape and
the helper signature so future work has a place to slot live replay
logic into. No persona's actual replay data is wired up yet.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

REPLAY_NOT_IMPLEMENTED = "replay_not_implemented"


@dataclass(frozen=True)
class ReplayResult:
    """Outcome of replaying one persona transcript step.

    `status` is `REPLAY_NOT_IMPLEMENTED` while the helper is a stub.
    Future work will add concrete statuses (e.g. `match`, `regression`,
    `chatbot_error`, `tool_unavailable`) and an `evidence` payload.
    """

    status: str
    note: str


def replay_persona_step(step: dict) -> ReplayResult:
    """Replay one persona transcript step against the live platform.

    TODO: wire this to claude_chat.py + MCP connector once the live-sim
    capture format is canonicalised. For now it returns a placeholder so
    callers can build against the signature.
    """

    return ReplayResult(
        status=REPLAY_NOT_IMPLEMENTED,
        note=(
            "scaffold only — step replay against live platform not yet "
            f"wired (received step keys: {sorted(step)})"
        ),
    )


@pytest.fixture
def persona_session_dir(tmp_path: Path) -> Path:
    """Simulated `output/personas/<name>/sessions/<n>/` directory.

    Two hardcoded steps modeled on the priya transcript shape
    (user message + predicted ideal chatbot response). Real replay
    captures will live under `output/personas/` once the capture path
    is wired; this fixture mirrors that shape so tests can exercise
    the helper without depending on disk state outside `tmp_path`.
    """

    session_dir = tmp_path / "personas" / "priya_ramaswamy" / "sessions" / "1"
    session_dir.mkdir(parents=True)

    steps = [
        {
            "t_offset": "T+0:00",
            "speaker": "user",
            "message": (
                "i need to run maxent on 14 species x 5 reg values x "
                "5-fold cv. budget ~$10. can workflow do this?"
            ),
            "expected_chatbot_intent": "invoke_workflow_assume_default",
        },
        {
            "t_offset": "T+0:01",
            "speaker": "chatbot",
            "expected_tool_calls": ["universe.inspect", "goals.propose"],
            "expected_response_contains": ["sweep", "maxent", "14 species"],
        },
    ]

    (session_dir / "transcript.json").write_text(
        json.dumps({"persona": "priya_ramaswamy", "session": 1, "steps": steps}),
        encoding="utf-8",
    )
    return session_dir


def test_persona_replay_infrastructure_present(persona_session_dir: Path) -> None:
    """Smoke check: fixture + helper exist and return the placeholder."""

    transcript_path = persona_session_dir / "transcript.json"
    assert transcript_path.is_file()

    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    assert transcript["persona"] == "priya_ramaswamy"
    assert len(transcript["steps"]) == 2

    result = replay_persona_step(transcript["steps"][0])
    assert isinstance(result, ReplayResult)
    assert result.status == REPLAY_NOT_IMPLEMENTED
    assert "scaffold only" in result.note


@pytest.mark.skip(reason="awaits live persona-step replay implementation per host directive")
def test_priya_session_1_replay_baseline(persona_session_dir: Path) -> None:
    """Future shape: replay priya session 1 step 0, assert chatbot intent matches.

    Once `replay_persona_step` is wired to the live platform, this test
    will assert that the chatbot's first response to priya's MaxEnt
    sweep ask (a) invokes TinyAssets without disambiguation, and (b)
    surfaces the recorded `expected_tool_calls` in the same order.
    Regression here means a chain-break versus the recorded baseline.
    """

    transcript = json.loads(
        (persona_session_dir / "transcript.json").read_text(encoding="utf-8")
    )
    result = replay_persona_step(transcript["steps"][0])
    assert result.status == "match", f"replay regressed: {result.note}"
