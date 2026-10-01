"""The committed brand exports must stay bound to their one drawing source.

The check itself lives in scripts/invariants/brand_parity.py (the `invariants`
gate runs it); this test runs the same code rather than a second copy of it.
"""

from __future__ import annotations

from pathlib import Path

from scripts.invariants import Status
from scripts.invariants.brand_parity import (
    BrandParityInvariant,
    app_badge_data_uri,
    app_badge_problems,
)

REPO = Path(__file__).resolve().parents[1]
TILE = (REPO / "WebSite" / "brand" / "mark-tile.svg").read_text(encoding="utf-8")


def _app(uri: str) -> str:
    return (
        f'<head><link rel="icon" href="{uri}" /></head>'
        f'<style>:root{{--brand-mark:url("{uri}");}}'
        ".brand-dot{background:var(--brand-mark) center/contain no-repeat}</style>"
    )


def test_every_brand_export_matches_the_canonical_receipt() -> None:
    result = BrandParityInvariant()._check()
    assert result.status is Status.OK, result.evidence


def test_app_html_is_checked_by_its_badge_not_by_a_whole_file_hash() -> None:
    """A feature edit to app.html must not need the brand exporter re-run."""
    receipt = (REPO / "WebSite" / "brand" / "generated-assets.json").read_text(
        encoding="utf-8"
    )
    assert "tinyassets/onboarding/app.html" not in receipt
    current = app_badge_data_uri(TILE)
    assert app_badge_problems(_app(current) + "<main>any feature</main>", TILE) == []


def test_a_stale_badge_in_either_place_is_a_violation() -> None:
    current = app_badge_data_uri(TILE)
    stale = app_badge_data_uri(TILE.replace("<svg", "<svg data-old='1'", 1))
    assert stale != current
    favicon_stale = _app(current).replace(f'href="{current}"', f'href="{stale}"')
    glyph_stale = _app(current).replace(f'url("{current}")', f'url("{stale}")')
    assert app_badge_problems(favicon_stale, TILE) == [
        "app.html must have exactly one favicon link, the current tile mark (found 1)"
    ]
    assert app_badge_problems(glyph_stale, TILE) == [
        "app.html must declare --brand-mark exactly once, as the current tile mark (found 1)"
    ]


def test_the_badge_is_checked_as_the_browser_uses_it() -> None:
    """Each of these kept the right substring somewhere and showed a retired mark."""
    current = app_badge_data_uri(TILE)
    good = _app(current)
    retired = 'url("/retired-mark.svg")'
    overridden = good.replace("</style>", f".brand-dot{{--brand-mark:{retired}}}</style>")
    unused_variable = good.replace("background:var(--brand-mark)", f"background:{retired}")
    commented_out = good.replace(
        f'<link rel="icon" href="{current}" />',
        f'<!-- <link rel="icon" href="{current}" /> --><link rel="icon" href="/retired.ico" />',
    )
    second_icon = good.replace("</head>", '<link rel="shortcut icon" href="/x.ico"></head>')
    for name, html in [
        ("overridden", overridden),
        ("unused_variable", unused_variable),
        ("commented_out", commented_out),
        ("second_icon", second_icon),
    ]:
        assert app_badge_problems(html, TILE), name
