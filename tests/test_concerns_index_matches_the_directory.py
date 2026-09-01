"""Every concern file is linked from the table, and every link resolves.

`AGENTS.md` names `docs/concerns/README.md` as the thing to skim when an area
has known-unresolved findings, and a concern's whole purpose is to be found by
the next session. On 2026-08-31 ten of twenty-eight files were missing from that
table -- including a **P0** (`authenticated_external_call` failing in production
for three days). Each was filed correctly and then not linked, which is a
one-line omission with the same effect as not filing it.

Filing and linking are two steps, so they drift. This makes them one step: the
table and the directory have to agree, in both directions.
"""
from __future__ import annotations

import pathlib

import pytest

CONCERNS = pathlib.Path(__file__).resolve().parents[1] / "docs" / "concerns"
README = CONCERNS / "README.md"


def _files() -> set[str]:
    return {p.name for p in CONCERNS.glob("*.md") if p.name != "README.md"}


def test_every_concern_file_is_linked_from_the_readme() -> None:
    """A concern nobody links is a concern nobody reads."""
    text = README.read_text(encoding="utf-8")
    unlinked = sorted(name for name in _files() if name not in text)
    assert not unlinked, (
        "these concern files are not mentioned anywhere in "
        "docs/concerns/README.md, so nothing points at them:\n  "
        + "\n  ".join(unlinked)
        + "\n\nIf you did not file these: CI tests your PR MERGED INTO main, so "
        "a concern filed in another lane while your PR was open shows up here. "
        "Adding the row is one line and the right fix -- the index is only "
        "useful if it is complete at merge time."
    )


def test_every_link_in_the_readme_resolves_to_a_file() -> None:
    """The other direction, and the one that bites after a RESOLUTION.

    A concern is resolved by DELETING its file (AGENTS.md). Delete the file and
    leave the row and the table advertises a finding that is fixed, with a link
    that 404s in the browser and resolves to nothing in a clone.
    """
    import re

    text = README.read_text(encoding="utf-8")
    linked = set(re.findall(r"\]\((\d{4}-\d{2}-\d{2}-[^)]+\.md)\)", text))
    dangling = sorted(name for name in linked if not (CONCERNS / name).exists())
    assert not dangling, (
        "docs/concerns/README.md links files that do not exist "
        "(resolved without removing the row?):\n  " + "\n  ".join(dangling)
    )


@pytest.mark.parametrize("name", sorted(_files()))
def test_each_concern_says_when_it_was_filed(name: str) -> None:
    """The date is what makes "re-verify a premise before acting on it" possible.

    Deliberately loose: it accepts `**Filed:**`, `**Found**`, `**Hit live**` and
    the other openings already in use here, because the point is that a reader
    can date the claim -- not that everyone words it identically.
    """
    head = (CONCERNS / name).read_text(encoding="utf-8")[:1200]
    assert "2026-" in head or "2025-" in head, (
        f"{name} does not date its claim in the first 1200 characters, so a "
        "reader cannot tell how stale it is"
    )
