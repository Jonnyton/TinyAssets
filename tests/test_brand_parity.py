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
        f'<style>:root{{--brand-mark:url("{uri}");}}</style>'
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
        "app.html favicon is not the current tile mark"
    ]
    assert app_badge_problems(glyph_stale, TILE) == [
        "app.html --brand-mark is not the current tile mark"
    ]
