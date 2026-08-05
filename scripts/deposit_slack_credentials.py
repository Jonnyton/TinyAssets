"""Deposit a universe's Slack credentials, verifying them before writing.

Run this yourself; it is deliberately not an agent-callable surface. The tokens
are read from the environment, never from argv:

    # PowerShell
    $env:SLACK_BOT_TOKEN = "xoxb-..."
    $env:SLACK_APP_TOKEN = "xapp-..."
    python scripts/deposit_slack_credentials.py --universe-dir <path> --connection slack-main

    # bash
    read -rs SLACK_BOT_TOKEN && export SLACK_BOT_TOKEN
    read -rs SLACK_APP_TOKEN && export SLACK_APP_TOKEN
    python scripts/deposit_slack_credentials.py --universe-dir <path> --connection slack-main

Command-line arguments are the wrong channel for a secret: argv is visible to
every process on the machine via the process list, and shells record it in
history. Environment variables are not perfect either, but they are not
world-readable and not persisted by default.

Both tokens are VERIFIED against Slack before anything is written. A vault that
contains a typo'd or already-revoked token produces the failure this project
keeps hitting: a service that starts, connects, and answers nobody, with the
real cause visible only at the moment a user happens to send a message. Better
to find out here, where a human is watching the output.

Verification also reports the bot's own user id, which the running service needs
in order to recognise its own messages and not answer itself forever.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tinyassets.credential_vault import write_credential_vault  # noqa: E402
from tinyassets.effectors.slack_socket_mode import is_app_token  # noqa: E402

AUTH_TEST_URL = "https://slack.com/api/auth.test"
CONNECTIONS_OPEN_URL = "https://slack.com/api/apps.connections.open"
BOT_TOKEN_ENV = "SLACK_BOT_TOKEN"
APP_TOKEN_ENV = "SLACK_APP_TOKEN"


def _call(url: str, token: str) -> dict:
    """POST to Slack with a bearer token. Never echoes the token."""
    request = urllib.request.Request(  # noqa: S310 - fixed https Slack endpoints
        url,
        data=b"",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Slack returned HTTP {exc.code} for {url}") from None
    except Exception:  # noqa: BLE001 - the cause may quote the Authorization header
        raise SystemExit(f"Could not reach Slack at {url}") from None


def verify_bot_token(token: str) -> tuple[str, str, str]:
    """Return (team_id, bot_user_id, team_name), or exit with the reason."""
    result = _call(AUTH_TEST_URL, token)
    if not result.get("ok"):
        raise SystemExit(
            f"Bot token rejected by Slack: {result.get('error') or 'unknown_error'}"
        )
    return (
        str(result.get("team_id") or ""),
        str(result.get("user_id") or ""),
        str(result.get("team") or ""),
    )


def verify_app_token(token: str) -> None:
    """Confirm the app-level token can actually open a socket."""
    if not is_app_token(token):
        raise SystemExit(
            "That is not an app-level token. Socket Mode needs the xapp- token "
            "from 'Basic Information -> App-Level Tokens', with the "
            "connections:write scope — not the xoxb- bot token."
        )
    result = _call(CONNECTIONS_OPEN_URL, token)
    if not result.get("ok"):
        error = str(result.get("error") or "unknown_error")
        hint = ""
        if error == "not_allowed_token_type":
            hint = " (this looks like a bot or user token, not an app-level one)"
        elif error in {"missing_scope", "no_permission"}:
            hint = " (the token needs the connections:write scope)"
        raise SystemExit(f"App-level token rejected by Slack: {error}{hint}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify and deposit Slack credentials for one universe."
    )
    parser.add_argument(
        "--universe-dir", required=True, help="the universe's directory"
    )
    parser.add_argument(
        "--connection",
        default="slack-main",
        help="connection id; one per Slack workspace (default: slack-main)",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="write without contacting Slack. Not recommended: the whole point "
        "is to fail here rather than at 3am in a socket loop.",
    )
    args = parser.parse_args()

    bot_token = os.environ.get(BOT_TOKEN_ENV, "").strip()
    app_token = os.environ.get(APP_TOKEN_ENV, "").strip()
    missing = [
        name
        for name, value in ((BOT_TOKEN_ENV, bot_token), (APP_TOKEN_ENV, app_token))
        if not value
    ]
    if missing:
        raise SystemExit(
            f"Set {' and '.join(missing)} in the environment first. "
            "Do not pass tokens as command-line arguments."
        )

    universe_dir = Path(args.universe_dir).expanduser().resolve()
    if not universe_dir.is_dir():
        raise SystemExit(f"No such universe directory: {universe_dir}")

    team_id = bot_user_id = team_name = ""
    if not args.skip_verify:
        print("Verifying the bot token with Slack...")
        team_id, bot_user_id, team_name = verify_bot_token(bot_token)
        print(f"  ok - workspace {team_name or team_id}, bot user {bot_user_id}")
        print("Verifying the app-level token can open a socket...")
        verify_app_token(app_token)
        print("  ok - Socket Mode is reachable")

    record = {
        "credential_type": "social",
        "service": "slack",
        "destination": args.connection,
        "bot_token": bot_token,
        "app_token": app_token,
    }
    summary = write_credential_vault(universe_dir, [record])

    print()
    print(f"Deposited into {universe_dir}")
    print(f"  connection : {args.connection}")
    if team_id:
        # Printed because the running service needs both, and neither is secret.
        print(f"  team_id    : {team_id}")
        print(f"  bot_user_id: {bot_user_id}")
    print(f"  vault      : {json.dumps(summary, sort_keys=True)}")
    print()
    print("Nothing above contains a token. Unset the env vars when you are done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
