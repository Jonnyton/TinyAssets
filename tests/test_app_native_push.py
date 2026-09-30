"""The phone app's notification code, executed at its native and HTTP boundaries.

The shipped functions are pulled out of ``app.html`` and run under Node with
the Capacitor plugins and ``fetch`` replaced -- the two edges of the page.
Nothing between them is stubbed, so these fail if the code posts the wrong
platform, names an owner, forgets the bearer, or leaves a registration behind
for the next person to sign in.
"""
from __future__ import annotations

from tests.test_app_browser_notifications import functions, run_js

NAMES = (
    "notificationSession", "notificationAPI", "nativePush", "wireNativePush",
    "nativeFcmToken", "registerNativeNotifications", "rebindNativeNotifications",
    "unregisterNativeNotifications",
)

# The page's own globals the functions close over, then a fake push plugin.
PRELUDE = """
const NATIVE=true, NATIVE_PUSH_FLAG="app.push.fcm";
let nativePushWired=false, nativeTokenWaiter=null, pendingReply=null;
const store={}, localStorage={getItem:k=>k in store?store[k]:null,
  setItem:(k,v)=>{store[k]=String(v);},removeItem:k=>{delete store[k];}};
const MCP={_loginEpoch:1}; let queueOwner='alice'; const token=()=>'alice-token';
const calls=[], posts=[], listeners={};
let permission='granted', registerBehavior='token', postOk=true, FCM='fcm-token-1';
const plugin={
  checkPermissions:async()=>({receive:permission}),
  requestPermissions:async()=>{calls.push('requestPermissions');return {receive:permission};},
  addListener:(name,fn)=>{(listeners[name]=listeners[name]||[]).push(fn);},
  register:async()=>{
    calls.push('register');
    if(registerBehavior==='reject') throw new Error('FirebaseApp is not initialized');
    setTimeout(()=>(listeners.registration||[]).forEach(f=>f({value:FCM})),0);
  },
  unregister:async()=>calls.push('unregister'),
  removeAllDeliveredNotifications:async()=>calls.push('removeAll'),
};
const nativePlugin=name=>name==='PushNotifications'?plugin:null;
const fetch=async(path,options)=>{posts.push({path,options,body:JSON.parse(options.body||'null')});
  return {ok:postOk,status:postOk?200:500,json:async()=>({device_id:'dev_1'})};};
const out=()=>console.log(JSON.stringify({calls,posts,store}));
"""


def run(body: str, *, names=NAMES):
    return run_js(functions(*names) + PRELUDE + "(async()=>{" + body + "})();")


def test_turning_notifications_on_registers_the_phone_under_the_session():
    out = run("""
await registerNativeNotifications(notificationSession());
out();""")

    [post] = out["posts"]
    assert post["path"] == "/app/devices"
    assert post["options"]["headers"]["Authorization"] == "Bearer alice-token"
    # Nothing in the body names an owner: the server takes it from the bearer.
    assert post["body"] == {"platform": "fcm", "token": "fcm-token-1",
                            "label": "This phone"}
    assert out["store"]["app.push.fcm"] == "1"


def test_a_denied_permission_registers_nothing():
    out = run("""
permission='denied'; let error='';
try{ await registerNativeNotifications(notificationSession()); }catch(e){ error=e.message; }
console.log(JSON.stringify({calls,posts,store,error}));""")

    assert out["posts"] == []
    assert "register" not in out["calls"]
    assert "blocked" in out["error"]
    assert "app.push.fcm" not in out["store"]


def test_a_build_without_firebase_says_so_instead_of_hanging():
    out = run("""
registerBehavior='reject'; let error='';
try{ await registerNativeNotifications(notificationSession()); }catch(e){ error=e.message; }
console.log(JSON.stringify({posts,store,error}));""")

    assert "aren't set up" in out["error"]
    assert out["posts"] == [] and "app.push.fcm" not in out["store"]


def test_a_token_refresh_is_posted_only_for_a_phone_that_opted_in():
    out = run("""
wireNativePush();
(listeners.registration||[]).forEach(f=>f({value:'rotated-1'}));
await new Promise(r=>setTimeout(r,5));
const before=posts.length;
localStorage.setItem('app.push.fcm','1');
(listeners.registration||[]).forEach(f=>f({value:'rotated-2'}));
await new Promise(r=>setTimeout(r,5));
console.log(JSON.stringify({before,posts}));""")

    assert out["before"] == 0          # never opted in: nothing leaves the phone
    [post] = out["posts"]
    assert post["body"]["token"] == "rotated-2" and post["body"]["platform"] == "fcm"


def test_sign_in_reposts_the_current_token_so_a_rotation_while_closed_is_not_lost():
    out = run("""
localStorage.setItem('app.push.fcm','1'); FCM='token-after-rotation';
await rebindNativeNotifications();
out();""")

    [post] = out["posts"]
    assert post["body"]["token"] == "token-after-rotation"


def test_sign_in_does_nothing_for_a_phone_that_never_opted_in():
    out = run("""
await rebindNativeNotifications();
out();""")

    assert out["posts"] == [] and out["calls"] == []


def test_a_registration_that_cannot_move_to_the_new_owner_is_removed_from_the_phone():
    out = run("""
localStorage.setItem('app.push.fcm','1'); postOk=false;
await rebindNativeNotifications();
out();""")

    # Otherwise this phone keeps receiving the PREVIOUS owner's requests.
    assert "unregister" in out["calls"] and "removeAll" in out["calls"]
    assert "app.push.fcm" not in out["store"]


def test_signing_out_drops_the_registration_and_the_notifications_on_screen():
    out = run("""
localStorage.setItem('app.push.fcm','1');
await unregisterNativeNotifications();
out();""")

    assert out["calls"] == ["unregister", "removeAll"]
    assert "app.push.fcm" not in out["store"]


# --- the inline Reply hand-off --------------------------------------------------

REPLY_NAMES = ("collectNotificationReply", "applyPendingReply")

REPLY_PRELUDE = """
const NATIVE=true; let pendingReply=null, railCache=[];
const fields={'fb_req_1::one':{value:''},'note_req_1::one':{},'fb_req_1':{value:''},
  'note_req_1':{},'composer-input':{value:''}};
const $=id=>fields[id]; const answered=[], refreshed=[];
const answerRail=(target,mode,note,buttons)=>answered.push(
  {target,mode,text:fields['fb_'+target.request_id].value});
const refreshRail=()=>refreshed.push(1);
let consumed=null;
const nativePlugin=name=>name==='NotificationReply'?{consume:async()=>consumed}:null;
"""


def run_reply(body: str):
    return run_js(functions(*REPLY_NAMES) + REPLY_PRELUDE + "(async()=>{" + body + "})();")


def test_a_reply_collected_natively_is_submitted_as_an_item_answer():
    out = run_reply("""
consumed={request_id:'req_1',item_id:'one',text:'Yes, at noon'};
railCache=[{request_id:'req_1',items:[{item_id:'one',status:'pending',fields:[]}]}];
await collectNotificationReply();
applyPendingReply();
console.log(JSON.stringify({answered,pending:pendingReply}));""")

    [sent] = out["answered"]
    assert sent["mode"] == "reply" and sent["text"] == "Yes, at noon"
    assert sent["target"]["request_id"] == "req_1::one"
    assert sent["target"]["parent_request_id"] == "req_1"
    assert out["pending"] is None       # once: never submitted twice


def test_a_reply_to_a_whole_request_goes_through_the_same_answer_path():
    out = run_reply("""
pendingReply={request_id:'req_1',item_id:'',text:'Looks good',seen:0};
railCache=[{request_id:'req_1'}];
applyPendingReply();
console.log(JSON.stringify({answered}));""")

    assert out["answered"][0]["target"]["request_id"] == "req_1"
    assert out["answered"][0]["text"] == "Looks good"


def test_no_reply_waiting_changes_nothing():
    out = run_reply("""
consumed={};
await collectNotificationReply();
console.log(JSON.stringify({pending:pendingReply,refreshed}));""")

    assert out["pending"] is None and out["refreshed"] == []


def test_a_reply_to_a_request_already_answered_elsewhere_is_kept_not_lost():
    out = run_reply("""
pendingReply={request_id:'req_1',item_id:'one',text:'too late',seen:0};
railCache=[{request_id:'req_1',items:[{item_id:'one',status:'answered'}]}];
applyPendingReply(); const mid=pendingReply!==null; applyPendingReply();
console.log(JSON.stringify({answered,mid,pending:pendingReply,composer:fields['composer-input'].value}));""")

    assert out["answered"] == []          # never re-answers a resolved item
    assert out["mid"] is True and out["pending"] is None
    assert out["composer"] == "too late"


def test_a_reply_never_overwrites_what_the_owner_is_typing():
    out = run_reply("""
fields['composer-input'].value='my own draft';
pendingReply={request_id:'gone',item_id:'',text:'reply text',seen:1};
railCache=[];
applyPendingReply();
console.log(JSON.stringify({composer:fields['composer-input'].value,pending:pendingReply}));""")

    assert out["composer"] == "my own draft"


def test_the_reply_waits_for_the_card_rather_than_submitting_into_nothing():
    out = run_reply("""
pendingReply={request_id:'req_1',item_id:'',text:'hi',seen:0};
railCache=[{request_id:'req_1'}];
delete fields['note_req_1'];
applyPendingReply();
console.log(JSON.stringify({answered,pending:pendingReply!==null}));""")

    assert out["answered"] == [] and out["pending"] is True
