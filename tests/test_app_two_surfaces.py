"""Two surfaces: default geometry and keyboard handoff using shipped functions."""
from tests.test_app_browser_notifications import functions, run_js
from tests.test_app_chat_cloud import call


def test_medium_geometry():
    assert call('cloudDefaultState(false,{w:1280,h:800})')["open"] == {
        "x": 828, "y": 168, "w": 440, "h": 620}
    assert call('cloudDefaultState(false,{w:390,h:700})')["open"] == {
        "x": 0, "y": 280, "w": 390, "h": 420}


DOM = """
let focused='', messages=[];
const frame={setAttribute(k,v){this[k]=v},focus(){focused='frame'},
 contentWindow:{postMessage(m,origin){messages.push([m,origin])}}};
const nodes={'ui-frame':frame,'ui-frame-host':{hidden:false},
 'cc-blank':{focus(){focused='blank'}}, 'chat-stage':{}, 'composer-input':{}};
const $=id=>nodes[id]; const document={body:{}};
"""


def test_focus_frame_or_blank():
    out = run_js(functions('focusCommandCenter') + DOM + """
focusCommandCenter(); const first=focused;
delete nodes['ui-frame']; focusCommandCenter();
console.log(JSON.stringify({first,focused,tabindex:frame.tabindex,messages}));
""")
    assert out == {"first": "frame", "focused": "blank", "tabindex": "0",
                   "messages": [[{"ta_ui": 1, "type": "focus"}, "*"]]}


def test_forward_only_from_unclaimed_focus():
    out = run_js(functions('forwardCommandCenterKey') + DOM + """
const e={key:'ArrowRight',code:'ArrowRight',shiftKey:true,altKey:false,
 ctrlKey:false,metaKey:true,repeat:true,preventDefault(){}};
for(const target of [document.body,nodes['chat-stage'],nodes['cc-blank']]){
 for(const type of ['keydown','keyup']) forwardCommandCenterKey({...e,target,type});
}
forwardCommandCenterKey({...e,target:nodes['composer-input'],type:'keydown'});
nodes['ui-frame-host'].hidden=true;
forwardCommandCenterKey({...e,target:document.body,type:'keydown'});
console.log(JSON.stringify(messages));
""")
    assert len(out) == 6
    for i, message in enumerate(out):
        assert message == [{"ta_ui": 1, "type": "key", "key": "ArrowRight",
                            "code": "ArrowRight", "shiftKey": True, "altKey": False,
                            "ctrlKey": False, "metaKey": True, "repeat": True,
                            "phase": "up" if i % 2 else "down"}, "*"]
