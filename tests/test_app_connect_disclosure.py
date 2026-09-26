"""The primary connect path stands alone until the user asks for the others.

Live 2026-09-26, unpowered free account: the "Connect the model your universe runs
on" ask rendered with "Other ways to connect" already OPEN, so a first-time user met
the one-tap primary button AND an API key / Model URL / Model id form at the same
time — three ways to do one thing, on the screen that decides whether they get a
working universe at all.

The cause was not the markup (``<details id="connect-other">`` ships closed). The
setup panel node is PARKED and reused across every rail refresh, and ``render`` only
ever assigned ``open = true``: once anything had opened it, nothing closed it again.

So the element's state is now DERIVED from a remembered user intent on every render.
Executes the REAL renderer sliced out of the shipped ``app.html`` — only the DOM and
the transport are synthetic.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from tinyassets.onboarding import render_app_html

_SLICE_START = "  // ---- Pending-request rail ---"
#: Stops before the endpoint-connect call, which needs the MCP transport. Everything
#: this test drives -- the rail renderer, `connectBody`, `ConnectShapes` and
#: `forgetFinishedSetup` -- is inside the slice.
_SLICE_END = "  // A declared model list needs a context size"

#: A DOM that records exactly what the renderer set, and nothing else. `open` is a
#: plain property here, as it is on a real <details>, so a test can prove the
#: renderer ASSIGNS it rather than relying on the markup default.
HARNESS = r"""
const elements=new Map();
function node(tag){
  const n={tag,children:[],attrs:{},textContent:'',id:'',className:'',type:'',
    hidden:false,open:false,disabled:false,dataset:{},listeners:{},
    replaceChildren(){this.children=[];},
    append(...k){this.children.push(...k);},
    appendChild(c){this.children.push(c);return c;},
    setAttribute(k,v){this.attrs[k]=String(v);},
    getAttribute(k){return Object.prototype.hasOwnProperty.call(this.attrs,k)?this.attrs[k]:null;},
    addEventListener(e,h){this.listeners[e]=h;},
    closest(){return null;},
    classList:{toggle(){},add(){},remove(){}},
  };
  return n;
}
const $=id=>{if(!elements.has(id)){const e=node(id);e.id=id;elements.set(id,e);}
  return elements.get(id);};
const document={createElement:node,addEventListener(){}};
const window={};
const HostedModelConnect={adopt(){},configure(){},setup:null};
// The real ids the page uses, declared above the slice.
const CONNECT_REQUEST_ID='sys_connect_llm';
function foldedModelAccess(){return null;}
function railBody(){return node('body');}
function autoGrow(){}
__SOURCE__
// Tap the disclosure the way a user does: the browser flips `open`, then fires
// `toggle`. Anything that only flips the property is not a tap.
function tapOther(){
  const d=$('connect-other');
  d.open=!d.open;
  if(d.listeners.toggle) d.listeners.toggle();
}
function ask(over){
  return Object.assign({
    request_id:CONNECT_REQUEST_ID, kind:'Setup', title:'Connect the model your universe runs on',
    body:'Your universe has no model yet.', sticky:true,
    // `type:'connect'` + a `setup` block is what isSetupRequest recognises. Without
    // the type it is an ordinary rail row, the setup panel is never rendered, and
    // every assertion below would pass for the wrong reason.
    action:{type:'connect',
      setup:{primary:{provider:'a-source',label:'Continue'},shapes:['api_key','local']}},
  }, over||{});
}
__STEPS__
console.log(JSON.stringify({open:$('connect-other').open,
  hidden:$('connect-other').hidden, remembered:connectOtherOpen}));
"""


def _slice() -> str:
    html, _ = render_app_html()
    return html[html.index(_SLICE_START) : html.index(_SLICE_END)]


def run(steps: str) -> dict:
    node = shutil.which("node")
    if not node:  # pragma: no cover - the shipped page is JavaScript
        pytest.skip("node is required to execute the shipped renderer")
    program = HARNESS.replace("__SOURCE__", _slice()).replace("__STEPS__", steps)
    result = subprocess.run(
        [node, "-e", program],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


STICKY = "renderRail([ask()]);"


def test_the_primary_path_stands_alone_on_a_first_render():
    """The regression: an unpowered account met both paths at once."""
    state = run(STICKY)
    assert state["open"] is False
    assert state["hidden"] is False  # discoverable, just not unfolded


def test_it_opens_on_the_users_tap():
    state = run(STICKY + " tapOther();")
    assert state["open"] is True
    assert state["remembered"] is True


def test_a_rail_refresh_does_not_fold_the_users_tap_back_shut():
    """The failure mode of a naive fix: closing it on every poll."""
    state = run(STICKY + " tapOther(); renderRail([ask()]); renderRail([ask()]);")
    assert state["open"] is True


def test_a_stale_open_on_the_parked_node_is_not_inherited():
    """The actual cause. The node survives refreshes; its state must not."""
    state = run("$('connect-other').open=true; renderRail([ask()]);")
    assert state["open"] is False
    assert state["remembered"] is False


def test_with_no_primary_path_the_fields_are_the_path_and_stay_open():
    """Never hide the only way through: no one-tap source means these fields ARE it."""
    no_primary = "renderRail([ask({action:{type:'connect',setup:{shapes:['api_key']}}})]);"
    assert run(no_primary)["open"] is True


def test_an_optional_row_the_user_opened_shows_the_fields():
    """A non-sticky 'connect another' row is the user asking for exactly this."""
    optional = "railOpen=CONNECT_REQUEST_ID; renderRail([ask({sticky:false})]);"
    assert run(optional)["open"] is True


def test_finishing_setup_forgets_the_tap():
    """Same transition the connected-optional collapse uses: blocking -> optional."""
    state = run(
        "renderRail([ask()]); tapOther();"
        " renderRail([ask({sticky:false})]);"
    )
    assert state["open"] is False
    assert state["remembered"] is False


def test_the_markup_still_ships_closed():
    """Belt and braces: the default must not depend on the renderer running."""
    html, _ = render_app_html()
    block = html[html.index('<details id="connect-other"'):]
    assert block[: block.index(">")].find(" open") == -1
