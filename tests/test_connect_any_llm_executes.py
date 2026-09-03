"""The endpoint deposit path, EXECUTED, not grepped.

Codex on the connect-any-LLM lane: every test in `test_connect_any_llm.py` is a
source-text pin, so deleting the endpoint click branch outright leaves all of
them green (verified: 7/7 still passed with the branch removed). Static pins
cannot see call ORDER, the arguments actually sent, or which returns clear the
key -- which is the whole contract here.

So `depositEndpoint` is lifted out of the rendered page and run under node with
a recording `MCP`, the same technique `test_app_serving_heal_executes.py` uses.
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
        start -= 6          # keep the `async` -- this is awaited
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
    return "\n".join(
        _function_source(html, name)
        for name in ("depositEndpoint", "connectEndpointFlow")
    )


_HARNESS = r"""
const calls = [];
// The DOM the function reads. `value` is what a user typed; clearing it is the
// behaviour under test, so we watch the live object rather than a copy.
const fields = {
  "endpoint-name":     {value: ""},
  "endpoint-url":      {value: ""},
  "endpoint-protocol": {value: "openai_chat"},
  "endpoint-model":    {value: ""},
  "endpoint-key":      {value: ""},
};
globalThis.$ = (id) => fields[id];
const out = {textContent: ""};

globalThis.MCP = {
  async connectHTTP(destination, secret, allowedEndpoints, authScheme) {
    calls.push({call: "connectHTTP", destination, secret, allowedEndpoints, authScheme,
                keyInDom: fields["endpoint-key"].value});
    return connectHTTPAnswer;
  },
  async connectCompute(descriptor) {
    calls.push({call: "connectCompute", descriptor,
                keyInDom: fields["endpoint-key"].value});
    return connectComputeAnswer;
  },
};
let connectHTTPAnswer = {grant_id: "grant_1"};
let connectComputeAnswer = {definition_id: "def_1"};
let serveAnswer = {status: "serving"};

// The rest of the page `connectEndpointFlow` touches.
let engineConnected = 0;
globalThis.serveOn = async (service) => {
  calls.push({call: "serveOn", service});
  return serveAnswer;
};
globalThis.servingSentence = (label, sv) =>
  label + " -> " + (sv && sv.status ? sv.status : "none");
globalThis.onEngineConnected = () => { engineConnected += 1; };
globalThis.enterSignedOut = () => { calls.push({call: "enterSignedOut"}); };
const btn = {disabled: false};

%(app)s

const scenario = process.argv[process.argv.length - 1];
(async () => {
  let ref;
  if (scenario === "happy") {
    fields["endpoint-name"].value = "my gateway";
    fields["endpoint-url"].value = "https://gateway.example/custom/chat";
    fields["endpoint-model"].value = "some-model";
    fields["endpoint-key"].value = "SECRET-KEY";
    ref = await depositEndpoint(out);
  } else if (scenario === "not_https") {
    fields["endpoint-name"].value = "my gateway";
    fields["endpoint-url"].value = "http://gateway.example/v1/chat/completions";
    fields["endpoint-model"].value = "some-model";
    fields["endpoint-key"].value = "SECRET-KEY";
    ref = await depositEndpoint(out);
  } else if (scenario === "bad_url") {
    fields["endpoint-name"].value = "my gateway";
    fields["endpoint-url"].value = "not a url at all";
    fields["endpoint-model"].value = "some-model";
    fields["endpoint-key"].value = "SECRET-KEY";
    ref = await depositEndpoint(out);
  } else if (scenario === "missing_model") {
    fields["endpoint-name"].value = "my gateway";
    fields["endpoint-url"].value = "https://gateway.example/v1/chat/completions";
    fields["endpoint-model"].value = "";
    fields["endpoint-key"].value = "SECRET-KEY";
    ref = await depositEndpoint(out);
  } else if (scenario === "deposit_refused") {
    connectHTTPAnswer = {error: "nope"};
    fields["endpoint-name"].value = "my gateway";
    fields["endpoint-url"].value = "https://gateway.example/v1/chat/completions";
    fields["endpoint-model"].value = "some-model";
    fields["endpoint-key"].value = "SECRET-KEY";
    ref = await depositEndpoint(out);
  } else if (scenario === "flow_serving" || scenario === "flow_held") {
    if (scenario === "flow_held") serveAnswer = {status: "held", reason: "unknown_provider"};
    fields["endpoint-name"].value = "my gateway";
    fields["endpoint-url"].value = "https://gateway.example/v1/chat/completions";
    fields["endpoint-model"].value = "some-model";
    fields["endpoint-key"].value = "SECRET-KEY";
    await connectEndpointFlow(out, btn);
  } else if (scenario === "flow_refused") {
    fields["endpoint-url"].value = "http://gateway.example/v1/chat/completions";
    fields["endpoint-name"].value = "my gateway";
    fields["endpoint-model"].value = "some-model";
    fields["endpoint-key"].value = "SECRET-KEY";
    await connectEndpointFlow(out, btn);
  } else {
    console.log(JSON.stringify({scenario: "UNKNOWN"}));
    return;
  }
  console.log(JSON.stringify({
    scenario, calls, ref: ref === undefined ? null : ref,
    text: out.textContent, keyInDom: fields["endpoint-key"].value,
    engineConnected, btnDisabled: btn.disabled,
  }));
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
    # An unrecognised scenario would satisfy every "no call was made" assertion
    # vacuously; refuse that.
    assert out["scenario"] == scenario, out
    return out


pytestmark = pytest.mark.skipif(_NODE is None, reason="node is not installed")


def test_the_deposit_chains_connectHTTP_then_connectCompute_in_that_order():
    out = _run("happy")
    assert [c["call"] for c in out["calls"]] == ["connectHTTP", "connectCompute"], (
        "the endpoint path no longer chains the two agnostic calls"
    )
    assert out["ref"] == "def_1", "the compute definition is not returned for serving"


def test_the_user_s_own_endpoint_path_is_what_gets_granted():
    """The grant must permit the path the runtime will actually call.

    A grant on `/custom/chat` paired with a call to `/v1/chat/completions` is
    refused by the broker -- registerable, never servable.
    """
    out = _run("happy")
    http = out["calls"][0]
    assert http["allowedEndpoints"] == [
        {"host": "gateway.example", "path_template": "/custom/chat", "methods": ["POST"]}
    ], http["allowedEndpoints"]


def test_the_declared_model_and_protocol_reach_connect_compute():
    out = _run("happy")
    compute = out["calls"][1]["descriptor"]
    assert compute["access_method"] == "api_key_http"
    assert compute["protocol"] == "openai_chat"
    assert compute["model"] == "some-model"
    assert compute["ref"] == "grant_1", "the compute is not built on the deposit's grant"


def test_the_secret_is_out_of_the_dom_before_the_first_call():
    out = _run("happy")
    assert out["calls"][0]["keyInDom"] == "", (
        "the key was still in the DOM when the first await happened"
    )
    assert out["keyInDom"] == ""
    # It must still have been SENT -- clearing early must not clear the payload.
    assert out["calls"][0]["secret"] == "SECRET-KEY"


@pytest.mark.parametrize("scenario", ["not_https", "bad_url", "missing_model"])
def test_a_refused_deposit_still_clears_the_key_and_calls_nothing(scenario):
    """The validation returns are exactly where the key used to be left behind."""
    out = _run(scenario)
    assert out["calls"] == [], "a refused deposit still reached the network"
    assert out["ref"] is None
    assert out["keyInDom"] == "", (
        f"{scenario}: the key was left in the DOM on a validation refusal"
    )


def test_a_refused_deposit_does_not_register_compute():
    out = _run("deposit_refused")
    assert [c["call"] for c in out["calls"]] == ["connectHTTP"], (
        "compute was registered on a grant that was never issued"
    )
    assert out["ref"] is None


# --- the whole gesture, not just the deposit ---------------------------------
# Codex's actual finding: deleting the branch that CHAINS these left every
# source-text pin green. These drive the chain itself.

def test_the_gesture_chains_deposit_register_then_serve_in_that_order():
    out = _run("flow_serving")
    assert [c["call"] for c in out["calls"]] == [
        "connectHTTP", "connectCompute", "serveOn",
    ], "the connect gesture no longer runs deposit -> register -> serve"
    assert out["calls"][2]["service"] == "def_1", (
        "the universe was pointed at something other than the registered compute"
    )


def test_a_serving_answer_marks_the_engine_connected():
    out = _run("flow_serving")
    assert out["engineConnected"] == 1
    assert out["btnDisabled"] is False, "the button was left disabled"


def test_a_held_answer_does_not_claim_the_universe_is_running():
    out = _run("flow_held")
    assert out["engineConnected"] == 0, (
        "a held bind still reported the universe as connected"
    )
    assert "held" in out["text"]


def test_a_refused_deposit_never_reaches_serving():
    out = _run("flow_refused")
    assert out["calls"] == [], "a refused deposit still tried to point the universe"
    assert out["engineConnected"] == 0
    assert out["btnDisabled"] is False
