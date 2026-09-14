"""Ensure the App Store Connect account holder can install an internal build.

Credentials stay in the protected ``app-store`` GitHub environment. Output is
deliberately limited to resource IDs and booleans; the account holder's name and
email are never printed.
"""

from __future__ import annotations

import os
import urllib.parse
from collections.abc import Mapping
from typing import Any

from app_store_review_account import AppStoreConnect, _token


def _boolean(value: str, *, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise SystemExit(f"{name} must be true/false, yes/no, or 1/0")


def _required_environment(environ: Mapping[str, str]) -> dict[str, str]:
    names = ("API_KEY_ID", "API_ISSUER_ID", "API_KEY_B64", "APP_ID")
    values = {name: environ.get(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise SystemExit(f"missing required values: {', '.join(missing)}")
    if not values["APP_ID"].isdigit():
        raise SystemExit("APP_ID must contain digits only")
    return values


def _one_resource(resources: list[dict[str, Any]], *, description: str) -> dict[str, Any]:
    if len(resources) != 1:
        raise SystemExit(f"expected one {description}, found {len(resources)}")
    return resources[0]


def account_holder(client: AppStoreConnect) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "filter[roles]": "ACCOUNT_HOLDER",
            "fields[users]": "username,firstName,lastName,roles",
            "limit": "200",
        }
    )
    holder = _one_resource(
        client.request("GET", f"/users?{query}")["data"],
        description="App Store Connect account holder",
    )
    attributes = holder.get("attributes", {})
    if "ACCOUNT_HOLDER" not in attributes.get("roles", []):
        raise SystemExit("selected App Store Connect user is not the account holder")
    username = str(attributes.get("username", "")).strip()
    if not username:
        raise SystemExit("App Store Connect returned no account-holder username")
    return holder


def internal_group(
    client: AppStoreConnect, app_id: str, *, group_name: str
) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {"fields[betaGroups]": "name,isInternalGroup", "limit": "200"}
    )
    groups = client.request("GET", f"/apps/{app_id}/betaGroups?{query}")["data"]
    matching = [
        group
        for group in groups
        if group.get("attributes", {}).get("name") == group_name
        and group.get("attributes", {}).get("isInternalGroup") is True
    ]
    return _one_resource(matching, description=f"internal beta group named {group_name!r}")


def group_testers(client: AppStoreConnect, group_id: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {"fields[betaTesters]": "email,inviteType,state", "limit": "200"}
    )
    return client.request("GET", f"/betaGroups/{group_id}/betaTesters?{query}")["data"]


def _tester_with_email(
    testers: list[dict[str, Any]], email: str
) -> dict[str, Any] | None:
    normalized = email.casefold()
    matching = [
        tester
        for tester in testers
        if str(tester.get("attributes", {}).get("email", "")).strip().casefold()
        == normalized
    ]
    if len(matching) > 1:
        raise SystemExit("App Store Connect returned duplicate testers for account holder")
    return matching[0] if matching else None


def existing_tester(client: AppStoreConnect, email: str) -> dict[str, Any] | None:
    query = urllib.parse.urlencode(
        {
            "fields[betaTesters]": "email,inviteType,state",
            "limit": "200",
        }
    )
    return _tester_with_email(client.request("GET", f"/betaTesters?{query}")["data"], email)


def add_account_holder(
    client: AppStoreConnect,
    *,
    holder: dict[str, Any],
    group: dict[str, Any],
) -> tuple[str, bool]:
    attributes = holder.get("attributes", {})
    email = str(attributes["username"]).strip()
    group_id = str(group["id"])
    tester = _tester_with_email(group_testers(client, group_id), email)
    if tester is not None:
        return str(tester["id"]), False

    tester = existing_tester(client, email)
    if tester is None:
        tester_attributes = {"email": email}
        for source, destination in (("firstName", "firstName"), ("lastName", "lastName")):
            value = str(attributes.get(source, "")).strip()
            if value:
                tester_attributes[destination] = value
        response = client.request(
            "POST",
            "/betaTesters",
            {
                "data": {
                    "type": "betaTesters",
                    "attributes": tester_attributes,
                    "relationships": {
                        "betaGroups": {
                            "data": [{"type": "betaGroups", "id": group_id}]
                        }
                    },
                }
            },
        )
        tester_id = str(response.get("data", {}).get("id", "")).strip()
        if not tester_id:
            raise SystemExit("App Store Connect did not return a beta tester ID")
    else:
        tester_id = str(tester["id"])
        client.request(
            "POST",
            f"/betaTesters/{tester_id}/relationships/betaGroups",
            {"data": [{"type": "betaGroups", "id": group_id}]},
        )

    if _tester_with_email(group_testers(client, group_id), email) is None:
        raise SystemExit("App Store Connect did not add the account holder to the group")
    return tester_id, True


def main() -> None:
    values = _required_environment(os.environ)
    apply = _boolean(os.environ.get("APPLY", "false"), name="APPLY")
    group_name = os.environ.get("GROUP_NAME", "Internal").strip()
    if not group_name:
        raise SystemExit("GROUP_NAME must not be empty")

    client = AppStoreConnect(_token(values))
    holder = account_holder(client)
    group = internal_group(client, values["APP_ID"], group_name=group_name)
    email = str(holder["attributes"]["username"]).strip()
    tester = _tester_with_email(group_testers(client, str(group["id"])), email)
    changed = False
    if apply and tester is None:
        tester_id, changed = add_account_holder(client, holder=holder, group=group)
    else:
        tester_id = "" if tester is None else str(tester["id"])

    fields = [
        f"app={values['APP_ID']}",
        f"group_id={group['id']}",
        "account_holder_count=1",
        f"already_tester={str(tester is not None).lower()}",
        f"apply={str(apply).lower()}",
        f"changed={str(changed).lower()}",
    ]
    if tester_id:
        fields.append(f"tester_id={tester_id}")
    print("App Store internal tester status " + " ".join(fields))


if __name__ == "__main__":
    main()
