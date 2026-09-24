# The notification is the setup

**Founder, 2026-09-24:** "the connect model flow should all be happening within
the notification request thing." And: users "should be able to handle all the
connection from those notification requests with as few clicks as possible
connecting the universe to whatever in whatever way they want".

This is Slice 6 of the vendor-neutral migration plan. It builds on Slice 1
(`unify-connection-uses`, the `connect` request action).

## The problem (live, 2026-09-24, a free-only account)

- An unpowered universe's rail already showed "Connect the model your universe
  runs on". Its button switched to a full-page "Connect a model" screen with
  long text, vendor cards (two subscription CLIs), a raw-deposit select, and a
  guided sign-in.
- After the provider sign-in, the page asked for a second approval ("Approve
  free models"). Its text named internal ids ("agent agent_binding_...", "root
  source api_key_http:provdef_...").
- A deploy restarted the daemon mid-approval. The page read the non-answer as
  success, the universe stayed unpowered, and a second "Power your universe
  with free models" card waited beside the first.
- The next message failed with "connect your provider: exactly one founder
  serving binding is required. Actions may already have occurred." Nothing
  had run.
- The Account page listed the connection as `model:openrouter_user_models_v1`.

## What changes

1. **The synthesized `sys_connect_llm` request uses the `connect` action.** Its
   action is `{type: "connect", use: "model", setup: {primary?, shapes}}`.
   `primary` is display data (preset id, label, name, key page, manual-key
   opt-in) read from the installed first-power preset, and it is present only
   while the universe is unpowered. `shapes` lists what the rail completes
   itself (`api_key`, `local`). A command runner joins that list when Slice 3
   exists. The entry grants nothing itself, so its grant sentence is empty.
2. **No full-page setup.** An unpowered, disconnected or unconfirmed universe
   lands in its normal chat with the connect request open and first. The
   setup is one panel inside that request. The vendor cards, the raw-deposit
   select and the connect view are deleted from the app, which names no
   provider.
3. **Two taps.** The primary button starts the guided sign-in. On return the
   app redeems the code and finishes the free-model request it gets back in
   the same step. The owner chose that on the request, whose text says "free
   models only; nothing is bought". "Finish connecting" is the one-tap
   recovery for an interrupted sign-in or an unconfirmed answer.
4. **Only `status: "answered"` counts as an answer.** An empty, non-JSON or
   failed result keeps the request and offers Finish connecting. The page
   re-reads `/mcp/app/me` either way, so an answer whose reply was lost but
   landed shows as connected.
5. **Other shapes in the same request.** An API key plus endpoint, or the
   owner's own server, are explicit fields. The app raises the same `connect`
   ask an agent would, with `uses.model` and a free-only `flat` declaration,
   and answers it in the same tap. There is no inference and no LLM call.
6. **One pending free-model request folds into the setup** while the universe
   is unpowered, so there is never a second card to accept.
7. **Honest text.** The free-model grant sentence names models and limits, not
   storage ids. A turn refused because nothing serves the universe returns
   `setup_required` with a note that points at the request and no "actions
   may already have occurred" caution. Account rows carry a human `label`.

## Tier

Tier 2 by the conservative reading: the rail now collects a model key for the
endpoint shape, and the guided sign-in finishes its free-only approval without
a second screen. Custody is unchanged: every key goes through the existing
`answer_request` / `deposit_key` vault paths. A cross-family review is owed
before landing.

## Out of scope

- `runner: command` (Slice 3), refreshable OAuth2 and device flow (Slice 2).
- Deleting the server-side vendor routes (Slice 7).
- A deterministic `/models` probe for the endpoint shape. The owner types the
  model id.
