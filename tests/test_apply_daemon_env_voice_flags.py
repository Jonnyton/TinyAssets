"""Contract tests for dark Voice flags in the safe production applier."""

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


def test_voice_flags_are_available_to_the_rollback_safe_operator_path() -> None:
    arm = _feature_flag_case_arm()
    keys, separator, value_rule = arm.partition(")\n")
    assert separator
    for flag in VOICE_FLAGS:
        assert flag in keys
    assert value_rule.lstrip().startswith("vpat='^[01]$' ;;")


def test_voice_flags_are_not_assigned_or_enabled_by_the_workflow() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for flag in VOICE_FLAGS:
        assert f"{flag}=1" not in text
