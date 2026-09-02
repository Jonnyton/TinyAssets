"""A serving universe is never told it has no serving provider.

App thread, 2026-09-02. The founder's universe had a ready provider
assignment and a serving binding (chat and runs worked), and `get_status`
kept saying:

    consumer_pump: no_serving_runtime -- "This universe has no serving
    provider selected ... Choose one (registering a provider is not
    selecting it)."

Tiny planned around it ("cloud automation is not fully ready ... I do not
have the surface that flips the universe onto one"), and the app's heal
re-fired on every page load because it keys on that reason. The reason was
wrong: the consumer records `no_serving_runtime` whenever the fleet-era
executor selects no daemon, which since the fleet retirement is every
universe, serving or not.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from tinyassets.consumer_reason_actions import consumer_next_action
from tinyassets.runtime.assigned_queue_consumer import AssignedQueueConsumer


def _consumer(tmp_path):
    """Only `base_path` is read by `_no_runtime_reason`; no executor needed."""
    return SimpleNamespace(
        base_path=tmp_path,
        _no_runtime_reason=lambda universe_id: AssignedQueueConsumer._no_runtime_reason(
            SimpleNamespace(base_path=tmp_path), universe_id,
        ),
    )


def test_a_universe_with_a_READY_assignment_is_not_told_to_choose_one(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "tinyassets.provider_assignment.load_provider_assignment",
        lambda base, universe_id: SimpleNamespace(
            state="ready", provider="codex", owner_user_id="alice",
        ),
    )
    assert _consumer(tmp_path)._no_runtime_reason("u-1") == "background_executor_unavailable"


@pytest.mark.parametrize("assignment", [
    None,
    SimpleNamespace(state="pending", provider="codex", owner_user_id="alice"),
])
def test_a_universe_without_a_ready_assignment_still_hears_no_serving_runtime(
    tmp_path, monkeypatch, assignment,
):
    monkeypatch.setattr(
        "tinyassets.provider_assignment.load_provider_assignment",
        lambda base, universe_id: assignment,
    )
    assert _consumer(tmp_path)._no_runtime_reason("u-1") == "no_serving_runtime"


def test_the_new_reason_says_the_universe_IS_serving_and_names_the_retired_executor():
    action = consumer_next_action("background_executor_unavailable")
    lowered = action.lower()
    assert "is serving" in lowered
    assert "retired" in lowered
    assert "no serving provider selected" not in lowered
    assert "choose one" not in lowered


# The wiring is pinned by tests/test_automations.py
# ::test_a_poll_beats_for_a_serving_universe_with_no_runtime_at_all, which
# drives the real poll against a universe with a READY assignment and now
# expects `background_executor_unavailable`.


# ------------------------------------------------ the app heal keys on the truth


_NODE = shutil.which("node")


@pytest.mark.skipif(_NODE is None, reason="node is not installed")
def test_the_app_heal_does_not_fire_on_the_new_reason():
    """The heal must keep firing for `no_serving_runtime` and stay quiet for a
    universe that is serving but has no background executor."""
    from tinyassets.onboarding import render_app_html

    html, _csp = render_app_html()

    def fn(name: str) -> str:
        start = html.index(f"function {name}(")
        if html[max(0, start - 6):start] == "async ":
            start -= 6
        i = html.index("{", start)
        depth = 0
        for j in range(i, len(html)):
            if html[j] == "{":
                depth += 1
            elif html[j] == "}":
                depth -= 1
                if depth == 0:
                    return html[start:j + 1]
        raise AssertionError(name)

    script = "\n".join([
        "const posts = [];",
        "globalThis.fetch = async (url, opts) => { posts.push(JSON.parse(opts.body));"
        " return {json: async () => ({serving: {status: 'serving'}})}; };",
        "globalThis.authHeaders = () => ({});",
        "globalThis.appendMessage = () => {};",
        "let servingHealAttempted = false;",
        fn("serveOn"), fn("serviceLabel"), fn("unservedCandidates"), fn("healServing"),
        "const status = (reason) => ({active_host: {llm_endpoint_bound: 'codex'},"
        " supervisor_liveness: {epoch2_operational: {consumer_pump: [{reason}]},"
        " provider_auth: {writers: {codex: {status: 'ok'}}}}});",
        "(async () => {",
        "  await healServing(status(process.argv[process.argv.length - 1]));",
        "  console.log(JSON.stringify({posts, attempted: servingHealAttempted}));",
        "})();",
    ])
    quiet = json.loads(subprocess.run(
        [_NODE, "-e", script, "--", "background_executor_unavailable"],
        capture_output=True, text=True, timeout=30, check=True,
    ).stdout.strip().splitlines()[-1])
    loud = json.loads(subprocess.run(
        [_NODE, "-e", script, "--", "no_serving_runtime"],
        capture_output=True, text=True, timeout=30, check=True,
    ).stdout.strip().splitlines()[-1])
    assert quiet == {"posts": [], "attempted": False}, quiet
    assert loud["posts"] == [{"service": "codex"}], loud
