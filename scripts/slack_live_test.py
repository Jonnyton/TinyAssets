"""One command: verify, deposit, connect, and prove a real Slack round trip.

    $env:SLACK_BOT_TOKEN = "xoxb-..."
    $env:SLACK_APP_TOKEN = "xapp-..."
    python scripts/slack_live_test.py --universe-id <id>

Then send one message in Slack. That is the whole test.

This exists because everything up to that message is automatable and the message
itself is not. The tokens are yours to generate and yours to put in the
environment; posting as a human in your own workspace is yours to do. Everything
between — verification, same-app checking, deposit, connection, the agent turn,
and the reply — happens here, and the result is reported as a plain PASS/FAIL
rather than something to interpret from logs.

It waits for exactly one answered message, prints what actually happened at each
step, and exits non-zero if any of it failed. `--timeout` bounds the wait so it
cannot hang a terminal indefinitely.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tinyassets.effectors.slack_agent_service import (  # noqa: E402
    SlackAgentConfig,
    SlackAgentConfigError,
    build_resolver,
)
from tinyassets.effectors.slack_agent_turn import build_handlers  # noqa: E402
from tinyassets.effectors.slack_socket_mode import app_id_from_token  # noqa: E402
from tinyassets.effectors.slack_socket_runner import run_socket_forever  # noqa: E402
from tinyassets.effectors.slack_transport import build_slack_transport  # noqa: E402

from tinyassets.credential_vault import (  # noqa: E402
    resolve_slack_app_token,
    resolve_slack_token,
)

BOT_TOKEN_ENV = "SLACK_BOT_TOKEN"
APP_TOKEN_ENV = "SLACK_APP_TOKEN"


def _load_windows_user_env(name: str) -> None:
    """Fall back to the Windows *User* environment for `name`.

    `setx` and `[Environment]::SetEnvironmentVariable(..., 'User')` write to the
    registry, and only processes started AFTERWARDS inherit them. A shell that
    was already open — which is the normal case when someone sets the variable
    and then runs this in an existing terminal — sees nothing, and the script
    said "set the env vars" to someone who just had. Read the registry directly
    so the obvious sequence works.

    Reads only; never writes, and never prints the value.
    """
    if os.environ.get(name, "").strip() or sys.platform != "win32":
        return
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
    except (ImportError, OSError):
        return
    if isinstance(value, str) and value.strip():
        os.environ[name] = value.strip()


def _step(n: int, text: str) -> None:
    print(f"[{n}/6] {text}", flush=True)


def _fail(text: str) -> None:
    print(f"\nFAIL — {text}", flush=True)
    raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="End-to-end live Slack test for one universe."
    )
    parser.add_argument("--universe-id", required=True)
    parser.add_argument("--connection", default="slack-main")
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="seconds to wait for your message (default 300)",
    )
    parser.add_argument(
        "--skip-deposit",
        action="store_true",
        help="credentials are already in the vault; do not read the env vars",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="      %(message)s")

    # The env vars are checked BEFORE anything slow or side-effecting, so a
    # missing one fails in a second rather than after a network round trip.
    if not args.skip_deposit:
        _load_windows_user_env(BOT_TOKEN_ENV)
        _load_windows_user_env(APP_TOKEN_ENV)
        if not (
            os.environ.get(BOT_TOKEN_ENV, "").strip()
            and os.environ.get(APP_TOKEN_ENV, "").strip()
        ):
            _fail(
                f"set {BOT_TOKEN_ENV} and {APP_TOKEN_ENV} in the environment "
                "(not as arguments — argv is world-readable), or pass "
                "--skip-deposit if they are already deposited"
            )

    _step(1, "Resolving the universe...")

    try:
        probe = SlackAgentConfig(
            universe_id=args.universe_id.strip(),
            connection_id=args.connection,
            team_id="pending",
            bot_user_id="pending",
        )
        universe_dir = probe.universe_dir
    except SlackAgentConfigError as exc:
        _fail(str(exc))
    if not universe_dir.is_dir():
        _fail(
            f"universe {args.universe_id!r} resolves to {universe_dir}, "
            "which does not exist"
        )
    print(f"      {universe_dir}")

    if not args.skip_deposit:
        import subprocess

        _step(2, "Verifying both tokens with Slack and depositing...")
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent / "deposit_slack_credentials.py"),
                "--universe-dir",
                str(universe_dir),
                "--connection",
                args.connection,
            ],
            text=True,
            env=os.environ.copy(),
        )
        if result.returncode != 0:
            _fail("credential verification failed — see the message above")
    else:
        _step(2, "Using credentials already in the vault.")

    # --- 3. identity --------------------------------------------------------
    _step(3, "Asking Slack who this app is...")
    from run_slack_agent import identify  # noqa: E402  - sibling script

    bot_token = resolve_slack_token(universe_dir, args.connection)
    if not bot_token:
        _fail("no bot token in the vault after deposit")
    team_id, bot_user_id, team_name = identify(bot_token)
    api_app_id = app_id_from_token(
        resolve_slack_app_token(universe_dir, args.connection)
    )
    print(f"      workspace {team_name or team_id} ({team_id})")
    print(f"      bot user  {bot_user_id}")
    print(f"      app       {api_app_id or '(not derivable — cross-app filter OFF)'}")

    config = SlackAgentConfig(
        universe_id=args.universe_id.strip(),
        connection_id=args.connection,
        team_id=team_id,
        bot_user_id=bot_user_id,
        api_app_id=api_app_id,
    )

    # --- 4/5/6. connect, wait for one message, report -----------------------
    _step(4, "Opening the socket (outbound — no public endpoint)...")
    answered: list[dict] = []
    failures: list[str] = []
    post = build_slack_transport(universe_dir)
    resolve = build_resolver(config)

    def _traced_post(destination, body, *, thread_ts=""):
        where = thread_ts or "(new)"
        print(f"      -> replying in {destination.address} thread {where}")
        return post(destination, body, thread_ts=thread_ts)

    handle, on_failure = build_handlers(resolve=resolve, post=_traced_post)

    async def _watch(event):
        text = str(event.get("text") or "")
        print(f"\n      <- {event.get('user')} said: {text[:120]}", flush=True)
        await handle(event)
        answered.append(dict(event))

    async def _watch_failure(event, exc):
        failures.append(type(exc).__name__)
        print(f"      !! turn failed: {type(exc).__name__}", flush=True)
        await on_failure(event, exc)

    async def _run():
        _step(
            5,
            "Connected. Now MENTION the app in Slack — "
            f"e.g. `@{team_name or 'your app'} hello`",
        )
        print(f"      (waiting up to {args.timeout:.0f}s; Ctrl-C to stop)\n", flush=True)
        started = time.monotonic()

        async def _until_answered():
            while not answered and time.monotonic() - started < args.timeout:
                await asyncio.sleep(0.5)

        socket_task = asyncio.create_task(
            run_socket_forever(
                resolve_slack_app_token(universe_dir, args.connection),
                bot_user_id=bot_user_id,
                handle=_watch,
                on_failure=_watch_failure,
            )
        )
        waiter = asyncio.create_task(_until_answered())
        done, _ = await asyncio.wait(
            {socket_task, waiter}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in (socket_task, waiter):
            if not task.done():
                task.cancel()
        for task in done:
            if task is socket_task and task.exception():
                raise task.exception()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:  # pragma: no cover - interactive
        print("\nStopped before a message arrived.")
        return 1
    except Exception as exc:  # noqa: BLE001
        _fail(f"the socket failed: {type(exc).__name__}: {exc}")

    _step(6, "Result")
    if not answered:
        _fail(
            "no message arrived within the timeout. Check the app is IN the "
            "channel, that Socket Mode is enabled, and that the app subscribes "
            "to app_mention (and message.im for DMs)."
        )
    if failures:
        _fail(f"a message arrived but the turn failed: {', '.join(failures)}")
    print("\nPASS — the agent received a real Slack message and answered it.")
    print("       Check the thread in Slack to read the reply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
