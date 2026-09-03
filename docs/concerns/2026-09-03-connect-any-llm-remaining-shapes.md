# "Connect any LLM" is real for one endpoint shape, not every shape

Filed 2026-09-03, from the Codex review of `claude/connect-any-llm` (verdict
ADAPT). The lane fixed the findings it could; these two need a decision, not a
patch, so they are here rather than half-built.

## 1. `anthropic_messages` is offered but can never authenticate (P1, half fixed)

The endpoint pane offers two wire protocols. The deposit always sends
`auth_scheme="bearer"` (`tinyassets/onboarding/app.html`, `depositEndpoint`),
because `bearer` is the only scheme the pane can express. An endpoint that wants
the key in a named header (`x-api-key`, the shape the Messages API documents)
therefore gets the wrong authentication and fails at call time.

`connect_http` already accepts `header` in `_DEPOSITABLE_AUTH_SCHEMES`
(`tinyassets/api/http_connection.py:105`), but **`header_name` is not a
deposit-time field** — it exists only for `authenticated_external_call`. So the
pane cannot express "this key goes in `x-api-key`" today.

Not silently removed, because it is not universally broken: gateways that speak
the Messages wire shape while accepting `Bearer` do work. It is broken for
endpoints that follow the published spec, which is the more common case.

**Decision needed:** add `header_name` to the deposit contract (a public-surface
change — wants a proposal), or stop offering the protocol until it can be
authenticated honestly.

**Fixed in the same lane, for contrast:** the *path* half of the same finding.
The grant carried the user's own path while the runtime called the protocol's
canonical one, so every endpoint whose path was not `/v1/chat/completions` was
registerable and never servable. `_declared_path` in
`tinyassets/providers/api_key_http_provider.py` now calls what the user granted.

## 2. The picker still reads two company names to the user (P2)

`<option>` labels and `SERVICE_LABELS` render "Claude subscription" and "OpenAI
subscription". The repo's own rule — enforced by
`test_the_deposit_form_names_protocols_not_companies` — is that `value="..."`
attributes are the wire contract and exempt, while everything a user *reads*
must name nobody. That test starts at `connect-endpoint`, so it never sees these
two.

Founder, 2026-09-02: *"must also be all agnostic shapes ... nor should any other
spasific channel code excist."*

Not renamed unilaterally, because the two options are the user's own
subscription credentials and a user has to be able to tell which one to paste. A
neutral label that leaves them guessing is a worse product, and this is the
founder's stated rule, so the wording is the founder's call.

**Decision needed:** the exact replacement wording, or an explicit exemption for
"the name of a credential the user is being asked to supply".

## Why this is not just tidy-up

The deeper version of the same question is live right now: `tiny`'s universe has
a `subscription_cli` `codex` provider registered that resolves to the *daemon
host's* CLI. Per [[no-host-writer-ever-prune-all-fleets]] the platform must never
supply an LLM, so that provider must never serve. If the two subscription options
are host-CLI-backed rather than user-credential-backed, they are not "vendor
labels to rename" — they are a route that should not exist at all. Worth
answering before rewording anything.
