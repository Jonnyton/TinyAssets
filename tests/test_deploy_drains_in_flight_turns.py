"""A deploy waits for the founder's turn instead of killing it 10 seconds in.

The concern (`docs/concerns/2026-08-29-a-deploy-kills-in-flight-turns-silently.md`)
proposed a drain ENDPOINT the deploy would ask. It is not needed, and finding
that out is what this change rests on:

* `restart_stack` is `docker compose up -d`, so a recreate STOPS the old daemon
  first and waits up to the service's ``stop_grace_period``;
* uvicorn's graceful shutdown already stops accepting connections and waits for
  in-flight requests, and a served ``converse`` IS an in-flight HTTP request;
* `deploy/compose.yml` declared no ``stop_grace_period``, so the effective bound
  was docker's 10-second default.

The daemon was already willing to drain. The only thing killing the turn was a
bound nobody had chosen. So the fix is three numbers in three files, and what
needs testing is the RELATIONSHIP between them -- each one alone looks fine while
the set is broken:

    universe_server.GRACEFUL_SHUTDOWN_S  <  compose daemon.stop_grace_period
                                         >=  deploy_fail_safe MIN_DAEMON_STOP_GRACE_S

Get the first wrong and the server is SIGKILLed mid-write instead of closing its
own connections. Get the second wrong and the deploy gate stops enforcing the
bound it was added to enforce.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
COMPOSE = REPO / "deploy" / "compose.yml"
SCRIPT = REPO / "deploy" / "deploy_fail_safe.sh"
SERVER = REPO / "tinyassets" / "universe_server.py"

#: What the deploy job allows in total, from `.github/workflows/deploy-prod.yml`.
#: The grace has to fit inside it alongside build, validation, snapshot and
#: health checks, which is why a bound covering the 3600s a granted turn may run
#: is not available: it would make every merge wait on one user's turn.
DEPLOY_JOB_BUDGET_S = 15 * 60


def _compose_grace_s() -> float:
    daemon = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["daemon"]
    raw = daemon.get("stop_grace_period")
    assert raw is not None, (
        "the daemon must declare stop_grace_period; absent means docker's 10s default, "
        "which is what killed the founder's in-flight turns")
    match = re.fullmatch(r"(\d+)(s|m)?", str(raw).strip())
    assert match, f"stop_grace_period {raw!r} is not a plain seconds/minutes duration"
    return int(match.group(1)) * (60 if match.group(2) == "m" else 1)


def _script_floor_s() -> int:
    match = re.search(r"^MIN_DAEMON_STOP_GRACE_S=(\d+)$", SCRIPT.read_text(encoding="utf-8"), re.M)
    assert match, "MIN_DAEMON_STOP_GRACE_S is no longer a plain integer assignment"
    return int(match.group(1))


def test_the_server_finishes_before_docker_kills_it():
    """The ordering that makes the drain a clean shutdown rather than a SIGKILL.

    Equal is not good enough: the server must have time to close its own
    connections and exit INSIDE the window, so a strict inequality is the
    property, not a formatting preference.
    """
    from tinyassets.universe_server import GRACEFUL_SHUTDOWN_S

    grace = _compose_grace_s()
    assert GRACEFUL_SHUTDOWN_S < grace, (
        f"the server waits {GRACEFUL_SHUTDOWN_S}s but docker SIGKILLs at {grace}s, so "
        "an in-flight turn dies mid-write instead of being closed cleanly")
    assert grace - GRACEFUL_SHUTDOWN_S >= 5, (
        "leave the server a real margin to close connections and exit, not a rounding error")


def test_the_deploy_gate_enforces_exactly_the_bound_that_shipped():
    """The floor the validator asserts IS the value in the file it validates.

    A floor below the shipped value would let a later bundle quietly lower the
    grace; a floor above it would refuse the bundle that is live right now.
    """
    assert _script_floor_s() == _compose_grace_s()


def test_the_bound_fits_inside_the_deploy_job():
    """A grace the deploy job cannot afford is a grace that gets cut off anyway."""
    grace = _compose_grace_s()
    assert 0 < grace <= DEPLOY_JOB_BUDGET_S / 2, (
        f"a {grace}s drain leaves too little of the {DEPLOY_JOB_BUDGET_S}s job for build, "
        "validation, snapshot and health checks")


def test_the_served_launch_chooses_its_shutdown_bound():
    """Passed explicitly at the launch, not left to uvicorn's default.

    Uvicorn's default is to wait INDEFINITELY, which reads generous and is
    worthless: docker's SIGKILL arrives first, so the real bound was 10 seconds
    and nothing in the code said so. An AST check because the claim IS about the
    call site's arguments.
    """
    calls = [
        node for node in ast.walk(ast.parse(SERVER.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "uvicorn"
    ]
    assert calls, "the ASGI launch moved; re-point this assertion at it"
    for call in calls:
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        assert "timeout_graceful_shutdown" in keywords, (
            "uvicorn's default waits forever and docker SIGKILLs first; choose the bound")
        value = keywords["timeout_graceful_shutdown"]
        assert isinstance(value, ast.Name) and value.id == "GRACEFUL_SHUTDOWN_S", (
            "pass the module constant, so the tests above constrain what actually runs")


def test_uvicorn_accepts_the_keyword_we_are_passing():
    """The kwarg is real, in the installed version. A silent typo here would mean
    the server keeps uvicorn's wait-forever default while every check above
    passes -- the whole failure mode this change exists to remove.
    """
    import inspect

    import uvicorn

    assert "timeout_graceful_shutdown" in inspect.signature(uvicorn.Config).parameters


def test_the_converge_is_timed_so_the_bound_can_be_measured():
    """300s is a judgement, and it is only revisable with data.

    `restart_stack` logs how long the converge took, and says so when it reaches
    the grace bound -- which is the observable that says whether turns are still
    being cut off.
    """
    body = SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"^restart_stack\(\) \{\n(.*?)^\}", body, re.S | re.M)
    assert match, "restart_stack is no longer a plain shell function"
    function = match.group(1)
    assert 'started="$SECONDS"' in function
    assert "SECONDS - started" in function
    assert "converge took" in function
    assert "MIN_DAEMON_STOP_GRACE_S" in function, (
        "reaching the bound is the signal that a turn was cut off; say so in the log")


def test_the_concern_this_does_not_close_is_still_open():
    """A 300s bound does not save a turn that runs for an hour.

    The concern's own resolution condition is a turn that survives a deploy OR is
    left a truthful notice, observed live. This change plus the startup
    reconciliation make the second half true; neither makes the first half true
    for a long turn, so the file stays until someone sees it on the live surface.
    """
    concern = REPO / "docs" / "concerns" / (
        "2026-08-29-a-deploy-kills-in-flight-turns-silently.md")
    assert concern.is_file(), (
        "if this was deleted, it needs the live observation its own 'How to resolve' "
        "section demands -- not a green test suite")


@pytest.mark.parametrize("name", ["daemon"])
def test_only_the_daemon_carries_the_grace(name: str):
    """The sidecars are stateless; a grace on them only slows every deploy down."""
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    carriers = {
        service for service, body in services.items()
        if isinstance(body, dict) and body.get("stop_grace_period") is not None
    }
    assert carriers == {name}, f"{sorted(carriers)} declare a grace; only {name} should"
