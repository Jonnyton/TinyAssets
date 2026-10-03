"""A read says which stored UI the app will refuse, and how to fix it.

Companion to ``tests/test_app_ui_one_bad_component.py``: the app stops hiding
the good UIs, and the SERVER read tells the agent which one it broke and why.
The agent cannot run the app's JavaScript, so without this it sees a library
that looks fine and a person who says nothing works.

The split this respects: the write path owns what the server's own stores
depend on (``_check_component`` -- bounds, assets, libraries, script_type) and
deliberately does not police the rendering contract. So ``app_ui_renderability``
checks exactly what a STORED entry can still fail, and it only reports: no
write starts refusing because of it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tinyassets.custom_agents import (
    APP_UI_COMPONENT_FIELDS,
    APP_UI_FORMAT_VERSION,
    APP_UI_KIND,
    APP_UI_MAX_NAME,
    APP_UI_OPTIONAL_COMPONENT_FIELDS,
    app_ui_index,
    app_ui_renderability,
    save_app_ui,
)

ALICE = "alice"
HOME = "u-alice"
#: The founder's actual value: a timestamp used as a cache-buster.
CACHE_BUSTER = 1791005187


def _bundle(**over) -> dict:
    return {"kind": APP_UI_KIND, "version": APP_UI_FORMAT_VERSION, "ui_id": "office",
            "name": "Office", "markup": "<div>Lobby</div>", "style": "", "script": "",
            **over}


def test_a_good_component_is_renderable() -> None:
    assert app_ui_renderability(_bundle()) == {}
    # Every optional field present is still fine.
    assert app_ui_renderability(_bundle(libraries=["three"], script_type="module",
                                        assets={})) == {}


def test_the_founders_timestamp_version_names_itself_and_the_fix() -> None:
    refusal = app_ui_renderability(_bundle(version=CACHE_BUSTER))
    assert str(CACHE_BUSTER) in refusal["reason"]
    assert "not supported" in refusal["reason"]
    # The hint has to say the thing the agent got wrong, or it will do it again.
    assert "FORMAT version" in refusal["hint"]
    assert "cache-buster" in refusal["hint"]
    assert "revision moves" in refusal["hint"], "and what to do instead"
    assert "sha256" in refusal["hint"]


@pytest.mark.parametrize(("entry", "expected"), [
    ("not an object", "not an object"),
    ({}, "missing"),
    ({**_bundle(), "build_id": "7"}, "does not render: build_id"),
    ({**_bundle(), "kind": "something.else"}, f"not a {APP_UI_KIND}"),
    (_bundle(version="1"), "not supported"),
    (_bundle(version=True), "not supported"),
    (_bundle(ui_id="Office Tower"), "ui_id must be"),
    (_bundle(ui_id=""), "ui_id must be"),
    (_bundle(name="  "), "name must be"),
    (_bundle(name="x" * (APP_UI_MAX_NAME + 1)), "name must be"),
    (_bundle(markup=None), "markup must be a string"),
    (_bundle(script=42), "script must be a string"),
])
def test_each_way_a_stored_entry_can_be_unrenderable(entry, expected) -> None:
    refusal = app_ui_renderability(entry)
    assert refusal, f"{entry!r} should not be renderable"
    assert expected in refusal["reason"], refusal
    assert refusal["hint"], "every refusal carries a fix the agent can act on"


def test_a_spare_field_is_refused_so_a_build_id_is_not_the_answer() -> None:
    """Why the guidance cannot say "use a build id instead".

    There is no field to put one in: anything outside the component contract is
    refused by the app, so inventing a cache-buster field reproduces this P1 by
    another route.
    """
    refusal = app_ui_renderability({**_bundle(), "build_id": "7"})
    assert "build_id" in refusal["reason"]
    assert "build_id" not in str(APP_UI_COMPONENT_FIELDS + APP_UI_OPTIONAL_COMPONENT_FIELDS)


def test_the_index_marks_each_ui_and_only_the_broken_one(tmp_path) -> None:
    """The whole point: a library with one bad entry still reads as a library."""
    library = [_bundle(ui_id="office", name="Office building"),
               _bundle(ui_id="furry-house", name="Furry House", version=CACHE_BUSTER),
               _bundle(ui_id="village", name="Village")]
    saved = save_app_ui(tmp_path, owner_user_id=ALICE, universe_id=HOME,
                        expected_revision=0, changes={"ui_library": library})
    # The write really does accept it -- which is how the row got this way.
    assert saved["ui_library"] == library

    index = app_ui_index(saved)
    by_id = {entry["ui_id"]: entry for entry in index["uis"]}
    assert len(by_id) == 3, "every UI is still listed"
    assert by_id["office"]["renderable"] is True
    assert by_id["village"]["renderable"] is True
    assert "reason" not in by_id["office"] and "fix" not in by_id["office"]

    bad = by_id["furry-house"]
    assert bad["renderable"] is False
    assert str(CACHE_BUSTER) in bad["reason"]
    assert "FORMAT version" in bad["fix"]
    assert bad["name"] == "Furry House", "named, so the person can be told which"


def test_a_non_dict_entry_does_not_crash_the_index() -> None:
    assert app_ui_index({"ui_library": ["nonsense", None]})["uis"] == []


def test_the_python_contract_matches_the_app_that_enforces_it() -> None:
    """These constants are a mirror; the app is the authority.

    A drift here is worse than no check: the read would tell the agent a UI is
    fine while the app refuses it, or name a field the app accepts.
    """
    source = Path("tinyassets/onboarding/app_ui.js").read_text(encoding="utf-8")
    assert f'KIND:"{APP_UI_KIND}"' in source
    assert f"VERSION:{APP_UI_FORMAT_VERSION}," in source

    def listed(name: str) -> tuple[str, ...]:
        found = re.search(name + r":\[(.*?)\]", source)
        assert found, name
        return tuple(sorted(re.findall(r'"([a-z_]+)"', found.group(1))))

    assert listed("FIELDS") == tuple(sorted(APP_UI_COMPONENT_FIELDS))
    assert listed("OPTIONAL") == tuple(sorted(APP_UI_OPTIONAL_COMPONENT_FIELDS))
    assert f"MAX_NAME:{APP_UI_MAX_NAME}," in source
    assert "ID_RE:/^[a-z0-9][a-z0-9-]{0,63}$/" in source


def test_the_interfaces_chapter_says_version_is_the_format_version() -> None:
    """The agent-facing guidance, so the next agent does not repeat it."""
    from tinyassets.engine_mcp_server import _WRITE_GRAPH_INTERFACES_CHAPTER as chapter

    flat = " ".join(chapter.split())
    assert "FORMAT version" in flat
    assert "not a revision, a build number or a cache-buster" in flat
    assert "renderable" in flat, "and how to find out which UI is refused"
    # It must not send the agent after a field that does not exist. There IS no
    # build id in this repo, so the only allowed mention is the one that says
    # there is nowhere to put one -- naming the move it should not make.
    for sentence in re.split(r"(?<=[.:])\s", flat):
        if "build id" in sentence:
            assert "nowhere to put" in sentence, sentence
    assert "nowhere to put a build id" in flat, (
        "the guidance pre-empts inventing a cache-buster field")
