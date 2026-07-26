from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "select_do_image.py"


def _load_module():
    assert SCRIPT.exists(), "DigitalOcean image selector is missing"
    spec = importlib.util.spec_from_file_location("select_do_image", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPT.parent))
    return module


def _image(
    slug: str,
    *,
    public: bool = True,
    status: str = "available",
    distribution: str = "Debian",
    regions: list[str] | None = None,
) -> dict:
    return {
        "slug": slug,
        "public": public,
        "status": status,
        "distribution": distribution,
        "regions": regions if regions is not None else ["nyc3"],
    }


def _page(images: list[dict], next_url: str | None = None) -> bytes:
    pages = {"next": next_url} if next_url is not None else {}
    return json.dumps({"images": images, "links": {"pages": pages}}).encode()


def _fetcher(pages: dict[str, bytes]):
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return pages[url]

    return fetch, calls


def test_selects_newest_eligible_image_from_second_page():
    selector = _load_module()
    page_2 = f"{selector.START_URL}&page=2"
    fetch, calls = _fetcher({
        selector.START_URL: _page([_image("debian-12-x64")], page_2),
        page_2: _page([_image("debian-13-x64")]),
    })

    selected = selector.select_image_slug(region="nyc3", fetch_page=fetch)

    assert selected == "debian-13-x64"
    assert calls == [selector.START_URL, page_2]


def test_valid_single_page_catalog_may_omit_links():
    selector = _load_module()
    payload = json.dumps({
        "images": [_image("debian-13-x64")],
    }).encode()

    assert selector.select_image_slug(
        region="nyc3",
        fetch_page=lambda _url: payload,
    ) == "debian-13-x64"


def test_exact_provider_predicate_rejects_higher_ineligible_candidates():
    selector = _load_module()
    fetch, _calls = _fetcher({
        selector.START_URL: _page([
            _image("debian-20-x64", public=False),
            _image("debian-19-x64", status="deleted"),
            _image("debian-18-x64", distribution="Ubuntu"),
            _image("debian-17-x64", regions=["sfo3"]),
            _image("debian-16-x64-extra"),
            _image("debian-13-x64"),
        ]),
    })

    assert selector.select_image_slug(
        region="nyc3",
        fetch_page=fetch,
    ) == "debian-13-x64"


def test_failed_continuation_remains_red():
    selector = _load_module()
    page_2 = f"{selector.START_URL}&page=2"

    def fetch(url: str) -> bytes:
        if url == selector.START_URL:
            return _page([_image("debian-12-x64")], page_2)
        raise RuntimeError("bounded continuation failure")

    with pytest.raises(RuntimeError, match="bounded continuation failure"):
        selector.select_image_slug(region="nyc3", fetch_page=fetch)


@pytest.mark.parametrize(
    "next_url",
    [
        "https://example.com/v2/images?page=2",
        "https://api.digitalocean.com/v2/droplets?page=2",
        "https://api.digitalocean.com:443/v2/images?page=2",
        42,
    ],
)
def test_malformed_or_off_endpoint_continuation_is_rejected(next_url):
    selector = _load_module()
    payload = {
        "images": [_image("debian-12-x64")],
        "links": {"pages": {"next": next_url}},
    }

    with pytest.raises(selector.ImageSelectionError, match="continuation"):
        selector.select_image_slug(
            region="nyc3",
            fetch_page=lambda _url: json.dumps(payload).encode(),
        )


def test_cyclic_continuation_is_rejected():
    selector = _load_module()

    with pytest.raises(selector.ImageSelectionError, match="repeated|cycle"):
        selector.select_image_slug(
            region="nyc3",
            fetch_page=lambda _url: _page(
                [_image("debian-12-x64")],
                selector.START_URL,
            ),
        )


def test_page_budget_exhaustion_is_rejected():
    selector = _load_module()

    def fetch(url: str) -> bytes:
        page = int(url.rsplit("=", 1)[1]) if "&page=" in url else 1
        return _page(
            [_image(f"debian-{10 + page}-x64")],
            f"{selector.START_URL}&page={page + 1}",
        )

    with pytest.raises(selector.ImageSelectionError, match="page budget"):
        selector.select_image_slug(
            region="nyc3",
            fetch_page=fetch,
            max_pages=2,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"images": "not-a-list", "links": {"pages": {}}},
        {"images": [{"slug": "debian-13-x64"}], "links": {"pages": {}}},
        {"images": [], "links": None},
        {"images": [], "links": "not-an-object"},
    ],
)
def test_malformed_inventory_is_rejected(payload):
    selector = _load_module()

    with pytest.raises(selector.ImageSelectionError, match="malformed"):
        selector.select_image_slug(
            region="nyc3",
            fetch_page=lambda _url: json.dumps(payload).encode(),
        )


def test_empty_aggregate_is_rejected_without_static_fallback():
    selector = _load_module()

    with pytest.raises(selector.ImageSelectionError, match="eligible"):
        selector.select_image_slug(
            region="nyc3",
            fetch_page=lambda _url: _page([]),
        )
