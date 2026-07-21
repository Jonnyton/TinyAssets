"""Real container smoke for root-preload/drop-privileges vault custody."""

from __future__ import annotations

import os

from tinyassets.credential_broker import deposit_credential, resolve_credential
from tinyassets.credentials import SecretKind


def main() -> None:
    if os.geteuid() != 1001:
        raise RuntimeError("vault smoke did not run as the tinyassets user")
    projection = deposit_credential(
        universe_id="container-smoke",
        founder_id="container-smoke-founder",
        provider="smoke",
        destination="local",
        purpose="container_test",
        kind=SecretKind.API_KEY,
        value=b"container-smoke-secret",
    )
    with resolve_credential("container-smoke", "smoke", "container_test", "local") as lease:
        if lease.reveal() != b"container-smoke-secret":
            raise RuntimeError("vault container round-trip mismatch")
    if not str(projection.get("ref", "")).startswith("secret:v1:"):
        raise RuntimeError("vault container deposit returned no opaque ref")
    print("VAULT-CONTAINER-SMOKE: ok uid=1001")


if __name__ == "__main__":
    main()
