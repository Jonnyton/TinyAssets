"""The platform control plane must not probe for an attached model executor."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_platform_llm_binding_canary_is_retired() -> None:
    workflow = ROOT / ".github" / "workflows" / "llm-binding-canary.yml"
    assert not workflow.exists()
