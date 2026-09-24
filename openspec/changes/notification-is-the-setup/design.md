# Design: the notification is the setup

## Shape

The rail's synthesized `sys_connect_llm` entry is the only way into model
setup. `openConnectRequest()` replaced `showConnect()`: it shows the chat,
opens that request, and re-reads the rail. Every former caller uses it: sign-in,
the model dialog's "Connect a source", the voice "unpowered" path, the
`setup_required` notice, and Account > Back after a disconnect.

The panel is one DOM node (`#connect-panel`). `renderRail` moves it into the
request's tab on each render and parks it before rebuilding, so typed values
survive the 15-second rail refresh. While the entry is sticky (unpowered), the
rail widens on desktop and moves above the thread on a phone.

The app names no provider. The primary button's label, the key-page link and
the manual-key opt-in come from `action.setup.primary`, which the server reads
from `acquisition_presets.json`. A malformed primary hides the button.

## Click path (free-only account)

1. Sign in. The chat opens with "Connect the model your universe runs on" open
   first in the rail, showing "Continue with <preset name>".
2. Tap it. Sign in or sign up at the provider and approve (provider steps).
3. The provider redirects to `/mcp/app/model-callback/<flow>`. The app strips
   the code from the URL, redeems it (`/mcp/app/model-connect/exchange`) and
   answers the returned `bind_model_access` request with `{values:{}}`. It then
   re-reads `/mcp/app/me` and says "Your universe is connected. Say hello."

That is two taps plus the provider's sign-in. Every step on the way is
deterministic: the key exchange, the ledger connection and grant, the catalogue
and benchmark fetch through the broker, free-model selection (price 0, tools
supported), and the serving bind. No model is called before the first reply.

## Failure handling

| Situation | What the owner sees |
|---|---|
| Sign-in cancelled or expired | The request, with "nothing was connected; continue again" |
| Exchange outcome unknown | "Not finished yet ... tap Finish connecting". No auto retry |
| Answer lost (deploy restart, non-JSON, empty) | The request kept; "Not connected yet, and nothing was lost. Tap Finish connecting" |
| Answer landed but the reply was lost | Re-read of `/mcp/app/me` shows connected |
| Pending free-model request on reload | Folded into the setup; one tap finishes it |
| Message sent while unpowered | `setup_required`: "Your universe has no model connected yet, so nothing ran ... Connect one from the request under Waiting on you" |

## Live acceptance (free-only second account, after deploy)

Pre-state: unpowered. The founder's reset went through the product (Account >
Disconnect), and the rail shows the connect request.

1. Open https://tinyassets.io/mcp/app and sign in. Expect the normal chat with
   the connect request open first, and no full-page "Connect a model" screen.
2. Tap "Continue with OpenRouter" (tap 1), then approve at OpenRouter (tap 2).
3. Expect a return to the chat with "Your universe is connected. Say hello."
   The rail shows only a collapsed "Connect another LLM", with no Models card.
4. Send "hi! what can you do?". Expect a reply from a free model, with the
   execution line naming the actual model, and at least one tool use when
   asked something that needs one (for example "what's in your brain?").
5. Evidence: the provider-call ledger has no calls for the universe before
   that reply's turn; `deployed_sha.py --assert-contains <sha>`.
6. Account page: the connection reads "OpenRouter (free models)".
7. Optional second source: expand "Connect another LLM" > API key, then paste
   a URL, key and model id. Expect "Connected. Your universe keeps its current
   model".
