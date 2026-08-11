"""Long-running Slack agent, as a deployed service.

    python -m tinyassets.slack_agent_worker

This exists because `scripts/slack_live_test.py` — useful as it is for proving
the thing works — runs on whoever's laptop is open. The Forever Rule is that
every surface works 24/7 with **zero hosts online**, so the socket has to be
held by a container on the droplet, next to `cloud_worker`, not by a terminal
someone might close.

Configuration comes from the environment, matching how `cloud_worker` is
deployed:

    TINYASSETS_SLACK_UNIVERSES   comma-separated universe ids to serve
    TINYASSETS_SLACK_CONNECTION  connection id (default: slack-main)

Credentials are NOT read from the environment. Each universe's Slack tokens
come from its own vault, so one container can serve several universes without
any of them borrowing another's identity — and a universe with no deposit is
skipped loudly rather than silently falling back.

One socket per universe, each in its own task. A universe whose socket dies
permanently (revoked token) is reported and dropped; the others keep running,
because one user's revoked credential must not take down everybody else's
agent.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from collections.abc import Callable

from tinyassets.effectors.slack_agent_service import (
    SlackAgentConfig,
    SlackAgentConfigError,
    run_slack_agent,
)
from tinyassets.effectors.slack_socket_mode import app_id_from_token
from tinyassets.effectors.slack_socket_runner import SocketModePermanentError

logger = logging.getLogger("tinyassets.slack_agent_worker")

UNIVERSES_ENV = "TINYASSETS_SLACK_UNIVERSES"
CONNECTION_ENV = "TINYASSETS_SLACK_CONNECTION"
DEFAULT_CONNECTION = "slack-main"

AUTH_TEST_URL = "https://slack.com/api/auth.test"


def configured_universes() -> list[str]:
    raw = os.environ.get(UNIVERSES_ENV, "")
    return [part.strip() for part in raw.split(",") if part.strip()]


def dynamic_serving_universes() -> list[str]:
    """Discover server-authorized serving bindings from the canonical store."""

    from tinyassets.provider_serving_binding import list_serving_universes
    from tinyassets.storage import data_dir

    return list_serving_universes(data_dir())


def _identify(bot_token: str) -> tuple[str, str]:
    """Ask Slack for (team_id, bot_user_id). Raises on refusal."""
    import json
    import urllib.error
    import urllib.request

    request = urllib.request.Request(  # noqa: S310 - fixed https Slack endpoint
        AUTH_TEST_URL,
        data=b"",
        method="POST",
        headers={
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    failure = ""
    result = None
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        failure = f"auth.test http {exc.code}"
    except Exception:  # noqa: BLE001 - the cause may quote the Authorization header
        failure = "could not reach slack for auth.test"
    if failure:
        raise SlackAgentConfigError(failure)
    if not result.get("ok"):
        from tinyassets.effectors.slack_errors import safe_error_code

        code = safe_error_code(result.get("error"), default="unknown_error")
        raise SlackAgentConfigError(f"slack rejected the bot token: {code}")
    return str(result.get("team_id") or ""), str(result.get("user_id") or "")


def build_config(universe_id: str, connection: str) -> SlackAgentConfig:
    """Resolve one universe's Slack identity entirely from its own vault."""
    from tinyassets.credential_vault import (
        resolve_slack_app_token,
        resolve_slack_token,
    )

    probe = SlackAgentConfig(
        universe_id=universe_id,
        connection_id=connection,
        team_id="pending",
        bot_user_id="pending",
    )
    udir = probe.universe_dir
    bot_token = resolve_slack_token(udir, connection)
    if not bot_token:
        raise SlackAgentConfigError(
            f"no Slack bot token deposited for connection {connection!r}"
        )
    team_id, bot_user_id = _identify(bot_token)
    return SlackAgentConfig(
        universe_id=universe_id,
        connection_id=connection,
        team_id=team_id,
        bot_user_id=bot_user_id,
        api_app_id=app_id_from_token(resolve_slack_app_token(udir, connection)),
    )


async def serve_universe(universe_id: str, connection: str) -> None:
    """Hold one universe's socket until permanent failure or cancellation."""
    try:
        config = build_config(universe_id, connection)
    except SlackAgentConfigError as exc:
        # Loud and specific, then this universe is skipped. Not fatal to the
        # process: one user's missing deposit must not silence everyone else.
        logger.error("slack agent: %s not started — %s", universe_id, exc)
        return
    logger.info(
        "slack agent: serving %s as %s in workspace %s",
        universe_id,
        config.bot_user_id,
        config.team_id,
    )
    try:
        handled = await run_slack_agent(config)
        logger.warning(
            "slack agent: %s socket ended after %d event(s)", universe_id, handled
        )
    except SocketModePermanentError as exc:
        logger.error("slack agent: %s stopped permanently — %s", universe_id, exc)
    except asyncio.CancelledError:
        logger.info("slack agent: %s shutting down", universe_id)
        raise


async def _report_unexpected(universe_id: str, coro) -> None:
    """Run one universe task and LOG anything it raises unexpectedly.

    `asyncio.gather(return_exceptions=True)` is what stops one universe from
    cancelling the others — but it also swallows whatever they raise. A
    PermissionError reading a vault surfaced as a clean `exit 0` with nothing
    in the log, twice, during the first real deployment. Fault isolation must
    not mean fault silence.
    """
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - isolate the universe, report the cause
        logger.exception("slack agent: %s failed unexpectedly", universe_id)


async def serve_all(universe_ids: list[str], connection: str) -> int:
    tasks = [
        asyncio.create_task(
            _report_unexpected(uid, serve_universe(uid, connection)),
            name=f"slack:{uid}",
        )
        for uid in universe_ids
    ]
    if not tasks:
        return 1
    stopping = asyncio.Event()

    def _stop(*_args: object) -> None:
        logger.info("slack agent: signal received — shutting down")
        stopping.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _stop)
        except (NotImplementedError, AttributeError):
            # Windows proactor loops do not support add_signal_handler.
            signal.signal(sig, _stop)

    # Gather the universe tasks into ONE awaitable and race that against the
    # stop signal. Racing the individual tasks with FIRST_COMPLETED — which is
    # what this did — meant the FIRST universe to finish for any reason (a
    # missing deposit returns immediately) cancelled every other universe. That
    # is the exact opposite of the isolation this module's docstring promises,
    # and a cross-family review caught it before it shipped: one tenant with a
    # revoked token could drop every other tenant's agent.
    running = asyncio.gather(*tasks, return_exceptions=True)
    waiter = asyncio.create_task(stopping.wait(), name="slack:stop")
    await asyncio.wait([running, waiter], return_when=asyncio.FIRST_COMPLETED)
    if not waiter.done():
        waiter.cancel()
    if not running.done():
        running.cancel()
    await asyncio.gather(running, waiter, return_exceptions=True)
    return 0


async def serve_reconciling(
    universe_ids: list[str],
    connection: str,
    *,
    enrollment_source: Callable[[], list[str]] = dynamic_serving_universes,
    poll_interval_s: float = 5.0,
    stopping: asyncio.Event | None = None,
    install_signal_handlers: bool = True,
) -> int:
    """Continuously reconcile sockets with static + server serving intent."""

    static = set(universe_ids)
    stop = stopping or asyncio.Event()
    tasks: dict[str, asyncio.Task[None]] = {}
    retired: list[asyncio.Task[None]] = []
    enrolled: set[str] = set()

    def _stop(*_args: object) -> None:
        logger.info("slack agent: signal received — shutting down")
        stop.set()

    if install_signal_handlers:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, _stop)
            except (NotImplementedError, AttributeError):
                signal.signal(sig, _stop)

    try:
        while not stop.is_set():
            try:
                dynamic = set(enrollment_source())
            except Exception:  # noqa: BLE001 - keep current sockets, report drift
                logger.exception("slack agent: serving enrollment refresh failed")
                dynamic = enrolled - static
            desired = static | dynamic
            for uid in sorted(enrolled - desired):
                task = tasks.pop(uid, None)
                if task is not None and not task.done():
                    task.cancel()
                if task is not None:
                    retired.append(task)
                enrolled.remove(uid)
                logger.info("slack agent: withdrew dynamic enrollment for %s", uid)
            for uid in sorted(desired - enrolled):
                tasks[uid] = asyncio.create_task(
                    _report_unexpected(uid, serve_universe(uid, connection)),
                    name=f"slack:{uid}",
                )
                enrolled.add(uid)
                logger.info("slack agent: enrolled %s", uid)
            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_interval_s)
            except TimeoutError:
                pass
    finally:
        for task in tasks.values():
            if not task.done():
                task.cancel()
        pending = [*retired, *tasks.values()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Slack Socket Mode agents for the configured universes."
    )
    parser.add_argument(
        "--universe",
        action="append",
        default=[],
        help=f"universe id to serve (repeatable); defaults to ${UNIVERSES_ENV}",
    )
    parser.add_argument(
        "--connection",
        default=os.environ.get(CONNECTION_ENV, DEFAULT_CONNECTION),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    universe_ids = args.universe or configured_universes()
    dynamic = dynamic_serving_universes()
    if not universe_ids and not dynamic:
        logger.error(
            "no universes configured — set %s (comma-separated) or pass --universe",
            UNIVERSES_ENV,
        )
        return 1

    logger.info(
        "slack agent worker starting for %d universe(s) on connection %s",
        len(universe_ids),
        args.connection,
    )
    return asyncio.run(serve_reconciling(universe_ids, args.connection))


if __name__ == "__main__":
    raise SystemExit(main())
