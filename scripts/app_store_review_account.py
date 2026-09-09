"""Save a dedicated App Review demo account through App Store Connect.

All credentials are supplied through environment variables. The script never
prints the reviewer password or Apple's response bodies.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any

import jwt

BASE_URL = "https://api.appstoreconnect.apple.com/v1"


def _required_environment(environ: Mapping[str, str]) -> dict[str, str]:
    names = (
        "API_KEY_ID",
        "API_ISSUER_ID",
        "API_KEY_B64",
        "REVIEW_USERNAME",
        "REVIEW_PASSWORD",
        "APP_ID",
        "VERSION",
    )
    values = {name: environ.get(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise SystemExit(f"missing required values: {', '.join(missing)}")
    if not values["APP_ID"].isdigit():
        raise SystemExit("APP_ID must contain digits only")
    return values


def _token(values: Mapping[str, str], *, now: int | None = None) -> str:
    issued_at = int(time.time()) if now is None else now
    private_key = base64.b64decode(values["API_KEY_B64"], validate=True)
    return jwt.encode(
        {
            "iss": values["API_ISSUER_ID"],
            "iat": issued_at - 5,
            "exp": issued_at + 600,
            "aud": "appstoreconnect-v1",
        },
        private_key,
        algorithm="ES256",
        headers={"kid": values["API_KEY_ID"], "typ": "JWT"},
    )


class AppStoreConnect:
    def __init__(self, token: str) -> None:
        self._token = token

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        not_found_ok: bool = False,
    ) -> Any:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            BASE_URL + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and not_found_ok:
                return None
            # A validation response could contain submitted field values. Never
            # copy an App Store Connect response body into CI logs.
            raise SystemExit(f"App Store Connect API returned HTTP {exc.code}") from None


def save_review_account(client: AppStoreConnect, values: Mapping[str, str]) -> tuple[str, str]:
    query = urllib.parse.urlencode(
        {"filter[platform]": "IOS", "filter[versionString]": values["VERSION"]}
    )
    versions = client.request(
        "GET", f"/apps/{values['APP_ID']}/appStoreVersions?{query}"
    )["data"]
    if len(versions) != 1:
        raise SystemExit(
            f"expected one iOS {values['VERSION']} version, found {len(versions)}"
        )
    version_id = versions[0]["id"]

    review_response = client.request(
        "GET",
        f"/appStoreVersions/{version_id}/appStoreReviewDetail",
        not_found_ok=True,
    )
    review = None if review_response is None else review_response["data"]
    attributes = {
        "demoAccountName": values["REVIEW_USERNAME"],
        "demoAccountPassword": values["REVIEW_PASSWORD"],
        "demoAccountRequired": True,
    }
    if review is None:
        result = client.request(
            "POST",
            "/appStoreReviewDetails",
            {
                "data": {
                    "type": "appStoreReviewDetails",
                    "attributes": attributes,
                    "relationships": {
                        "appStoreVersion": {
                            "data": {"type": "appStoreVersions", "id": version_id}
                        }
                    },
                }
            },
        )
    else:
        review_id = review["id"]
        result = client.request(
            "PATCH",
            f"/appStoreReviewDetails/{review_id}",
            {
                "data": {
                    "type": "appStoreReviewDetails",
                    "id": review_id,
                    "attributes": attributes,
                }
            },
        )

    saved = result["data"]
    saved_attributes = saved.get("attributes", {})
    if saved_attributes.get("demoAccountName") != values["REVIEW_USERNAME"]:
        raise SystemExit("App Store Connect did not retain the reviewer username")
    if saved_attributes.get("demoAccountRequired") is not True:
        raise SystemExit("App Store Connect did not mark the reviewer account as required")
    return version_id, saved["id"]


def main() -> None:
    values = _required_environment(os.environ)
    client = AppStoreConnect(_token(values))
    version_id, review_detail_id = save_review_account(client, values)
    print(
        "Saved App Review account for "
        f"app={values['APP_ID']} version={values['VERSION']} "
        f"version_id={version_id} review_detail_id={review_detail_id}"
    )


if __name__ == "__main__":
    main()
