"""One malformed UI must not hide the command centers a person built.

Founder, live, 2026-10-03: "i wasnt able to sellect from the command centers i
had built anymore". Their agent had set ``"version": 1791005187`` -- a
timestamp, used as a cache-buster -- on one component. The app renders format
version 1 and refuses anything else, and ``readLibrary`` returned the FIRST
refusal for the whole list, so the switcher said "Installed UIs unreadable ...
Installing would overwrite them, so it is disabled" and every other UI
disappeared with it.

The fix is per-entry: the readable UIs stay usable, the unreadable ones are
named with the parser's own reason, installing still works, and nothing that
could not be parsed is ever dropped from the stored list. The server read says
the same thing to the agent (``renderable`` + ``reason`` + ``fix``), so whoever
broke it can see why.
"""
# ruff: noqa: E501 -- embedded JavaScript fixture mirrors controller expressions
from __future__ import annotations

import re
from pathlib import Path

from tests.test_custom_ui_bridge import _run

#: The founder's actual value, so the fixture is the incident.
CACHE_BUSTER = 1791005187

LIBRARY = r'''
// Three UIs the person built, with the middle one carrying a timestamp where
// the format version belongs -- the founder's row, reduced.
const GOOD_A=bundleOf({ui_id:'office',name:'Office building'});
const BROKEN={...bundleOf({ui_id:'furry-house',name:'Furry House'}),version:1791005187};
const GOOD_B=bundleOf({ui_id:'village',name:'Village'});
const uiText=()=>$('ui-list').children.map(li=>
  (li.textContent||'')+li.children.map(c=>c.textContent||'').join(' ')).join(' | ');
'''

CHECKS = r'''
(async()=>{
const u=AppUI;
u.enabled=true;u.home=HOME;u.principal=PRINCIPAL;

// ---- the incident: one bad component used to hide every UI --------------
appUi=stored([GOOD_A,BROKEN,GOOD_B],{version:1,state:'active',ui_id:'office'});
u.adopt(clone(appUi));

assert.equal(u.unreadable,'','the library as a whole is readable');
assert.deepEqual(u.library.map(b=>b.ui_id),['office','village'],
 'both good UIs are selectable');
assert(u.active&&u.active.ui_id==='office','the chosen UI still mounts');
assert(/Using Office building/.test($('ui-status').textContent),$('ui-status').textContent);

// The broken one is named, with the reason, and the person is told how many.
assert.equal(u.broken.length,1);
assert.equal(u.broken[0].ui_id,'furry-house');
assert.equal(u.broken[0].label,'Furry House','named by its own name, not its id');
assert(/1791005187/.test(u.broken[0].reason),u.broken[0].reason);
assert(/version/.test(u.broken[0].reason),u.broken[0].reason);
assert(/1 installed UI cannot be shown/.test($('ui-status').textContent),$('ui-status').textContent);

// ---- the switcher lists the good ones and flags only the broken one -----
u.paint();
const listed=uiText();
assert(/Use Village/.test(listed),listed);
assert(/Using: Office building|Use Office building/.test(listed),listed);
assert(/Furry House cannot be shown/.test(listed),listed);
assert(/1791005187/.test(listed),'the reason reaches the screen: '+listed);
assert(!/Installed UIs unreadable/.test($('ui-status').textContent),
 'the blanket refusal is gone');
assert(!/No custom UI installed/.test(listed),
 'a library with entries never reads as empty: '+listed);

// ---- installing is not disabled, and the bad entry is NOT lost ----------
const before=clone(appUi.ui_library.find(e=>e.ui_id==='furry-house'));
const added=await u.install(bundleOf({ui_id:'newcomer',name:'Newcomer'}));
assert(added.ok,'installing works beside a broken entry: '+JSON.stringify(added));
const stillThere=appUi.ui_library.find(e=>e.ui_id==='furry-house');
assert(stillThere,'the entry the app cannot parse is still stored');
assert.deepEqual(stillThere,before,'and is byte-identical: it was carried, not rewritten');
assert.deepEqual(appUi.ui_library.map(e=>e.ui_id).sort(),
 ['furry-house','newcomer','office','village']);

// ---- switching to a good UI still works while one is broken ------------
await u.choose('village');
assert(u.active&&u.active.ui_id==='village','a good UI is selectable: '+JSON.stringify(u.active));

// ---- choosing the broken one says WHICH and WHY ------------------------
appUi=stored([GOOD_A,BROKEN],{version:1,state:'active',ui_id:'furry-house'});
u.adopt(clone(appUi));
assert.equal(u.active,null,'nothing is mounted for an unrenderable choice');
const why=$('ui-status').textContent;
assert(/Furry House cannot be shown/.test(why),why);
assert(/1791005187/.test(why),why);
assert(!/no longer installed/.test(why),'it IS installed; it cannot render: '+why);
assert(/your other UIs still work/i.test(why),why);

// ---- a library that is not a list at all is still library-wide ---------
u.adopt({...stored([],null),ui_library:'not a list'});
assert(u.unreadable,'that one really is unreadable');
assert(/Installed UIs unreadable/.test($('ui-status').textContent),$('ui-status').textContent);

// ---- an entry with no usable name is still named by position ----------
u.adopt(stored([{kind:'tinyassets.app-ui.v1'}],null));
assert.equal(u.broken.length,1);
assert.equal(u.broken[0].ui_id,'','no id is recorded when it is not well formed');
assert(/position 1/.test(u.broken[0].label),u.broken[0].label);

console.log('one-bad-component checks passed');
})().catch(err=>{console.error(err);process.exit(1);});
'''


def test_one_malformed_ui_leaves_every_other_ui_selectable(tmp_path) -> None:
    out = _run(tmp_path, "one_bad_component.js", CHECKS, extra=LIBRARY)
    assert "one-bad-component checks passed" in out


def test_the_controller_no_longer_aborts_the_library_on_one_entry() -> None:
    """The shipped controller, read as text: no early return in readLibrary.

    The regression was structural -- ``return parsed`` inside the loop. A test
    that only drives the happy path would pass again if someone restored it,
    because the first entry parses.
    """
    source = Path("tinyassets/onboarding/app_ui.js").read_text(encoding="utf-8")
    body = re.search(r"readLibrary\(configuration\)\{(.*?)\n    \},", source, re.S)
    assert body, "readLibrary is still a method on the controller"
    loop = body.group(1)
    assert "broken.push" in loop, "an unparsable entry is set aside, not returned"
    assert "if(!parsed.ok) return parsed" not in loop, (
        "readLibrary must not abandon the whole library on one entry")
