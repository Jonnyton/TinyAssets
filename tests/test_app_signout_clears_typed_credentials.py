"""A credential typed into setup and never submitted dies with the login.

Found by the cross-family review of `notification-is-the-setup` on 2026-09-26
(P0), against code that was already live. Every setup panel cleared its OWN field
on SUBMIT, and the hosted panel's `reset()` cleared its own input on sign-out — so
a key pasted into "Other ways to connect" and never submitted stayed in the DOM.
On the signed-out page, `document.getElementById("endpoint-key").value` still
returned it, readable by whoever used that browser next.

`enterSignedOut` is lifted out of the rendered page and run for real under node.
The field set is PARSED FROM THE PAGE, not hand-listed: the fix is a rule over
`input[type="password"]`, so the test has to ask the page which fields exist or it
would only ever prove the one field the reviewer happened to name.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

_NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(_NODE is None, reason="node is required to run the page's own code")

# `clearCredentialFields` is OPTIONAL on purpose: against a tree without the fix
# the test must fail on its ASSERTIONS (the credential survived), not on a lift
# error that looks like a broken test.
_LIFT = ("enterSignedOut",)
_OPTIONAL = ("clearCredentialFields",)


def _app_html() -> str:
    from tinyassets.onboarding import render_app_html

    html, _csp = render_app_html()
    return html


def _function_source(html: str, name: str, required: bool = True):
    try:
        start = html.index("function " + name + "(")
    except ValueError:
        if required:
            raise AssertionError(name + " not found in the rendered app")
        return None
    if html[max(0, start - 6):start] == "async ":
        start -= 6
    i = html.index("{", html.index(")", start))
    depth = 0
    for j in range(i, len(html)):
        if html[j] == "{":
            depth += 1
        elif html[j] == "}":
            depth -= 1
            if depth == 0:
                return html[start:j + 1]
    raise AssertionError("unbalanced braces in " + name)


def _password_field_ids(html: str) -> list[str]:
    """Every credential-bearing input the PAGE declares, in page order.

    Asked of the page rather than written down here, because the fix is a rule and
    a hand-list would silently stop covering a field added later — which is the
    exact failure mode that produced the defect.
    """
    ids = re.findall(r'<input\s+id="([^"]+)"\s+type="password"', html)
    assert len(ids) >= 2, f"expected several credential fields, found {ids}"
    return ids


def _run_node(script: str):
    with tempfile.TemporaryDirectory(prefix="ta-signout-") as box:
        path = os.path.join(box, "harness.cjs")
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(script)
        run = subprocess.run([_NODE, path], capture_output=True, text=True,
                             encoding="utf-8", timeout=120, check=False)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


_HARNESS = r"""
'use strict';
// The page's own module-scope state, declared as the page declares it.
let statusTimer=null, workingTimer=null, modelChoiceForNextTurn="a-model";
const TOKEN_KEY="ta_token", EXP_KEY="ta_exp";
const STORE={session:{}};
const sessionStorage={ removeItem(k){ delete STORE.session[k]; },
  setItem(k,v){ STORE.session[k]=String(v); }, getItem(k){ return STORE.session[k]||null; } };

// The fields the PAGE declares, each a distinct object so clearing one cannot
// read as clearing another.
const FIELDS={};
for(const id of FIELD_IDS) FIELDS[id]={id, type:"password", value:""};
function $(id){ return FIELDS[id]||{id, value:"", textContent:"", style:{}}; }
// Only the selector the fix uses resolves. Anything else returns nothing, so a
// fix that swept the whole DOM by some other route would not pass here by luck.
const document={ querySelectorAll(selector){
  return selector==='input[type="password"]' ? Object.values(FIELDS) : [];
} };

const VIEWS=[];
function clearInterval(){}
function showView(v){ VIEWS.push(v); }
function clearAccountScopedState(){}
const Uploads={ abort(){} };
const Voice={ stop(){} };
const ModelPicker={ reset(){} };
// Deliberately does NOT clear anything: the page's hosted reset used to be the
// only thing clearing a credential on sign-out, and relying on it is the defect.
const HostedModelConnect={ reset(){} };
const AppLayout={ reset(){} };
const MCP={ _loginEpoch:0, endLogin(){ this._loginEpoch++; } };
"""


def _script(html: str, *, typed: dict) -> str:
    ids = _password_field_ids(html)
    lifted = [_function_source(html, name) for name in _LIFT]
    for name in _OPTIONAL:
        src = _function_source(html, name, required=False)
        if src:
            lifted.append(src)
    return "\n".join([
        "const FIELD_IDS=%s;" % json.dumps(ids),
        _HARNESS,
        "\n".join(lifted),
        # The owner pastes, then signs out without submitting.
        "".join('FIELDS[%s].value=%s;\n' % (json.dumps(k), json.dumps(v))
                for k, v in typed.items()),
        "enterSignedOut();",
        "console.log(JSON.stringify({"
        " remaining: Object.keys(FIELDS).filter(id=>FIELDS[id].value!==''),"
        " views: VIEWS,"
        " ids: FIELD_IDS }));",
    ])


def test_an_unsubmitted_key_does_not_survive_sign_out():
    """The reviewer's exact reproduction: paste into the endpoint key, sign out
    without submitting, and read the field back on the signed-out page."""
    html = _app_html()
    out = _run_node(_script(html, typed={"endpoint-key": "sk-not-submitted"}))

    assert "endpoint-key" in out["ids"], "the page no longer has that field"
    assert out["remaining"] == [], (
        "a credential typed into setup survived sign-out in: %s" % out["remaining"]
    )
    # The sign-out really happened, so the emptiness is not just an inert harness.
    assert out["views"] == ["signin"]


def test_every_credential_field_the_page_has_is_cleared():
    """The rule, not the one field the review named.

    Each `type="password"` input the page declares is filled with a distinct
    sentinel, so a fix that cleared only the field it was written for leaves the
    others behind and this test names them.
    """
    html = _app_html()
    ids = _password_field_ids(html)
    typed = {field_id: "secret-%d" % index for index, field_id in enumerate(ids)}
    out = _run_node(_script(html, typed=typed))

    assert out["remaining"] == [], (
        "these credential fields survived sign-out: %s" % out["remaining"]
    )
    assert len(out["ids"]) == len(ids) >= 6, out["ids"]
