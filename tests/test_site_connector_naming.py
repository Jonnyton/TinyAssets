from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_connect_page_names_custom_connector_workflow() -> None:
    source = (
        REPO_ROOT / "WebSite/site/src/routes/connect/+page.svelte"
    ).read_text(encoding="utf-8")

    assert "Name the connector Workflow" in source
    assert "rather than TinyAssets" in source
    assert "reusable building blocks earlier users leave for later builders" in source


def test_chatgpt_submission_display_name_stays_workflow() -> None:
    packet = json.loads(
        (REPO_ROOT / "chatgpt-app-submission.json").read_text(encoding="utf-8")
    )

    assert packet["app_info"]["display_name"] == "Workflow"
    assert packet["app_info"]["display_name"] != "TinyAssets"
