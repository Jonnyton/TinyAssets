"""Class and version from a model id alone, with no vendor knowledge.

The whole point is that nobody ships a patch when a vendor names a new model
(founder, 2026-09-26). So the rule is about the SHAPE of an id, and these tables
are the rule: a run of digits or a date stamp is version, everything else -
including a named suffix like -sol - is class.

The real ids below are here because they are the shapes that exist, not because
the code knows them. Nothing in `tinyassets/providers/model_class.py` names a
vendor, and `test_no_vendor_names_in_the_derivation` holds that.
"""

from __future__ import annotations

import pytest

from tinyassets.providers.model_class import (
    model_class_and_version,
    newer,
    newest_per_class,
)


@pytest.mark.parametrize(
    ("model_id", "expected_class", "expected_version"),
    [
        # Dashed numeric versions: the common shape.
        ("claude-opus-4-6", "claude-opus", (4, 6)),
        ("claude-opus-4-7", "claude-opus", (4, 7)),
        ("claude-fable-5-1", "claude-fable", (5, 1)),
        ("claude-haiku-4-5", "claude-haiku", (4, 5)),
        # Dotted versions describe the same thing as dashed ones.
        ("gpt-5.6", "gpt", (5, 6)),
        ("gpt-5-6", "gpt", (5, 6)),
        # A NAMED suffix is class, not version - so these are separate lines.
        ("gpt-5.6-sol", "gpt-sol", (5, 6)),
        ("gpt-5.7-sol", "gpt-sol", (5, 7)),
        ("gpt-5.7-astra", "gpt-astra", (5, 7)),
        # A date stamp is just a number, and orders as one.
        ("claude-opus-4-6-20260115", "claude-opus", (4, 6, 20260115)),
        ("claude-haiku-4-5-20251001", "claude-haiku", (4, 5, 20251001)),
        # No version token at all: its own class, empty version.
        ("some-model", "some-model", ()),
        ("mistral", "mistral", ()),
        # Underscores and slashes are separators too, and the class KEEPS the
        # separator the id used: `some_model` and `some-model` are two ids, so they
        # must stay two classes (Codex on #4028 -- normalising them collapsed the
        # classes and discarded one).
        ("vendor/model-3-1", "vendor/model", (3, 1)),
        ("vendor_model_3_1", "vendor_model", (3, 1)),
        ("some_model", "some_model", ()),
        # Mixed separators in one id keep their own shape rather than being
        # rewritten with whichever separator came first.
        ("vendor/thing-2.5-turbo", "vendor/thing-turbo", (2, 5)),
        # A leading version token still leaves the rest as class.
        ("4-mini", "mini", (4,)),
        # Only numbers: its own class, so it cannot win another class's newest.
        ("4-6", "4-6", (4, 6)),
        # Separators only: unparseable, so its own class.
        ("---", "---", ()),
        # Surrounding whitespace is not part of the id.
        ("  claude-opus-4-6  ", "claude-opus", (4, 6)),
    ],
)
def test_class_and_version_by_shape(model_id, expected_class, expected_version):
    assert model_class_and_version(model_id) == (expected_class, expected_version)


@pytest.mark.parametrize("bad", ["", "   ", None, 5, b"claude-opus-4-6"])
def test_an_unnamed_model_is_refused_rather_than_bucketed(bad):
    """Silently giving it a class would let it win a newest comparison."""
    with pytest.raises(ValueError):
        model_class_and_version(bad)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ((4, 7), (4, 6)),
        ((5,), (4, 9)),
        ((4, 6, 20260115), (4, 6)),      # a dated build of a version is later
        ((4, 10), (4, 9)),               # numeric, not lexical
        ((1,), ()),                      # any version beats none
    ],
)
def test_newer_orders_versions_numerically(left, right):
    assert newer(left, right) and not newer(right, left)


def test_versions_that_describe_the_same_release_are_not_newer_either_way():
    dashed, _ = model_class_and_version("gpt-5-6"), None
    dotted = model_class_and_version("gpt-5.6")
    assert dashed[1] == dotted[1]
    assert not newer(dashed[1], dotted[1]) and not newer(dotted[1], dashed[1])


class Row:
    """The two fields newest_per_class reads. Deliberately not the real store."""

    def __init__(self, model_id, first_verified_at="2026-01-01T00:00:00Z"):
        self.model_id = model_id
        self.first_verified_at = first_verified_at


def _ids(rows):
    return sorted(row.model_id for row in rows)


def test_only_the_newest_of_each_class_is_contributed():
    rows = [Row("claude-opus-4-6"), Row("claude-opus-4-7"), Row("claude-fable-5-1"),
            Row("claude-haiku-4-5")]
    # opus collapses to 4-7; fable and haiku are their own classes.
    assert _ids(newest_per_class(rows)) == [
        "claude-fable-5-1", "claude-haiku-4-5", "claude-opus-4-7"]


def test_a_named_suffix_keeps_its_own_newest():
    rows = [Row("gpt-5.6-sol"), Row("gpt-5.7-sol"), Row("gpt-5.7-astra"), Row("gpt-5.8")]
    assert _ids(newest_per_class(rows)) == ["gpt-5.7-astra", "gpt-5.7-sol", "gpt-5.8"], (
        "-sol and -astra are classes, so each keeps its own newest, and the bare "
        "line keeps its own")


def test_a_dated_build_supersedes_the_undated_one_of_the_same_version():
    rows = [Row("claude-opus-4-6"), Row("claude-opus-4-6-20260115")]
    assert _ids(newest_per_class(rows)) == ["claude-opus-4-6-20260115"]


def test_a_tie_goes_to_the_id_known_to_work_longest():
    """Equal versions: the earlier first-verified time wins, never read order."""
    late = Row("gpt-5-6", "2026-06-01T00:00:00Z")
    early = Row("gpt-5.6", "2026-02-01T00:00:00Z")
    assert _ids(newest_per_class([late, early])) == ["gpt-5.6"]
    # ...and the same answer whichever order the rows arrive in.
    assert _ids(newest_per_class([early, late])) == ["gpt-5.6"]


def test_an_unversioned_id_is_never_dropped_for_being_unusual():
    rows = [Row("some-model"), Row("mistral"), Row("claude-opus-4-7")]
    assert _ids(newest_per_class(rows)) == ["claude-opus-4-7", "mistral", "some-model"]


def test_two_ids_differing_only_by_separator_are_two_classes():
    """Codex on #4028: they collapsed, and newest_per_class discarded one."""
    rows = [Row("some-model"), Row("some_model")]
    assert _ids(newest_per_class(rows)) == ["some-model", "some_model"], (
        "an id this module cannot version is its own class, and these are two ids")


def test_an_equal_version_and_timestamp_tie_is_stable_not_input_ordered():
    """Same catalog, different read order, same answer."""
    same = "2026-02-01T00:00:00Z"
    a, b = Row("gpt-5-6", same), Row("gpt-5.6", same)
    assert _ids(newest_per_class([a, b])) == _ids(newest_per_class([b, a]))
    # ...and it is the lower id, chosen by a rule rather than by arrival.
    assert _ids(newest_per_class([a, b])) == ["gpt-5-6"]


def test_a_row_with_no_usable_id_is_skipped_not_fatal():
    rows = [Row(""), Row("claude-opus-4-7")]
    assert _ids(newest_per_class(rows)) == ["claude-opus-4-7"]


def test_no_vendor_names_in_the_derivation():
    """The module must not have learned any vendor's naming scheme.

    This is the requirement the founder stated -- no patches per provider -- and it
    is checkable. It is checked with the ratchet's OWN rule rather than a second
    one: `check_channel_agnostic.runtime_strings` is what decides whether a name is
    code or documentation, and reusing it means this test cannot drift away from the
    gate that enforces it repo-wide. A docstring may cite an id shape as an example;
    executable code may not. The names in THIS file are test data.
    """
    import importlib.util
    import sys
    from pathlib import Path

    import tinyassets.providers.model_class as module

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "_channel_ratchet", root / "scripts" / "check_channel_agnostic.py")
    ratchet = importlib.util.module_from_spec(spec)
    sys.modules["_channel_ratchet"] = ratchet
    spec.loader.exec_module(ratchet)

    runtime = [text.lower() for text in ratchet.runtime_strings(Path(module.__file__))]
    # The ratchet's own vendor list, plus the model-line names this change could
    # plausibly have been tempted to special-case.
    for vendor in (*ratchet.VENDORS, "opus", "haiku", "sonnet", "fable", "astra"):
        offenders = [text for text in runtime if vendor in text]
        assert not offenders, f"{vendor!r} is named in executable code: {offenders}"
