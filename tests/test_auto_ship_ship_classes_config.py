from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[1] / "auto_ship_ship_classes.yaml"


def test_ship_class_defaults_require_two_manual_keys():
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    defaults = config["defaults"]

    assert defaults["auto_merge"] is False
    assert defaults["keys_auto_open"] is False
    assert defaults["required_keys"] == ["codex_reviewer", "cowork_reviewer"]


def test_graduation_classes_start_disabled_until_policy_flip():
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    ship_classes = config["ship_classes"]

    assert "docs_canary" in ship_classes
    assert ship_classes["docs_general"]["enabled"] is False
    assert ship_classes["tests_canary"]["enabled"] is False
    assert ship_classes["docs_canary"]["graduation"]["next_class"] == "docs_general"
    assert ship_classes["docs_general"]["graduation"]["next_class"] == "tests_canary"
