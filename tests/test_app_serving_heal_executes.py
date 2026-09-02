"""The app's serving heal, EXECUTED, not grepped.

Codex on #2760 (S6): source-text pins pass as long as the strings exist
somewhere, and they cannot see ordering, the POST body, fallback on a held
answer, or once-per-page. So the three functions are lifted out of the
rendered page and run under node with a recording `fetch`.
"""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

_NODE = shutil.which("node")


def _function_source(html: str, name: str) -> str:
    """The full text of `function NAME(...) { ... }`, by brace matching."""
    start = html.index(f"function {name}(")
    if html[max(0, start - 6):start] == "async ":
        start -= 6          # keep the `async` -- these are awaited
    i = html.index("{", start)
    depth = 0
    for j in range(i, len(html)):
        if html[j] == "{":
            depth += 1
        elif html[j] == "}":
            depth -= 1
            if depth == 0:
                return html[start:j + 1]
    raise AssertionError(f"unbalanced braces in {name}")


def _extract() -> str:
    from tinyassets.onboarding import render_app_html

    html, _csp = render_app_html()
    parts = [_function_source(html, n) for n in
             ("serveOn", "serviceLabel", "unservedCandidates", "healServing")]
    assert "let servingHealAttempted = false;" in html
    return "let servingHealAttempted = false;\n" + "\n".join(parts)


_HARNESS = r"""
const posts = [];
const notes = [];
let answers = [];
globalThis.fetch = async (url, opts) => {
  posts.push({url, body: JSON.parse(opts.body)});
  const next = answers.length ? answers.shift() : {status: "held", reason: "none"};
  return {json: async () => ({serving: next})};
};
globalThis.authHeaders = () => ({});
globalThis.appendMessage = (role, text) => notes.push([role, text]);
%(app)s
const status = (opts) => ({
  active_host: {llm_endpoint_bound: opts.bound},
  supervisor_liveness: {
    epoch2_operational: {consumer_pump: opts.unserved ? [{reason: "no_serving_runtime"}] : []},
    provider_auth: {writers: opts.writers},
  },
});
// `node -e` shifts argv; the scenario is always the LAST argument.
const scenario = process.argv[process.argv.length - 1];
(async () => {
  if (scenario === "bound_first_then_serving") {
    answers = [{status: "serving"}];
    await healServing(status({bound: "codex", unserved: true,
      writers: {codex: {status: "ok"}, "claude-code": {status: "ok"}}}));
    await healServing(status({bound: "codex", unserved: true,
      writers: {codex: {status: "ok"}, "claude-code": {status: "ok"}}}));
  } else if (scenario === "held_then_fallback") {
    answers = [{status: "held", reason: "provider_authority_denied"}, {status: "serving"}];
    await healServing(status({bound: "codex", unserved: true,
      writers: {codex: {status: "ok"}, "claude-code": {status: "ok"}}}));
  } else if (scenario === "nothing_unserved") {
    await healServing(status({bound: "codex", unserved: false,
      writers: {codex: {status: "ok"}}}));
  } else if (scenario === "no_writer_ok") {
    await healServing(status({bound: "codex", unserved: true,
      writers: {codex: {status: "not_logged_in"}}}));
  } else if (scenario === "claude_bound") {
    answers = [{status: "serving"}];
    await healServing(status({bound: "claude-code", unserved: true,
      writers: {codex: {status: "ok"}, "claude-code": {status: "ok"}}}));
  } else {
    throw new Error("unknown scenario: " + scenario);
  }
  console.log(JSON.stringify({scenario, posts, notes, attempted: servingHealAttempted}));
})();
"""


def _run(scenario: str) -> dict:
    script = _HARNESS % {"app": _extract()}
    proc = subprocess.run(
        [_NODE, "-e", script, "--", scenario],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    # A scenario the harness did not recognise would pass every "no POST"
    # assertion vacuously; refuse that.
    assert out["scenario"] == scenario, out
    return out


pytestmark = pytest.mark.skipif(_NODE is None, reason="node is not installed")


def test_the_bound_engine_is_tried_first_and_the_heal_runs_once_per_page():
    out = _run("bound_first_then_serving")
    assert [p["body"] for p in out["posts"]] == [{"service": "codex"}]
    assert all(p["url"] == "/mcp/app/serving/bind" for p in out["posts"])
    assert out["attempted"] is True
    [(role, text)] = out["notes"]
    assert role == "system" and "OpenAI" in text


def test_a_held_answer_falls_back_to_the_next_connected_engine():
    out = _run("held_then_fallback")
    assert [p["body"] for p in out["posts"]] == [{"service": "codex"}, {"service": "claude"}]
    assert len(out["notes"]) == 1 and "Claude" in out["notes"][0][1]


def test_a_universe_that_is_serving_is_left_alone():
    out = _run("nothing_unserved")
    assert out["posts"] == [] and out["notes"] == []
    assert out["attempted"] is False


def test_no_connected_engine_means_no_attempt():
    out = _run("no_writer_ok")
    assert out["posts"] == []
    assert out["attempted"] is False, "an attempt was spent with nothing to try"


def test_a_claude_bound_host_tries_claude_first():
    out = _run("claude_bound")
    assert [p["body"] for p in out["posts"]] == [{"service": "claude"}]
