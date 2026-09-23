#!/usr/bin/env python3
"""Emit the deploy-recorded expected-instance state for the cloud provenance resolver.

OpenSpec change `cloud-only-runtime-admission`, tasks 4 and 6. This state is an
input to `tinyassets.platform_runtime_provenance`; it is not itself authority.
Deployment must prepare and install it before starting an enforcing candidate.

Why a dedicated file and not a field in `release-state.json`
-----------------------------------------------------------
`deploy-prod.yml` starts and health-checks the candidate and only then publishes
the release receipt. A field added to that receipt
would therefore be absent at the exact moment the first enforcement needs it,
and the receipt is rewritten whole (`cat > release-state.json`) on every deploy,
so any rewrite that does not know about the field erases it. Publishing the
success receipt earlier to fix the ordering would be worse: it would report a
successful release before the health checks that justify it.

So the expected identity is prepared *before* the candidate starts, as its own
small typed file inside the existing data root. Receipt replacement cannot erase
it, and a rollback to a previous image on the same droplet leaves it correct
because the expected identity is a property of the machine, not of the build.

Identity source is the DigitalOcean API read from hosted CI, matched exactly
against `DO_DROPLET_HOST` — reusing `cloud_only_preflight.resolve_expected_droplet`,
which refuses a single-droplet fallback. It is never the droplet's own metadata
answer: recording what the box claims and then comparing it to the same claim
would be circular.

Exit codes
----------
0  state written
3  expected identity could not be resolved (sanitized reason on stdout).
   Deployment treats this as fatal before candidate startup. Any earlier remote
   state remains unchanged, not a substitute for successful preparation.
2  usage / write error
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cloud_only_preflight import PASS, resolve_expected_droplet  # noqa: E402

SCHEMA = "platform_expected_instance"
VERSION = 1


def build_state(instance_id: str, *, now: _dt.datetime | None = None) -> dict[str, object]:
    """Build the typed state payload.

    Deliberately minimal: the expected identity, its schema/version, and when it
    was recorded. No addresses, no token material, no build identity — the build
    receipt already owns build identity, and mixing the two is what made a field
    in the receipt unsafe.
    """
    stamp = (now or _dt.datetime.now(_dt.timezone.utc)).strftime(
        "%Y-%m-%dT%H:%M:%S.000000Z"
    )
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "expected_instance_id": str(instance_id),
        "recorded_at": stamp,
        "recorded_by": "deploy-prod",
        "enforced": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        required=True,
        help="path to write the expected-instance state JSON to",
    )
    args = parser.parse_args(argv)

    fact = resolve_expected_droplet(
        os.environ.get("DO_API_TOKEN"),
        os.environ.get("DO_DROPLET_HOST"),
    )
    if fact.get("verdict") != PASS:
        # Sanitized: the reason token only. `resolve_expected_droplet` keeps the
        # raw id in an underscore-prefixed internal field for exactly this
        # reason, and it is not printed.
        print(
            "expected_instance_state=not_prepared reason="
            f"{fact.get('reason', 'unknown')}"
        )
        return 3

    instance_id = fact.get("_instance_id")
    if not isinstance(instance_id, str) or not instance_id.isdigit():
        print("expected_instance_state=not_prepared reason=malformed_instance_id")
        return 3

    try:
        out = Path(args.out)
        out.write_text(
            json.dumps(build_state(instance_id), indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        print(f"expected_instance_state=write_failed reason={type(exc).__name__}")
        return 2

    # No identity on stdout: CI logs are readable by anyone with Actions access.
    print("expected_instance_state=prepared")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
