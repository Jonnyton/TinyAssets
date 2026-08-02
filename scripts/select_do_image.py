#!/usr/bin/env python3
"""Select the newest region-compatible public Debian x64 image."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from do_api_request import DigitalOceanRequestError, api_request

START_URL = (
    "https://api.digitalocean.com/v2/images"
    "?type=distribution&per_page=200"
)
MAX_PAGES = 10
_SLUG_PATTERN = re.compile(r"debian-(\d+)-x64")


class ImageSelectionError(RuntimeError):
    """The provider catalog could not yield one safe image selection."""


def _canonical_catalog_url(url: str) -> str:
    if not isinstance(url, str):
        raise ImageSelectionError("malformed image catalog continuation")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.digitalocean.com"
        or parsed.username
        or parsed.password
        or parsed.path != "/v2/images"
        or parsed.fragment
    ):
        raise ImageSelectionError(
            "image catalog continuation left the DigitalOcean images endpoint"
        )
    normalized_query = urlencode(sorted(parse_qsl(
        parsed.query,
        keep_blank_values=True,
    )))
    return urlunsplit(("https", "api.digitalocean.com", parsed.path, normalized_query, ""))


def _decode_page(raw: bytes) -> tuple[list[dict], str | None]:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ImageSelectionError("malformed image catalog JSON") from exc
    if not isinstance(payload, dict):
        raise ImageSelectionError("malformed image catalog payload")

    images = payload.get("images")
    if not isinstance(images, list):
        raise ImageSelectionError("malformed image catalog inventory")
    if "links" not in payload:
        pages = {}
    elif isinstance(payload["links"], dict):
        links = payload["links"]
        pages = links.get("pages", {})
        if not isinstance(pages, dict):
            raise ImageSelectionError("malformed image catalog pagination")
    else:
        raise ImageSelectionError("malformed image catalog pagination")

    for image in images:
        if (
            not isinstance(image, dict)
            or not isinstance(image.get("slug"), str)
            or not isinstance(image.get("public"), bool)
            or not isinstance(image.get("status"), str)
            or not isinstance(image.get("distribution"), str)
            or not isinstance(image.get("regions"), list)
            or not all(
                isinstance(region, str)
                for region in image["regions"]
            )
        ):
            raise ImageSelectionError("malformed image catalog inventory")

    next_url = pages.get("next")
    if next_url is not None and not isinstance(next_url, str):
        raise ImageSelectionError("malformed image catalog continuation")
    return images, next_url


def select_image_slug(
    *,
    region: str,
    fetch_page: Callable[[str], bytes],
    max_pages: int = MAX_PAGES,
) -> str:
    if not region:
        raise ImageSelectionError("drill region is empty")
    if max_pages < 1:
        raise ImageSelectionError("image catalog page budget must be positive")

    candidates: list[tuple[int, str]] = []
    seen: set[str] = set()
    next_url: str | None = START_URL

    for _page_number in range(1, max_pages + 1):
        if next_url is None:
            break
        canonical_url = _canonical_catalog_url(next_url)
        if canonical_url in seen:
            raise ImageSelectionError(
                "image catalog continuation repeated or formed a cycle"
            )
        seen.add(canonical_url)

        images, next_url = _decode_page(fetch_page(next_url))
        for image in images:
            slug = image["slug"]
            match = _SLUG_PATTERN.fullmatch(slug)
            if (
                image["public"] is True
                and image["status"] == "available"
                and image["distribution"] == "Debian"
                and region in image["regions"]
                and match is not None
            ):
                candidates.append((int(match.group(1)), slug))
    else:
        if next_url is not None:
            raise ImageSelectionError(
                f"image catalog exceeded {max_pages}-page budget"
            )

    if not candidates:
        raise ImageSelectionError(
            f"no eligible public Debian x64 image serves region {region}"
        )
    return max(candidates)[1]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    token = os.environ.get("DO_TOKEN", "")

    def fetch_page(url: str) -> bytes:
        return api_request(
            method="GET",
            url=url,
            token=token,
        )

    try:
        slug = select_image_slug(
            region=args.region,
            fetch_page=fetch_page,
        )
    except (DigitalOceanRequestError, ImageSelectionError, ValueError) as exc:
        print(
            f"::error::DigitalOcean image selection failed: {exc}",
            file=sys.stderr,
        )
        return 1
    print(slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
