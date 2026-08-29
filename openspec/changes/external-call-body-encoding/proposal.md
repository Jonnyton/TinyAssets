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

One additive, channel-blind body transform in the outbound effector's packet
contract: a JSON value of the form `{"$base64": "<utf-8 text>"}` anywhere in
`request.body` is replaced, inside the credential-blind worker, by the base64
of that text before the request is sent. The inverse for reads,
`{"$utf8_of_base64": ...}`, is out of scope here: responses already arrive as
evidence and a text node can decode them; the corruption happens on the write.

- The platform still knows nothing about GitHub or any channel; it knows one
  encoding. The packet stays fully user-specified.
- No behaviour changes for packets that do not use the sentinel.
- The sentinel is refused (secret-free error, never a raise) when the value
  is not a string, so a malformed packet cannot send a half-transformed body.

## Impact

- `tinyassets/effectors/authenticated_external_call.py` (packet doc + the
  transform applied to `wire_request["body"]` before `proxy.request`), the
  broker worker if the transform must run inside it (it need not: the text is
  not a secret), tests beside the effector's.
- Spec: the outbound-channel capability's packet-shape requirement gains the
  transform (delta in `specs/`).
- The `control_station` prompt / node-authoring guidance should say: write
  file content as text with `{"$base64": ...}`; never generate base64.
- Not a migration, not money, not authority: the surface is additive. Public
  effector contract, so it is specified here before code (AGENTS.md: spec what
  is hard to reverse).
