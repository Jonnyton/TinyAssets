"""Run one universe's Slack agent.

    python scripts/run_slack_agent.py --universe-dir <path> [--connection slack-main]

Everything it needs beyond those two arguments is derived, not configured. The
workspace id and the bot's own user id both come from `auth.test` at startup,
using the credential already in the vault — so there is nothing to copy between
the deposit step and this one, and therefore nothing to copy wrongly. Getting
`bot_user_id` wrong in particular is not a visible error: the agent simply stops
recognising its own messages and answers itself in a loop.

Ctrl-C stops it. The socket is an outbound WebSocket, so this works behind a
firewall with no public endpoint and no inbound port.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tinyassets.credential_vault import resolve_slack_token  # noqa: E402
from tinyassets.effectors.slack_agent_service import (  # noqa: E402
    SlackAgentConfig,
    SlackAgentConfigError,
    run_slack_agent,
)

AUTH_TEST_URL = "https://slack.com/api/auth.test"

logger = logging.getLogger("slack-agent")


def identify(bot_token: str) -> tuple[str, str, str]:
    """Ask Slack who we are: (team_id, bot_user_id, team_name)."""
    request = urllib.request.Request(  # noqa: S310 - fixed https Slack endpoint
        AUTH_TEST_URL,
        data=b"",
        method="POST",
        headers={
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Slack returned HTTP {exc.code} for auth.test") from None
    except Exception:  # noqa: BLE001 - the cause may quote the Authorization header
        raise SystemExit("Could not reach Slack to identify this app") from None
    if not result.get("ok"):
        raise SystemExit(
            f"Slack rejected the bot token: {result.get('error') or 'unknown_error'}"
        )
    return (
        str(result.get("team_id") or ""),
        str(result.get("user_id") or ""),
        str(result.get("team") or ""),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one universe's Slack agent.")
    parser.add_argument("--universe-dir", required=True)
    parser.add_argument("--universe-id", default="")
    parser.add_argument("--connection", default="slack-main")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    universe_dir = Path(args.universe_dir).expanduser().resolve()
    if not universe_dir.is_dir():
        raise SystemExit(f"No such universe directory: {universe_dir}")
    universe_id = args.universe_id.strip() or universe_dir.name

    bot_token = resolve_slack_token(universe_dir, args.connection)
    if not bot_token:
        raise SystemExit(
            f"No Slack bot token for connection {args.connection!r} in {universe_dir}.\n"
            "Deposit it first:\n"
            "  python scripts/deposit_slack_credentials.py "
            f"--universe-dir {universe_dir} --connection {args.connection}"
        )

    team_id, bot_user_id, team_name = identify(bot_token)
    logger.info(
        "identified as bot %s in workspace %s (%s)",
        bot_user_id,
        team_name or team_id,
        team_id,
    )

    try:
        config = SlackAgentConfig(
            universe_id=universe_id,
            universe_dir=universe_dir,
            connection_id=args.connection,
            team_id=team_id,
            bot_user_id=bot_user_id,
        )
    except SlackAgentConfigError as exc:
        raise SystemExit(str(exc)) from None

    print(f"Listening as {bot_user_id} for universe {universe_id}. Ctrl-C to stop.")
    try:
        handled = asyncio.run(run_slack_agent(config))
    except SlackAgentConfigError as exc:
        # Fail loudly and specifically: this is the "up but answering nobody"
        # class, and the whole point is that it is visible at startup.
        raise SystemExit(f"Cannot start: {exc}") from None
    except KeyboardInterrupt:  # pragma: no cover - interactive
        print("\nStopped.")
        return 0
    print(f"Socket closed after handling {handled} event(s).")
    return 0


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        raise SystemExit(main())
