"""The deploy must prove its protected release receipt after publication."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-prod.yml"


def _steps() -> list[dict]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["deploy"]["steps"]


def test_deploy_runs_authenticated_deployed_sha_after_receipt_publication() -> None:
    steps = _steps()
    receipt_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Publish release-state receipt"
    )
    proof_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Verify protected receipt contains target revision"
    )
    proof = steps[proof_index]

    assert receipt_index < proof_index
    assert proof.get("id") == "deployed_sha"
    assert proof["env"]["GIT_SHA"] == "${{ steps.tag.outputs.revision }}"
    assert proof["env"]["TINYASSETS_WIKI_CANARY_TOKEN"] == (
        "${{ secrets.TINYASSETS_WIKI_CANARY_TOKEN }}"
    )
    script = proof["run"]
    assert "python scripts/deployed_sha.py" in script
    assert "--url https://tinyassets.io/mcp" in script
    assert '--assert-contains "${GIT_SHA}"' in script
    assert "get_status" not in script


def test_deploy_summary_exposes_protected_receipt_assertion_outcome() -> None:
    summary = next(step for step in _steps() if step.get("name") == "Summary")
    assert "steps.deployed_sha.outcome" in summary["run"]
