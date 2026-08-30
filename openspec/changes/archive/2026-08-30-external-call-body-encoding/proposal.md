## Why

The live naive-user retest on 2026-08-29 (production, universe
`u-01kxm1vszd8hwp7em418asq8h9`) got a user's agent all the way to a commit on
a GitHub branch — and the commit corrupted the file. GitHub's contents API
takes file content as base64; `authenticated_external_call` passes
`request.body` through verbatim, so the graph's writer node had to produce
the base64 itself. First attempt: `422 content is not valid Base64`. Second:
valid base64 of a JSON-escaped string — `README.md +2/-87`, every newline a
literal `\n` (`7de31f12` on `auto/tiny-docs-touch-20260829d`). The universe's
own diagnosis: "redesign this delivery path away from model-generated base64".
Finding: `docs/concerns/2026-08-29-file-writes-need-model-generated-base64.md`.

This blocks the founder's goal — a naive user's agent scoping, building and
pushing real PRs from the app — because every file write goes through it.

## What Changes

Five additive, channel-blind body transforms in the outbound effector's packet
contract, applied in the effector process before `proxy.request` (the text
is not a secret; the worker stays credential-blind and unchanged). Anywhere
in `request.body`, a one-key object in the reserved `$ta.` namespace:

- `{"$ta.base64": X}` — base64 of X's UTF-8 bytes; `{"$ta.from_base64": X}` —
  the UTF-8 text of base64 X (text files only); `{"$ta.concat": [X, …]}`.
- `{"$ta.ref": "key.a.0.b"}` — a value from the run's state, fenced to the
  emitting node's declared `input_keys` and state_schema-defaulted keys
  (narrower than the compiler's render view, deliberately).
- `{"$ta.effect": "node.response.body.x"}` — `response.body` or
  `response.status` from the evidence of an EARLIER node's generic-call effect
  in the same run ("earlier" = stored earlier in the branch, the order effects
  fire in). This is what removes the model from the byte path: a `fetch` node
  and a `write` node in ONE run, the model authoring only the new line. The
  first cut (a bare `$base64`) still needed the model to carry the fetched
  bytes; the live "repair" showed why that fails — bytes through a model are
  transcribed, not copied.

Bounds refuse the whole call before anything is sent: nesting > 32, a
cumulative working set > 32 MiB (charged as values are produced), a
transformed body > 8 MiB, an unknown `$ta.*` spelling, a reference outside
the fence, bytes that are not UTF-8 text. The persisted effect evidence keeps
a 4 KiB body preview (size + sha256), so a fetched file does not re-enter a
model through `read_graph target="run"`; the full body is available only to
later nodes in the same dispatch. A body with no `$ta.*` transform is sent
byte-for-byte, its own `$`-keys included.

## Impact

- `tinyassets/effectors/authenticated_external_call.py` (transforms, fence,
  bounds, `bounded_evidence`), `tinyassets/effectors/__init__.py` (per-node
  fence, in-run chain, storage-order contract), `tinyassets/engine_mcp_server.py`
  (`write_graph` docs the SERVED agent reads), `tinyassets/api/prompts.py`.
- Spec: `external-effect-adapters` gains the transform requirement (delta in
  `specs/`).
- Authority: this is a **read-authority** change, kept strictly narrower than
  what the node already had — an effect packet may read its node's declared
  inputs and earlier effects' body/status, and nothing else. Public effector
  contract, so it is specified here (AGENTS.md: spec what is hard to reverse).
