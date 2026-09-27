"""A deploy waits for the founder's turn instead of killing it 10 seconds in.

The concern (`docs/concerns/2026-08-29-a-deploy-kills-in-flight-turns-silently.md`)
proposed a drain ENDPOINT the deploy would ask. It is not needed, and finding
that out is what this change rests on:

* `restart_stack` is `docker compose up -d`, so a recreate STOPS the old daemon
  first and waits up to the service's ``stop_grace_period``;
* uvicorn's graceful shutdown already stops accepting connections and waits on
  in-flight work;
* `deploy/compose.yml` declared no ``stop_grace_period``, so the effective bound
  was docker's 10-second default.

The daemon was already willing to drain. The only thing killing the turn was a
bound nobody had chosen.

WHAT THE GRACE ACTUALLY BUYS, since the first version of this file claimed more.
A served ``converse`` is NOT saved end to end: sse-starlette cancels the SSE
response the moment uvicorn begins shutting down -- measured at 0.49s against a
5s grace, while the turn itself finished at 1.99s
(``docs/audits/2026-09-26-pr4039-drain-repro.py``, Codex on #4039, reproduced
independently). What the grace buys is the turn COMPLETING: its effects land and
``record_exchange`` stores the answer, so the founder reads it in the thread
rather than losing the work. Saving the reply itself is a transport-level problem
and not this change.

So the fix is three numbers in three files, and what needs testing is the
RELATIONSHIP between them -- each one alone looks fine while the set is broken:

    universe_server.GRACEFUL_SHUTDOWN_S  <  compose daemon.stop_grace_period
                                         >=  deploy_fail_safe MIN_DAEMON_STOP_GRACE_S

and the whole worst case has to fit inside the deploy job, which the first version
of this file got WRONG: it divided the job budget by two and passed, missing that
a failing deploy drains a SECOND time on the rollback converge and waits for
health both times. At 300s that was 960s against a 900s job -- a slow deploy
CANCELLED part-way instead of rolled back, worse than the bug being fixed.
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
DEPLOY_JOB_BUDGET_S = 15 * 60
#: How many times one run can converge, and therefore drain: the forward converge,
#: plus the rollback converge when the new image does not become acceptable.
#: Missing this is what made the first version's budget check wrong.
CONVERGES_PER_RUN = 2
#: Everything else the job must still afford after the drains and health waits:
#: image pull, bundle claim/validate/snapshot/install, env write, canary.
DEPLOY_OVERHEAD_S = 120


def _workflow_job_timeout_s() -> int:
    text = (REPO / ".github" / "workflows" / "deploy-prod.yml").read_text(encoding="utf-8")
    match = re.search(r"^    timeout-minutes:\s*(\d+)$", text, re.M)
    assert match, "the deploy job's timeout-minutes moved; re-point this"
    return int(match.group(1)) * 60


def _health_timeout_s() -> int:
    """The health wait that follows EVERY converge, from the workflow env."""
    text = (REPO / ".github" / "workflows" / "deploy-prod.yml").read_text(encoding="utf-8")
    match = re.search(r"HEALTH_TIMEOUT:?=?\s*[\"']?(\d+)", text)
    assert match, "HEALTH_TIMEOUT is no longer set in deploy-prod.yml"
    return int(match.group(1))


def _systemd_start_timeout_s() -> int:
    text = (REPO / "deploy" / "tinyassets-daemon.service").read_text(encoding="utf-8")
    match = re.search(r"^TimeoutStartSec=(\d+)s?$", text, re.M)
    assert match, "TimeoutStartSec is no longer a plain seconds value"
    return int(match.group(1))


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


def test_the_servers_own_bound_expires_before_dockers():
    """Uvicorn cancels first, so the two bounds do not race.

    Not a clean-exit guarantee, which is what the first version of this docstring
    claimed. Codex refuted it: the timeout bounds uvicorn's wait on connections
    and tracked request tasks, and expiry cancels those -- it does not stop an
    AnyIO worker thread or bound lifespan shutdown, and a 0.25s value still let a
    worker run to 1.98s. Docker's SIGKILL is the real bound. What the ordering
    buys is that the ordinary case reaches uvicorn's own cancellation inside the
    window instead of being cut off mid-write by docker.
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


def test_the_worst_case_deploy_still_fits_inside_the_job():
    """Both drains AND both health waits, not the grace on its own.

    A run that fails converges TWICE -- forward, then the rollback -- and waits
    HEALTH_TIMEOUT after each. The first version of this test compared the grace
    against half the budget and passed at 300s, where the real worst case was
    2*300 + 2*180 = 960 against a 900s job. Exceeding the job does not make a slow
    deploy; it CANCELS one part-way through a bundle install, which is worse than
    the bug this change fixes (Codex on #4039, P1).
    """
    grace = _compose_grace_s()
    budget = _workflow_job_timeout_s()
    assert budget == DEPLOY_JOB_BUDGET_S, "the job budget changed; re-derive the bound"
    worst_case = CONVERGES_PER_RUN * (grace + _health_timeout_s()) + DEPLOY_OVERHEAD_S
    assert worst_case <= budget, (
        f"worst case {worst_case}s ({CONVERGES_PER_RUN} x ({grace}s drain + "
        f"{_health_timeout_s()}s health) + {DEPLOY_OVERHEAD_S}s overhead) exceeds the "
        f"{budget}s job; a slow deploy is cancelled mid-install rather than rolled back")


def test_the_grace_stays_inside_the_units_own_start_deadline():
    """`apply-daemon-env-remote.sh` drives a recreate THROUGH the systemd unit.

    A grace longer than the unit's TimeoutStartSec means that path can be killed
    by its controller while docker was still willing to wait (Codex on #4039).
    """
    grace = _compose_grace_s()
    start_timeout = _systemd_start_timeout_s()
    assert grace < start_timeout, (
        f"a {grace}s drain outlives tinyassets-daemon.service's {start_timeout}s "
        "TimeoutStartSec, so a unit-driven recreate is cut off by systemd")


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


def test_the_measurement_behind_the_narrowed_claim_is_retained():
    """The reply-is-not-saved finding is evidence, and evidence rots when deleted.

    Every comment in this change says the grace preserves the TURN and not the
    reply. That is a measurement, not a reading of the code, so the script that
    produces it and the concern entry that dates it both have to stay -- otherwise
    the next person re-derives the stronger, false claim from the code alone,
    which is exactly what the first version of this PR did.
    """
    repro = REPO / "docs" / "audits" / "2026-09-26-pr4039-drain-repro.py"
    assert repro.is_file(), "the shutdown reproduction is the basis of the narrowed claim"
    concern = (REPO / "docs" / "concerns"
               / "2026-08-29-a-deploy-kills-in-flight-turns-silently.md").read_text(
        encoding="utf-8")
    assert "sse-starlette" in concern, (
        "the concern must record WHY a longer grace does not save the reply")


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
