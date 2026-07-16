"""Patch-loop S4 (GitHub-native): the merge PREFERENCE vocabulary.

The local eligibility evaluator was deleted when GitHub became authoritative for
review/merge state — GitHub decides eligibility (rulesets + required checks +
mergeability). What survives is the off-GitHub product preference vocabulary
(manual / auto / not_before) + small pure helpers. Pure-function tests (no IO).
"""

from __future__ import annotations

from tinyassets import merge_policy as mp


def test_preferences_are_the_three_expected():
    assert mp.MERGE_PREFERENCES == frozenset({"manual", "auto", "not_before"})
    assert mp.DEFAULT_MERGE_PREFERENCE == "manual"


def test_normalize_preference_defaults_and_trims():
    assert mp.normalize_preference(None) == "manual"
    assert mp.normalize_preference("") == "manual"
    assert mp.normalize_preference("  AUTO ") == "auto"
    assert mp.normalize_preference("Not_Before") == "not_before"
    # Unknown is returned as-is; callers reject via MERGE_PREFERENCES membership.
    assert mp.normalize_preference("yolo") == "yolo"


def test_is_autonomous():
    assert mp.is_autonomous("auto") is True
    assert mp.is_autonomous("not_before") is True
    assert mp.is_autonomous("manual") is False
    # manual is the safe default for unknown/None.
    assert mp.is_autonomous(None) is False


def test_verify_is_green_is_strict():
    assert mp.verify_is_green("pass") is True
    assert mp.verify_is_green("PASS") is True
    assert mp.verify_is_green("fail") is False
    assert mp.verify_is_green("unknown") is False
    assert mp.verify_is_green("") is False
    assert mp.verify_is_green(None) is False


def test_autonomous_preferences_membership():
    assert mp.AUTONOMOUS_PREFERENCES == frozenset({"auto", "not_before"})
    assert mp.MERGE_PREFERENCE_MANUAL not in mp.AUTONOMOUS_PREFERENCES
