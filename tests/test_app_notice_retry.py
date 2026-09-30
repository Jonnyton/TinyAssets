"""A saved failure's "Send it again" goes out through the composer's own path.

Driven through the page's real `loadHistory` / `appendFailureNotice` /
`sendTurn` / `queueTurn` under node (the shim in test_app_live_turn_recovery).
Two silent paths are pinned here: a retry queued behind a live turn wiped the
draft the founder was typing, and a retry folded into an identical queued line
showed nothing at all.
"""
from __future__ import annotations

import json
import time

import pytest

from tests.test_app_live_turn_recovery import _NODE, _run, html  # noqa: F401

pytestmark = pytest.mark.skipif(
    _NODE is None, reason="node is required to execute the page's own source")

FAILURE = {"version": 1, "kind": "turn_failed", "code": "unknown"}


def _history(original: str) -> str:
    stamp = time.time() - 60
    rows = [
        {"speaker": "founder", "text": original, "truncated": False, "ts": stamp},
        {"speaker": "platform", "text": "The turn did not complete.", "ts": stamp,
         "failure": FAILURE},
    ]
    return "SCENARIO.history=%s;\n" % json.dumps(rows)


_CLICK = r"""
const again=()=>els.thread.children.filter(n=>!n.removed).flatMap(n=>n.children)
  .find(c=>c.tagName==="BUTTON"&&c.textContent==="Send it again");
"""


def test_retry_after_reload_sends_the_original_exactly_once(tmp_path, html):  # noqa: F811
    out = _run(tmp_path, html, _history("build me a tracker") + _CLICK + r"""
    setQueueOwner("p-1");
    await loadHistory(); await settle();
    const before=snapshot();
    again().click(); await settle();
    const clicked=snapshot(); const disabled=again().disabled;
    again().click(); await settle();              // a second click is not a second turn
    gates[0].resolve({reply:"Here it is."}); await settle();
    console.log(JSON.stringify({before, clicked, disabled, done:snapshot()}));
    """)
    assert out["before"]["converseCalls"] == []
    assert out["clicked"]["converseCalls"] == ["build me a tracker"]
    assert out["disabled"] is True
    assert out["done"]["converseCalls"] == ["build me a tracker"]
    assert out["done"]["messages"][-1] == {"role": "universe", "text": "Here it is."}


def test_retry_while_a_turn_is_in_flight_is_queued_and_keeps_the_draft(tmp_path, html):  # noqa: F811
    out = _run(tmp_path, html, _history("build me a tracker") + _CLICK + r"""
    setQueueOwner("p-1");
    await loadHistory(); await settle();
    const live=sendTurn("something else"); await settle();
    els["composer-input"].value="half-typed next thought";
    again().click(); await settle();
    const queued=snapshot();
    const draft=els["composer-input"].value, waiting=sendQueue.length;
    gates[0].resolve({reply:"ok"}); await live; await settle();
    const flushed=snapshot();
    gates[1].resolve({reply:"tracker"}); await settle();
    console.log(JSON.stringify({queued, draft, waiting, flushed, done:snapshot()}));
    """)
    assert out["queued"]["converseCalls"] == ["something else"]
    assert out["waiting"] == 1, "the retry was dropped instead of queued"
    assert out["queued"]["status"].endswith("1 waiting")
    assert out["draft"] == "half-typed next thought", "a queued retry wiped the draft"
    assert out["flushed"]["converseCalls"] == ["something else", "build me a tracker"]
    assert out["done"]["messages"][-1] == {"role": "universe", "text": "tracker"}


def test_retry_matching_a_queued_line_says_so_instead_of_vanishing(tmp_path, html):  # noqa: F811
    out = _run(tmp_path, html, _history("build me a tracker") + _CLICK + r"""
    setQueueOwner("p-1");
    await loadHistory(); await settle();
    const live=sendTurn("something else"); await settle();
    sendTurn("build me a tracker"); await settle();     // typed again while busy
    again().click(); await settle();
    const status=els["status-line"].textContent, waiting=sendQueue.length;
    gates[0].resolve({reply:"ok"}); await live; await settle();
    gates[1].resolve({reply:"tracker"}); await settle();
    console.log(JSON.stringify({status, waiting, done:snapshot()}));
    """)
    assert out["waiting"] == 1, "one queued line, not a duplicate turn"
    assert "already waiting to be sent" in out["status"]
    assert out["done"]["converseCalls"] == ["something else", "build me a tracker"]
