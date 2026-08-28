# Paste whatever you have and the platform derives the connection

## Why

Founder, 2026-08-27, after his own GitHub deposit failed three times:

> its suppose to be an easy clear fast way for users to connect any channel that
> uses standered ways to connect even ones we havent thought of. so the ui and
> could should be channel agnostic, plug and play anything. [...] infact the idea
> is they would just drop in paist what ever credentials they have even ones it
> doesnt need and the plateform just figures it out

Today the deposit form asks a user to author an egress policy by hand: a slug
name, a bare hostname, an exact absolute path, a method list, and an auth scheme.
Every one of those is a thing the platform can work out, and every one of them is
a way to fail. The founder — who wrote this system — could not deposit a GitHub
key: the form told him the path was *"optional; default any path"* when a blank
path is always refused, and the refusal came back as
`Couldn't add it: endpoint_not_permitted` with the explaining `detail` dropped.
PR #2599 and #2600 make that form honest. Honest is not the goal; **not asking is
the goal.**

The critical constraint is the one the founder named: **"even ones we havent
thought of."** So this cannot be a table of known services. A per-service lookup
is exactly the hard-coded-effector shape `AGENTS.md` forbids, and it fails on the
first API nobody enumerated. The inference has to come from a model, which
already knows what `api.stripe.com` is and what a `github_pat_` prefix means,
including for services added after this code was written.

## What Changes

- **One box replaces five fields.** The user pastes whatever the service gave
  them — a token, a page of key/value pairs, four OAuth values, a curl example,
  extra credentials the connection does not need — plus an optional one-line
  "what do you want it to do?".
- **The platform derives the connection**: destination name, `auth_scheme`, host,
  path template, and methods. Extra pasted material is ignored, not rejected;
  ambiguity is resolved by the optional intent line, not by asking the user to
  learn the vocabulary.
- **Secrets do not leave the browser to be identified.** Inference runs on the
  *shape* of the pasted material — field labels, public prefixes (`github_pat_`,
  `sk-`, `xoxb-`), any hostnames or URLs present, and value lengths — never the
  high-entropy remainder. The secret itself goes only where it goes today: to
  `connect_http` over TLS, into the per-universe vault.
- **The user confirms one plain sentence**, not a form:
  *"This key will be allowed to POST to `api.github.com/repos/jonnyton/tinyassets/pulls`
  — nothing else."* They review a boundary instead of authoring one.
- **The manual fields survive as a disclosure**, so a service the model reads
  wrongly is corrected in place rather than becoming a dead end.

Deliberately unchanged: `connect_http` itself, the SSRF allow-list validator, and
the per-endpoint method gate. This change decides *who fills the policy in*, not
what the policy is permitted to say. A host-wide grant stays impossible —
widening it is what would make a leaked token dangerous.

## Capabilities

### New Capabilities
- `connection-inference`: deriving a proposed outbound connection policy
  (destination, auth scheme, host, path, methods) from pasted credential material
  plus optional intent, without transmitting secret material, and presenting it
  for confirmation before any deposit.

### Modified Capabilities
- `live-mcp-connector-surface`: adds the resolve operation the app calls to turn
  pasted shape into a proposed policy. New public tool surface, so it is specified
  before it is built.

## Impact

- `tinyassets/onboarding/app.html` — the "Any API service" card collapses to one
  textarea + optional intent line + confirm step; existing fields move behind a
  disclosure.
- `tinyassets/api/` — a new resolve handler; `connect_http` is called unchanged
  with the confirmed policy.
- `openspec/specs/live-mcp-connector-surface/spec.md` — one added operation.
- Follows PR #2599 and #2600, which land the honest-form fixes this supersedes.
- Related: `docs/concerns/2026-08-27-credential-deposit-refusals-are-unobservable.md`
  (refusals are invisible to the operator; unchanged by this proposal).
