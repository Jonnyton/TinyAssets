"""Related-page projections must reuse the root wiki visibility boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_wiki(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(wiki_root))
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path / "data"))
    return wiki_root


def _page(
    wiki_root: Path,
    *,
    slug: str,
    title: str,
    body: str,
    visibility: str | None = None,
) -> Path:
    target = wiki_root / "pages" / "authority" / f"{slug}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    visibility_line = (
        f"visibility: {visibility}\n" if visibility is not None else ""
    )
    target.write_text(
        f"---\ntitle: {title}\n{visibility_line}---\n\n{body}\n",
        encoding="utf-8",
    )
    return target


def _projection(branch_def_id: str) -> dict:
    from tinyassets.api.branches import _related_wiki_pages

    return _related_wiki_pages({
        "branch_def_id": branch_def_id,
        "node_defs": [],
    })


def test_hidden_matches_are_filtered_before_match_sort_cap_and_count(
    isolated_wiki: Path,
) -> None:
    for index in range(20):
        _page(
            isolated_wiki,
            slug=f"hidden-{index:02d}",
            title=f"AAA Hidden {index:02d}",
            body=f"secret-branch hidden-secret-{index}",
            visibility="private",
        )
    for index in range(22):
        _page(
            isolated_wiki,
            slug=f"visible-{index:02d}",
            title=f"Visible {index:02d}",
            body=f"secret-branch public-body-{index}",
        )

    projected = _projection("secret-branch")
    encoded = json.dumps(projected, sort_keys=True)

    assert len(projected["items"]) == 20
    assert projected["truncated_count"] == 2
    assert all("Visible" in item["title"] for item in projected["items"])
    assert "Hidden" not in encoded
    assert "hidden-secret" not in encoded
    assert all("filtered" not in key for key in projected)


def test_all_hidden_matches_return_stable_empty_projection(
    isolated_wiki: Path,
) -> None:
    _page(
        isolated_wiki,
        slug="only-secret",
        title="Only Secret",
        body="all-hidden-branch body-secret",
        visibility="private",
    )

    projected = _projection("all-hidden-branch")

    assert projected == {"items": [], "truncated_count": 0}
    assert "Only Secret" not in json.dumps(projected)
    assert "body-secret" not in json.dumps(projected)


def test_public_related_page_keeps_stable_fields(
    isolated_wiki: Path,
) -> None:
    _page(
        isolated_wiki,
        slug="public-plan",
        title="Public Plan",
        body="public-branch is described here.",
    )

    projected = _projection("public-branch")

    assert projected["truncated_count"] == 0
    assert projected["items"] == [{
        "path": "pages/authority/public-plan.md",
        "title": "Public Plan",
        "summary": "public-branch is described here.",
        "matched_via": ["branch_def_id"],
    }]


def test_related_paths_are_subset_of_blank_context_root_wiki_listing(
    isolated_wiki: Path,
) -> None:
    _page(
        isolated_wiki,
        slug="public-match",
        title="Public Match",
        body="subset-branch public.",
    )
    _page(
        isolated_wiki,
        slug="private-match",
        title="Private Match",
        body="subset-branch private.",
        visibility="private",
    )
    _page(
        isolated_wiki,
        slug="public-unrelated",
        title="Public Unrelated",
        body="nothing relevant.",
    )

    from tinyassets.api.wiki import _wiki_list

    root = json.loads(_wiki_list(universe_id=""))
    root_paths = {
        item["path"] for item in root["promoted"] + root["drafts"]
    }
    related_paths = {
        item["path"] for item in _projection("subset-branch")["items"]
    }

    assert related_paths == {"pages/authority/public-match.md"}
    assert related_paths <= root_paths
