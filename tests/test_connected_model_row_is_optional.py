"""A connected universe has nothing waiting on the user.

Live 2026-09-25, free-only account ``u-01ky3zh1arr8qth8jee7zx63pq``: OpenRouter
sign-in completed, and the rail still showed "Connect another LLM" under
"Waiting on you". The derived entry carried ``status: "pending"`` exactly like a
real ask, so every surface reading the rail -- and the user reading the heading
-- was told an action was outstanding when none was.

The entry itself must stay: it is the only route to adding a second source. It
is the STATUS and the heading that must tell the truth.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from tests import test_model_bootstrap as _bootstrap
from tests.test_notification_is_the_setup import _RAIL_HARNESS
from tests.test_onboarding_app import _js_function
from tinyassets.onboarding import render_app_html

_NODE = shutil.which("node")
rig = _bootstrap.rig
finish = _bootstrap.finish


def _rail():
    from tinyassets.api.pending_requests import list_requests

    return list_requests(universe_id="u-owner")["pending"]


# --------------------------------------------------------------------------- #
# The server's own answer: "optional" is not "pending".
# --------------------------------------------------------------------------- #


def test_an_unpowered_universe_still_blocks_on_its_connect_request(rig):
    """The unpowered state is unchanged: this one really is waiting on you."""
    first = _rail()[0]
    assert first["request_id"] == "sys_connect_llm"
    assert first["status"] == "pending" and first["sticky"] is True


def test_a_connected_universe_reports_the_row_as_optional(rig, monkeypatch):
    monkeypatch.setattr("tinyassets.api.pending_requests._serving_llm_bound",
                        lambda *a, **k: True)
    row = _rail()[-1]
    assert row["request_id"] == "sys_connect_llm"
    assert row["title"] == "Connect another LLM" and row["sticky"] is False
    # Still offered, still answerable -- just not outstanding.
    assert row["status"] == "optional"
    assert row["action"]["type"] == "connect" and row["action"]["use"] == "model"
    assert row["resolved_at"] is None and row["answer"] is None


def test_an_optional_row_is_not_counted_as_an_outstanding_ask(rig, monkeypatch):
    from tinyassets.api.pending_requests import list_requests

    monkeypatch.setattr("tinyassets.api.pending_requests._serving_llm_bound",
                        lambda *a, **k: True)
    document = list_requests(universe_id="u-owner")
    outstanding = [row for row in document["pending"] if row["status"] == "pending"]
    assert outstanding == [], "a connected universe reported work waiting on its user"


# --------------------------------------------------------------------------- #
# The page: the heading stops asking when only optional rows remain.
# --------------------------------------------------------------------------- #


_CONNECTED = {"request_id": "sys_connect_llm", "kind": "LLM", "sticky": False,
              "status": "optional", "title": "Connect another LLM",
              "body": "Add another model source.", "fields": [],
              "action": {"type": "connect", "use": "model",
                         "setup": {"shapes": ["api_key", "local"]}}}
_ASK = {"request_id": "req_b", "kind": "API", "status": "pending", "title": "Key please",
        "fields": [], "action": {"type": "answer"}}


def _run_head(rows, extra=""):
    html, _ = render_app_html()
    source = "\n".join(_js_function(html, name) for name in (
        "isSetupRequest", "isOptionalRequest", "foldedModelAccess", "renderRail",
        "connectBody"))
    shapes = html[html.index("  const ConnectShapes={"):
                  html.index("  // A declared model list needs")]
    script = (_RAIL_HARNESS.replace("__SOURCE__", source + "\n" + shapes)
              + "\nrenderRail(" + json.dumps(rows) + ");\n" + extra + r"""
const tabs=host.children.map(t=>({text:text(t),
  optional:(t.className||'').split(' ').includes('rtab--optional'),
  hasPanel:t.children.some(c=>c.children.includes($('connect-panel')))}));
console.log(JSON.stringify({tabs,head:$('rail-head').textContent,
  railHidden:$('request-rail').hidden}));
""")
    run = subprocess.run([_NODE, "-e", script], capture_output=True, text=True,
                         encoding="utf-8", timeout=30, check=False)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


@pytest.mark.skipif(_NODE is None, reason="node is not installed")
def test_the_heading_stops_asking_when_only_optional_rows_remain():
    out = _run_head([_CONNECTED])
    assert out["head"] == "Nothing waiting on you", "a connected universe was still asked"
    assert out["railHidden"] is False, "the only route to another source disappeared"
    assert len(out["tabs"]) == 1 and out["tabs"][0]["optional"] is True
    assert out["tabs"][0]["hasPanel"] is False, "an optional row opened itself"


@pytest.mark.skipif(_NODE is None, reason="node is not installed")
def test_one_real_ask_still_makes_the_heading_ask():
    out = _run_head([_ASK, _CONNECTED])
    assert out["head"] == "Waiting on you"
    assert [tab["optional"] for tab in out["tabs"]] == [False, True]


@pytest.mark.skipif(_NODE is None, reason="node is not installed")
def test_an_older_page_payload_without_a_status_is_still_treated_as_an_ask():
    """A row with no ``status`` is a real ask; never guess it optional."""
    out = _run_head([{k: v for k, v in _ASK.items() if k != "status"}])
    assert out["head"] == "Waiting on you"
    assert out["tabs"][0]["optional"] is False


@pytest.mark.skipif(_NODE is None, reason="node is not installed")
def test_an_optional_row_still_opens_when_the_user_taps_it():
    out = _run_head([_CONNECTED], "railOpen='sys_connect_llm';renderRail(railCache);")
    assert out["tabs"][0]["hasPanel"] is True, "the optional row could not be opened"
