"""A founder's private words must not become world-readable by conversing.

The exposure these close, reproduced by cross-family review on 2026-08-06:
a founder tells their universe something confidential; the founder turn commits
it as canon; the universe was created ``public`` by default; anonymous
``read_page`` and search then return it.

The fix is on the VISIBILITY side, never on the commit side — a founder should
be able to just talk and have the universe learn. No approval step, no prompt.
So every test here asserts BOTH halves: the page is withheld from a stranger AND
still committed and readable by its owner.
"""

from __future__ import annotations

import pytest

from tinyassets.api import visibility, wiki


def _meta_of(content: str) -> dict[str, str]:
    meta, _ = wiki._parse_frontmatter(content)
    return meta


def test_learned_canon_declares_a_restrictive_visibility():
    """The stamp exists at all — everything else depends on it."""
    stamped = wiki._stamp_page_visibility(
        "The Q3 acquisition target is Acme.", wiki.CANON_DEFAULT_VISIBILITY
    )

    assert _meta_of(stamped)["visibility"] == "private"


def test_the_default_is_restrictive_not_permissive():
    """A permissive default would reintroduce the whole defect silently."""
    level = visibility.parse_level(wiki.CANON_DEFAULT_VISIBILITY)

    assert level is not None, "the canon default must be a level the gate parses"
    assert level.read_content is False
    assert level.read_metadata is False
    assert level.discover_existence is False


def test_a_stranger_cannot_read_learned_canon_even_in_a_public_universe():
    """The reproduced exposure, as an assertion.

    `visibility.DEFAULT_CREATE_VISIBILITY` is "public", so this is the real
    configuration — not a contrived private universe.
    """
    assert visibility.DEFAULT_CREATE_VISIBILITY == "public", (
        "if this changes, re-read this test: it exists because universes are "
        "public by default"
    )
    stamped = wiki._stamp_page_visibility(
        "The Q3 acquisition target is Acme.", wiki.CANON_DEFAULT_VISIBILITY
    )
    meta = _meta_of(stamped)

    # No universe grant -> the stranger's view.
    assert visibility.page_content_permitted(meta, "u-not-mine") is False
    assert visibility.page_visible_in_listing(meta, "u-not-mine") is False


def test_the_model_cannot_opt_a_page_out_of_the_restriction():
    """Canon content is model-generated, so its own claim is not authority."""
    hostile = (
        "---\nvisibility: public\ncontent_visibility: public\n---\n"
        "The Q3 acquisition target is Acme."
    )

    stamped = wiki._stamp_page_visibility(hostile, wiki.CANON_DEFAULT_VISIBILITY)
    meta = _meta_of(stamped)

    assert meta["visibility"] == "private"
    assert "content_visibility" not in meta, (
        "a second key answering the same question is a bypass waiting to be read"
    )
    assert visibility.page_content_permitted(meta, "u-not-mine") is False


def test_stamping_preserves_the_body_and_other_frontmatter():
    """The fix must not corrupt what the universe actually learned."""
    original = (
        "---\ntitle: Acquisition\ncategory: lore\n---\n"
        "The Q3 acquisition target is Acme.\n\nSecond paragraph."
    )

    stamped = wiki._stamp_page_visibility(original, wiki.CANON_DEFAULT_VISIBILITY)
    meta, body = wiki._parse_frontmatter(stamped)

    assert meta["title"] == "Acquisition"
    assert meta["category"] == "lore"
    assert "The Q3 acquisition target is Acme." in body
    assert "Second paragraph." in body


def test_a_page_with_no_frontmatter_still_gets_stamped():
    """Learned canon usually arrives as a bare body; that is the common path."""
    stamped = wiki._stamp_page_visibility("bare body", wiki.CANON_DEFAULT_VISIBILITY)
    meta, body = wiki._parse_frontmatter(stamped)

    assert meta["visibility"] == "private"
    assert body.strip() == "bare body"


@pytest.mark.parametrize("level", ["public", "unlisted"])
def test_an_explicit_permissive_visibility_is_still_honoured(level):
    """Publishing stays possible — this closes a default, it does not remove a capability."""
    stamped = wiki._stamp_page_visibility("published note", level)

    assert _meta_of(stamped)["visibility"] == level


def test_the_real_canon_write_applies_the_stamp(tmp_path, monkeypatch):
    """Through `write_universe_canon`, not the helper — the wiring is the fix.

    Every other test here calls `_stamp_page_visibility` directly, so all of them
    stay green with the stamping call DELETED from `write_universe_canon`; a
    mutation probe caught exactly that. Testing the component is not testing that
    anything uses it.
    """
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))

    wiki.write_universe_canon(
        "u-canon-test",
        category="lore",
        filename="Acquisition",
        content="The Q3 acquisition target is Acme.",
        log_entry="test",
    )

    written = [
        path
        for path in (tmp_path / "u-canon-test").rglob("*.md")
        if "Acquisition" in path.stem or "acquisition" in path.stem.lower()
    ]
    assert written, f"no canon page was written under {tmp_path / 'u-canon-test'}"

    raw = written[0].read_text(encoding="utf-8")
    meta = _meta_of(raw)
    assert meta.get("visibility") == "private", (
        f"canon page {written[0].name} did not carry the restriction: {meta!r}"
    )
    assert "The Q3 acquisition target is Acme." in raw
    assert visibility.page_content_permitted(meta, "u-not-mine") is False


def test_a_multiline_frontmatter_value_survives_stamping():
    """Flattening a block value loses its tail AND promotes it to top level."""
    original = (
        "---\ntitle: Note\nsummary:\n  first line\n  second line\ntags: a, b\n---\n"
        "body text"
    )

    stamped = wiki._stamp_page_visibility(original, wiki.CANON_DEFAULT_VISIBILITY)
    meta, body = wiki._parse_frontmatter(stamped)

    assert meta["summary"] == "first line\nsecond line", (
        f"multi-line value was corrupted: {meta.get('summary')!r}"
    )
    assert meta["title"] == "Note"
    assert meta["tags"] == "a, b"
    assert meta["visibility"] == "private"
    assert body.strip() == "body text"


def test_frontmatter_cannot_smuggle_a_permissive_visibility():
    """A continuation line that looks like a key must not outrank the stamp.

    Model-generated canon can contain anything. If a block value's continuation
    line were promoted to a top-level `visibility: public`, and it landed after
    ours, `_parse_frontmatter`'s last-wins assignment would hand the page to
    anonymous readers.
    """
    hostile = (
        "---\ntitle: Note\nvisibility: public\nsummary:\n"
        "  intro\n  visibility: public\n---\n"
        "The Q3 acquisition target is Acme."
    )

    stamped = wiki._stamp_page_visibility(hostile, wiki.CANON_DEFAULT_VISIBILITY)
    meta = _meta_of(stamped)

    assert meta["visibility"] == "private"
    assert visibility.page_content_permitted(meta, "u-not-mine") is False


@pytest.mark.parametrize(
    "header",
    ["summary: |", "summary: >", "summary: |-", "summary: |+", "summary: >-"],
    ids=["literal", "folded", "literal-strip", "literal-keep", "folded-strip"],
)
def test_yaml_block_scalars_survive_stamping(header):
    """Standard YAML block scalars, which my first regression test missed.

    `_parse_frontmatter` records `summary: |` as the literal string "|" and skips
    the indented continuations, so an implementation that re-renders from the
    parsed dict DELETES the content. The parser being lossy is pre-existing and
    was harmless while canon was written through unchanged; stamping is what
    turned a lossy read into a lossy write. Caught by cross-family review.
    """
    original = (
        f"---\ntitle: Note\n{header}\n  first line\n  second line\n---\n"
        "body text"
    )

    stamped = wiki._stamp_page_visibility(original, wiki.CANON_DEFAULT_VISIBILITY)

    assert "first line" in stamped, f"block scalar content lost with {header!r}"
    assert "second line" in stamped, f"block scalar tail lost with {header!r}"
    assert header in stamped, "the block scalar header itself was rewritten"
    assert _meta_of(stamped)["visibility"] == "private"


def test_the_body_is_preserved_byte_for_byte():
    """Leading blank lines are part of the document, not noise to trim."""
    body = "\n\n  indented opening\n\ntrailing paragraph\n"
    original = f"---\ntitle: Note\n---\n{body}"

    stamped = wiki._stamp_page_visibility(original, wiki.CANON_DEFAULT_VISIBILITY)

    assert stamped.endswith(body), "the markdown body was altered by stamping"


def test_unknown_frontmatter_keys_are_preserved_verbatim():
    """Stamping must not be a filter on frontmatter it does not understand."""
    original = (
        "---\ntitle: Note\nweird_key: {nested: value}\nlist_key:\n  - one\n  - two\n---\n"
        "body"
    )

    stamped = wiki._stamp_page_visibility(original, wiki.CANON_DEFAULT_VISIBILITY)

    assert "weird_key: {nested: value}" in stamped
    assert "  - one" in stamped
    assert "  - two" in stamped


def test_dropping_a_visibility_key_takes_its_continuation_lines_with_it():
    """Otherwise the removed key leaves orphaned indented fragments behind."""
    original = (
        "---\ntitle: Note\nvisibility:\n  public\ntags: a\n---\nbody"
    )

    stamped = wiki._stamp_page_visibility(original, wiki.CANON_DEFAULT_VISIBILITY)
    meta = _meta_of(stamped)

    assert "  public" not in stamped, (
        "the dropped key's continuation line was left orphaned in the frontmatter"
    )
    assert meta["title"] == "Note"
    assert meta["tags"] == "a"
    assert meta["visibility"] == "private"


def test_the_writer_and_reader_agree_on_which_keys_declare_visibility():
    """A key the reader honours but the writer leaves in place is a bypass.

    The list is duplicated (`visibility` imports from `wiki`, so the writer
    cannot import the reader's copy). Duplication without this assertion is how
    a key gets added on one side only.
    """
    assert set(wiki._VISIBILITY_FRONTMATTER_KEYS) == set(
        visibility._PAGE_VISIBILITY_KEYS
    ), "writer and reader disagree about which frontmatter keys grant content"


def test_a_granted_reader_still_sees_it(monkeypatch):
    """The founder must lose nothing. Conversing stays frictionless.

    Without this the 'fix' could be a page nobody can read, which would pass
    every stranger-side assertion above and still be broken.
    """
    stamped = wiki._stamp_page_visibility(
        "The Q3 acquisition target is Acme.", wiki.CANON_DEFAULT_VISIBILITY
    )
    meta = _meta_of(stamped)

    monkeypatch.setattr(visibility, "_reader_has_grant", lambda universe_id: True)

    assert visibility.page_content_permitted(meta, "u-mine") is True
    assert visibility.page_visible_in_listing(meta, "u-mine") is True
