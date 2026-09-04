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

from tinyassets.effectors.slack_errors import safe_error_code  # noqa: E402
from tinyassets.effectors.slack_socket_mode import (  # noqa: E402
    app_id_from_token,
    is_app_token,
)

from tinyassets.credential_vault import (  # noqa: E402
    load_credential_vault,
    write_credential_vault,
)

AUTH_TEST_URL = "https://slack.com/api/auth.test"
CONNECTIONS_OPEN_URL = "https://slack.com/api/apps.connections.open"
BOTS_INFO_URL = "https://slack.com/api/bots.info"
BOT_TOKEN_PREFIX = "xoxb-"
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
    # Every failure is raised AFTER the handler exits. `from None` clears
    # __cause__ but leaves __context__ holding the URLError, whose message
    # quotes the Authorization header — a review read the token out of it.
    result = None
    failure = ""
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        failure = f"Slack returned HTTP {exc.code} for {url}"
    except Exception:  # noqa: BLE001
        failure = f"Could not reach Slack at {url}"
    if failure:
        raise SystemExit(failure)
    return result


def verify_bot_token(token: str) -> tuple[str, str, str, str]:
    """Return (team_id, bot_user_id, team_name, bot_id), or exit with the reason."""
    if not token.startswith(BOT_TOKEN_PREFIX):
        # `auth.test` succeeds for a USER token too, so a green setup could
        # deposit a credential that posts under a person's name. The service
        # refuses it later; refusing it here is where someone is watching.
        raise SystemExit(
            "That is not a bot token. A user (xoxp-) token would post replies "
            "under your own name, not the app's."
        )
    result = _call(AUTH_TEST_URL, token)
    if not result.get("ok"):
        # Slack's `error` is upstream text and has been seen echoing the
        # credential back; allow-list it to a real code.
        code = safe_error_code(result.get("error"), default="unknown_error")
        raise SystemExit(f"Bot token rejected by Slack: {code}")
    return (
        str(result.get("team_id") or ""),
        str(result.get("user_id") or ""),
        str(result.get("team") or ""),
        str(result.get("bot_id") or ""),
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
        error = safe_error_code(result.get("error"), default="unknown_error")
        hint = ""
        if error == "not_allowed_token_type":
            hint = " (this looks like a bot or user token, not an app-level one)"
        elif error in {"missing_scope", "no_permission"}:
            hint = " (the token needs the connections:write scope)"
        raise SystemExit(f"App-level token rejected by Slack: {error}{hint}")


def verify_same_app(bot_token: str, app_token: str, bot_id: str) -> None:
    """Refuse a bot token and app token that belong to DIFFERENT Slack apps.

    This is the check that makes the runtime `api_app_id` filter mean anything.
    The filter compares an incoming event against the app id derived from the
    APP token — but a socket only ever carries that app's events, so on its own
    the comparison is tautological. The actual hazard is a vault pairing App A's
    BOT token with App B's app token: App B's events arrive, pass the filter,
    and get answered as App A.

    `bots.info` needs the `users:read` scope. If it is missing we WARN rather
    than block: refusing to deposit over an optional scope would push people to
    `--skip-verify`, which is worse. The residual is stated out loud instead.
    """
    expected = app_id_from_token(app_token)
    if not expected:
        print("  note - app id not derivable from the app token; skipping same-app check")
        return
    if not bot_id:
        print("  note - Slack reported no bot_id; skipping same-app check")
        return
    result = _call(f"{BOTS_INFO_URL}?bot={bot_id}", bot_token)
    if not result.get("ok"):
        code = safe_error_code(result.get("error"), default="unknown_error")
        print(
            f"  WARNING - could not confirm both tokens belong to one app ({code}). "
            "Check they came from the SAME Slack app page."
        )
        return
    actual = str((result.get("bot") or {}).get("app_id") or "").strip()
    if actual and actual != expected:
        raise SystemExit(
            "These two tokens belong to DIFFERENT Slack apps: the bot token is "
            f"for {actual} and the app-level token is for {expected}. The agent "
            "would receive one app's messages and answer as the other. Take "
            "both from the same app's settings page."
        )
    print(f"  ok - both tokens belong to app {expected}")


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

    # Token TYPE is checked unconditionally. `--skip-verify` skips the network
    # round trip, not the local sanity checks — a review pointed out it was
    # skipping both, so a deposit could "succeed" with a credential the service
    # refuses at startup, or worse, one that posts under a person's name.
    if not bot_token.startswith(BOT_TOKEN_PREFIX):
        raise SystemExit(
            "That is not a bot token. A user (xoxp-) token would post replies "
            "under your own name, not the app's."
        )
    if not is_app_token(app_token):
        raise SystemExit(
            "That is not an app-level token. Socket Mode needs the xapp- token "
            "from 'Basic Information -> App-Level Tokens', with the "
            "connections:write scope — not the xoxb- bot token."
        )

    team_id = bot_user_id = team_name = bot_id = ""
    if not args.skip_verify:
        print("Verifying the bot token with Slack...")
        team_id, bot_user_id, team_name, bot_id = verify_bot_token(bot_token)
        print(f"  ok - workspace {team_name or team_id}, bot user {bot_user_id}")
        print("Verifying the app-level token can open a socket...")
        verify_app_token(app_token)
        print("  ok - Socket Mode is reachable")
        print("Confirming both tokens belong to the same Slack app...")
        verify_same_app(bot_token, app_token, bot_id)

    # Normalised ONCE, then used for both the comparison and the record. A
    # review deposited " conn-b " and got a duplicate: the merge compared the
    # untrimmed CLI value while the vault stored the trimmed one, so the stale
    # record survived and kept being resolved first.
    connection = args.connection.strip()
    if not connection:
        raise SystemExit("--connection cannot be blank")

    record = {
        "credential_type": "social",
        "service": "slack",
        "destination": connection,
        "bot_token": bot_token,
        "app_token": app_token,
    }
    # UPSERT, not replace. write_credential_vault treats a single record as an
    # upsert keyed on (credential_type, service) — which for Slack ignores the
    # connection, so depositing a second workspace silently deleted the first.
    # A review reproduced that data loss. Merge by destination ourselves.
    existing = [
        r
        for r in load_credential_vault(universe_dir)
        if not (
            r.get("credential_type") == "social"
            # `provider` is an accepted alias for `service` in vault
            # resolution, so matching only `service` left an aliased record
            # behind as a duplicate — and it resolved FIRST, so a rotation
            # silently kept posting with the superseded token.
            and str(r.get("service") or r.get("provider") or "").strip().lower()
            == "slack"
            and str(r.get("destination") or "").strip() == connection
        )
    ]
    summary = write_credential_vault(universe_dir, [*existing, record])

    print()
    print(f"Deposited into {universe_dir}")
    print(f"  connection : {connection}")
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
