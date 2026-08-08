"""In-container receiver for an X credential deposit. Secrets on STDIN only.

Runs INSIDE the daemon container (`docker exec -i tinyassets-daemon python
/app/x_deposit_receiver.py < payload.json`). Reads one JSON object from stdin:

    {"destination": "@handle", "api_key": …, "api_secret": …,
     "access_token": …, "access_token_secret": …}

and upserts it into `/data/u-tiny/.credential-vault.json` as the single
social/twitter record for that destination. Prints a summary that NEVER
contains a secret value. Argv carries nothing sensitive — argv is
world-readable; stdin is not.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "/app")

from tinyassets.credential_vault import (  # noqa: E402
    load_credential_vault,
    resolve_twitter_credentials,
    write_credential_vault,
)

UNIVERSE_DIR = "/data/u-tiny"
FIELDS = ("api_key", "api_secret", "access_token", "access_token_secret")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        print("FAIL: stdin was not valid JSON")
        return 1
    destination = str(payload.get("destination") or "").strip()
    if not destination.startswith("@"):
        print("FAIL: destination must be the @handle form")
        return 1
    values = {key: str(payload.get(key) or "").strip() for key in FIELDS}
    missing = [key for key, value in values.items() if not value]
    if missing:
        print(f"FAIL: missing fields: {missing}")
        return 1

    record = {
        "credential_type": "social",
        "service": "twitter",
        "destination": destination,
        **values,
    }
    # Replace-not-duplicate: write_credential_vault treats a MULTI-record
    # payload as a full replace, so build the complete new list explicitly
    # (the one-record upsert path keys on (type, service) and would collapse
    # per-destination records — the Slack deposit hit exactly this).
    kept = [
        r for r in load_credential_vault(UNIVERSE_DIR)
        if not (
            r.get("credential_type") == "social"
            and str(r.get("service") or r.get("provider") or "").strip().lower()
            in ("twitter", "x")
            and str(r.get("destination") or "").strip() == destination
        )
    ]
    write_credential_vault(UNIVERSE_DIR, [*kept, record])
    resolved = resolve_twitter_credentials(UNIVERSE_DIR, destination)
    if resolved is None:
        print("FAIL: wrote the record but could not resolve it back — "
              "the vault and resolver disagree; nothing will post")
        return 1
    print(f"OK: deposited X credentials for {destination} "
          f"({len(kept) + 1} records in vault); resolver round-trip passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
