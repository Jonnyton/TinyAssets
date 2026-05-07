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


def test_auto_merge_requires_explicit_host_named_key():
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    defaults = config["defaults"]
    auto_merge_required_keys = defaults["auto_merge_required_keys"]

    assert auto_merge_required_keys == ["host_reviewer"]
    assert "host_reviewer" in config["reviewer_roles"]
    for name, policy in config["ship_classes"].items():
        effective_auto_merge = policy.get("auto_merge", defaults["auto_merge"])
        if not effective_auto_merge:
            continue

        effective_required_keys = policy.get("required_keys", defaults["required_keys"])
        for required_key in auto_merge_required_keys:
            assert required_key in effective_required_keys, (
                f"{name} enables auto_merge without explicit {required_key}"
            )
