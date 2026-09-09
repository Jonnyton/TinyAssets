"""Inspect and, when authorized, release an approved App Store version.

The App Store Connect API credentials stay in the protected GitHub environment.
This script prints only non-secret release state and never response bodies.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any

from app_store_review_account import AppStoreConnect, _token


def _required_environment(environ: Mapping[str, str]) -> dict[str, str]:
    names = (
        "API_KEY_ID",
        "API_ISSUER_ID",
        "API_KEY_B64",
        "APP_ID",
        "VERSION",
        "SUBMISSION_ID",
    )
    values = {name: environ.get(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise SystemExit(f"missing required values: {', '.join(missing)}")
    if not values["APP_ID"].isdigit():
        raise SystemExit("APP_ID must contain digits only")
    return values


def _boolean(value: str, *, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise SystemExit(f"{name} must be true/false, yes/no, or 1/0")


def release_status(
    client: AppStoreConnect, values: Mapping[str, str]
) -> tuple[str, str, bool, str]:
    query = urllib.parse.urlencode(
        {
            "filter[platform]": "IOS",
            "filter[versionString]": values["VERSION"],
            "fields[appStoreVersions]": "appStoreState,downloadable,versionString",
        }
    )
    versions = client.request(
        "GET", f"/apps/{values['APP_ID']}/appStoreVersions?{query}"
    )["data"]
    if len(versions) != 1:
        raise SystemExit(
            f"expected one iOS {values['VERSION']} version, found {len(versions)}"
        )
    version = versions[0]
    attributes = version.get("attributes", {})
    app_store_state = str(attributes.get("appStoreState", "")).strip()
    if not app_store_state:
        raise SystemExit("App Store Connect returned no appStoreState")

    submission = client.request(
        "GET", f"/reviewSubmissions/{values['SUBMISSION_ID']}"
    )["data"]
    submission_state = str(submission.get("attributes", {}).get("state", "")).strip()
    if not submission_state:
        raise SystemExit("App Store Connect returned no review submission state")
    return (
        version["id"],
        app_store_state,
        attributes.get("downloadable") is True,
        submission_state,
    )


def request_release(client: AppStoreConnect, version_id: str) -> str:
    response: dict[str, Any] = client.request(
        "POST",
        "/appStoreVersionReleaseRequests",
        {
            "data": {
                "type": "appStoreVersionReleaseRequests",
                "relationships": {
                    "appStoreVersion": {
                        "data": {"type": "appStoreVersions", "id": version_id}
                    }
                },
            }
        },
    )
    request_id = str(response.get("data", {}).get("id", "")).strip()
    if not request_id:
        raise SystemExit("App Store Connect did not return a release request ID")
    return request_id


def us_storefront_listing(app_id: str) -> tuple[bool, str]:
    query = urllib.parse.urlencode({"id": app_id, "country": "us"})
    with urllib.request.urlopen(
        f"https://itunes.apple.com/lookup?{query}", timeout=30
    ) as response:
        payload: dict[str, Any] = json.load(response)
    results = payload.get("results", [])
    if len(results) != 1:
        return False, ""
    result = results[0]
    if str(result.get("bundleId", "")) != "io.tinyassets.app":
        raise SystemExit("Apple lookup returned an unexpected bundle ID")
    return True, str(result.get("trackViewUrl", "")).strip()


def main() -> None:
    values = _required_environment(os.environ)
    release_if_approved = _boolean(
        os.environ.get("RELEASE_IF_APPROVED", "false"),
        name="RELEASE_IF_APPROVED",
    )
    client = AppStoreConnect(_token(values))
    version_id, app_store_state, downloadable, submission_state = release_status(
        client, values
    )

    release_request_id = ""
    if app_store_state == "PENDING_DEVELOPER_RELEASE" and release_if_approved:
        release_request_id = request_release(client, version_id)

    listed_in_us, product_url = us_storefront_listing(values["APP_ID"])
    fields = [
        f"app={values['APP_ID']}",
        f"version={values['VERSION']}",
        f"version_id={version_id}",
        f"submission_id={values['SUBMISSION_ID']}",
        f"submission_state={submission_state}",
        f"app_store_state={app_store_state}",
        f"downloadable={str(downloadable).lower()}",
        f"listed_in_us={str(listed_in_us).lower()}",
    ]
    if release_request_id:
        fields.append(f"release_request_id={release_request_id}")
    if product_url:
        fields.append(f"product_url={product_url}")
    print("App Store release status " + " ".join(fields))


if __name__ == "__main__":
    main()
