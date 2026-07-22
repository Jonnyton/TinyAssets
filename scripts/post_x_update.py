"""Post a composed patch announcement to X.

Dry-run is the default. Set SOCIAL_POST_DRY_RUN=false and provide either:

- X_USER_ACCESS_TOKEN for OAuth 2.0 user-context bearer posting, or
- X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET for OAuth 1.0a.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
from pathlib import Path

CREATE_POST_URL = "https://api.x.com/2/tweets"


def is_false(value: str) -> bool:
    return value.strip().lower() in {"0", "false", "no", "off"}


def pct(value: str) -> str:
    return urllib.parse.quote(value, safe="~-._")


def oauth1_header(method: str, url: str, credentials: dict[str, str]) -> str:
    params = {
        "oauth_consumer_key": credentials["api_key"],
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": credentials["access_token"],
        "oauth_version": "1.0",
    }
    query_params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    signature_params = {**query_params, **params}
    normalized = "&".join(f"{pct(k)}={pct(v)}" for k, v in sorted(signature_params.items()))
    base_url = urllib.parse.urlunsplit((*urllib.parse.urlsplit(url)[:3], "", ""))
    base = "&".join([method.upper(), pct(base_url), pct(normalized)])
    key = f"{pct(credentials['api_secret'])}&{pct(credentials['access_token_secret'])}"
    digest = hmac.new(key.encode("utf-8"), base.encode("utf-8"), hashlib.sha1).digest()
    params["oauth_signature"] = base64.b64encode(digest).decode("ascii")
    return "OAuth " + ", ".join(f'{pct(k)}="{pct(v)}"' for k, v in sorted(params.items()))


def load_payload(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    text = payload.get("post_text") or payload.get("text")
    if payload.get("skip_reason") and not text:
        return payload
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{path} does not contain post_text")
    return payload


def post_to_x(text: str) -> dict:
    body = json.dumps({"text": text}).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    bearer = os.environ.get("X_USER_ACCESS_TOKEN", "").strip()
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    else:
        credentials = {
            "api_key": os.environ.get("X_API_KEY", "").strip(),
            "api_secret": os.environ.get("X_API_SECRET", "").strip(),
            "access_token": os.environ.get("X_ACCESS_TOKEN", "").strip(),
            "access_token_secret": os.environ.get("X_ACCESS_TOKEN_SECRET", "").strip(),
        }
        if not all(credentials.values()):
            raise RuntimeError(
                "Missing X credentials. Provide X_USER_ACCESS_TOKEN or OAuth 1.0a "
                "X_API_KEY/X_API_SECRET/X_ACCESS_TOKEN/X_ACCESS_TOKEN_SECRET."
            )
        headers["Authorization"] = oauth1_header("POST", CREATE_POST_URL, credentials)

    request = urllib.request.Request(CREATE_POST_URL, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--dry-run",
        choices=["true", "false"],
        default=os.environ.get("SOCIAL_POST_DRY_RUN", "true"),
    )
    args = parser.parse_args()

    payload = load_payload(args.input)
    text = (payload.get("post_text") or payload.get("text") or "").strip()
    if not text and payload.get("skip_reason"):
        result = {
            "dry_run": True,
            "skipped": True,
            "skip_reason": payload["skip_reason"],
        }
        print(f"Skipping X post: {payload['skip_reason']}")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return 0

    dry_run = not is_false(args.dry_run)

    if dry_run:
        result = {"dry_run": True, "post_text": text}
        print(text)
    else:
        result = {"dry_run": False, "response": post_to_x(text), "post_text": text}
        print(json.dumps(result["response"], indent=2, sort_keys=True))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
