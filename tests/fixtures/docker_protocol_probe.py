"""CI-only client for the isolated image's configured local auth issuer.

Retain every public-canary assertion; change only its deliberately pinned
production AuthKit expectation to this fixture's local authorization server.
Never installed in the image or used by the production deploy workflow.
"""

import importlib.util
from pathlib import Path

URL = "http://localhost:8001/mcp"


def run(canary) -> int:
    original = canary.EXPECTED_AUTHORIZATION_SERVERS
    try:
        canary.EXPECTED_AUTHORIZATION_SERVERS = (URL,)
        return canary.main([
            "--url", URL, "--timeout", "15", "--assert-handles", "--verbose",
        ])
    finally:
        canary.EXPECTED_AUTHORIZATION_SERVERS = original


if __name__ == "__main__":
    spec = importlib.util.spec_from_file_location(
        "image_fixture_canary",
        Path(__file__).resolve().parents[2] / "scripts/mcp_public_canary.py",
    )
    canary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(canary)
    raise SystemExit(run(canary))
