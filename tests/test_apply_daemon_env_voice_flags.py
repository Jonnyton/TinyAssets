"""Contract tests for retired Voice host flags in the production applier."""

from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(".github/workflows/apply-daemon-env.yml")
VOICE_FLAGS = (
    "TINYASSETS_REALTIME_VOICE_ENABLED",
    "TINYASSETS_ALLOW_REALTIME_VOICE_API",
)


def _feature_flag_case_arm() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index('case "${INPUT_KEY}" in')
    end = text.index("            *)", start)
    return text[start:end]


def test_retired_voice_flags_are_not_operator_controls() -> None:
    arm = _feature_flag_case_arm()
    for flag in VOICE_FLAGS:
        assert flag not in arm


def test_retired_voice_flags_are_not_assigned_by_the_workflow() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for flag in VOICE_FLAGS:
        assert f"{flag}=1" not in text
