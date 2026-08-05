## Context

Live production, 2026-08-05 (`git_sha df80b753`, canary green): `converse`
returns `held / setup_required`, `missing: ["compute", "model_access"]`, and
tells the caller "Engine assignment is not exposed by the advertised handles."
The V1 golden path reaches step 6 of 8 — discover, remix, bind privately, author
a Branch, publish an immutable version, and **execute a workflow with real
provider calls** all work — then stops, because the conversational surface has no
engine and a created automation never activates.

Three facts constrain the design:

1. `retire-mcp-provider-secret-deposit` (BREAKING) prohibits `llm_api_key`
   deposit through MCP. Requester keys belong in a requester-controlled
   executor's OS secret store, with only an opaque reference in the control
   plane. It explicitly leaves **subscription** custody unchanged.
2. `constrain-set-engine-provider-authority` records that `set_engine` wrote a
   *preference* without constraining `allowed_providers`, so a failed
   user-selected engine could fall through to an unchosen provider. That change
   is still open (~5 `ADAPT` rounds).
3. `provider_work_enrollment.py` already models requester-owned provider
   authority correctly: providers `{codex, claude-code}`, an opaque
   `credential_reference_digest`, and binding to owner + universe + generation
   with caps and expiry. Production reports both writers `ok — subscription auth
   available`.

## Goals / Non-Goals

**Goals:**
- A universe owner selects their providers through the advertised canonical
  handles, in an ordinary chatbot turn.
- Branches and automations each carry `preferred_provider` + ordered
  `accepted_fallbacks`, resolved fail-closed.
- Requester-owned automations execute without depending on a named maintainer
  daemon, many per owner, concurrently.
- Activation failures name a blocker and a next action.

**Non-Goals:**
- Accepting, storing, or transporting any provider credential. No new
  credential path whatsoever.
- Adding an advertised MCP handle. The canonical seven stay seven.
- Re-litigating the `allowed_providers` boundary owned by
  `constrain-set-engine-provider-authority`; this change consumes that
  boundary's outcome.
- Building the Slack adapter, or the tray-to-cloud cutover.

## Decisions

### D1 — Selection is a projection over enrollment, never a credential intake

The selection surface accepts only *identifiers of already-enrolled providers*.
It resolves against `provider_work_enrollment` for the authenticated owner +
universe, and rejects anything not in that set. It has no field capable of
carrying a secret, and validation rejects key-shaped input outright rather than
storing and ignoring it.

*Why:* this is the entire reason the change is compatible with
`retire-mcp-provider-secret-deposit`. If selection could ever accept a key, it
becomes the prohibited surface. The invariant must be structural, not a
convention — hence "no field capable of carrying a secret", verified by a test
that feeds key-shaped values and asserts rejection.

### D2 — A selection narrows `allowed_providers`; it never merely orders them

Writing a selection SHALL set `allowed_providers` to exactly
`{preferred} ∪ accepted_fallbacks`, intersected with the enrolled set. Routing
outside that set is refused, not deprioritised.

*Why:* this is the precise defect `constrain-set-engine-provider-authority`
found — a preference list that reorders but does not constrain lets a failed
choice consume unrelated quota or cross a privacy boundary. "Preferred + accepted
fallbacks" is the host's phrasing; the *accepted* set is the constraint, and
anything outside it is unaccepted by definition.

### D3 — Empty `accepted_fallbacks` means fail closed

An empty fallback list is a deliberate statement ("only this provider"), not an
absence of configuration. Resolution fails with a named error; it never widens
to "whatever is available".

*Why:* the opposite default is how ambient-credential leaks happen. A universe
that cannot reach its one chosen provider must stop, exactly as
`ambient-credential-fallback-is-an-identity-leak` requires.

### D4 — Two-level policy, intersection semantics

Universe-level selection is the outer bound. Branch- and automation-level policy
may narrow it, never widen it. Effective set =
`workflow_policy ∩ universe_selection ∩ enrolled_set`. An empty intersection is a
fail-closed error naming which of the three produced the empty set.

*Why:* the owner's universe-level choice is a ceiling they set once; a workflow
must not be able to escape it by declaring a different preference. Naming *which*
input emptied the set is what makes the error actionable rather than another
dead end (see D6).

### D5 — Automation policy lives inside the immutable definition digest

`preferred_provider` and `accepted_fallbacks` are part of the automation
definition that `definition_digest` covers, alongside `branch_version_id` and
the accepted-spec digest. Changing policy requires a new definition and a
rebind; it is never mutable state on a live automation.

*Why:* the systemic defect recorded in
[[unified-authority-derivation-rearchitecture]] is authority derived from mutable
DB state. Model policy decides which credentialed provider executes work, so it
is authority-bearing and must be frozen at admission like every other input.

### D6 — Executor selection binds to the provider binding, not a daemon id

An automation's claimable executor class is derived from its
`provider_binding_id`, not from a hardcoded `daemon_id`. Any executor holding a
compatible, live, requester-owned binding may claim it; the cloud drain becomes
one ordinary consumer.

*Why:* today `automation_repo_7a09c311891da0f773aa1a8b024ecd19` carries
`daemon_id: daemon::tinyassets-cloud-drain::8b33ef940c59574e` and cannot run
because that daemon has `runtime_instance_count: 0`. A user's scheduled work
must not queue behind the maintainer's OpenSpec drain. This also makes
"many automations per owner" a capacity question rather than a contention one.

### D7 — Activation health must carry a blocker and a next action

Whenever `health.state` is not a running state, `health.blocker` and
`health.next_action` SHALL be non-null. Production currently returns
`state: activation_stopped` with **both null**.

*Why:* the fields already exist and are empty in exactly the state where they
matter. An owner is told their automation is stopped and given nothing to act
on. This is cheap to fix and is the difference between a self-serve product and
a support ticket.

## Risks / Trade-offs

- **Reopening the secret boundary.** The dominant risk. Mitigation: D1 makes the
  surface structurally incapable of carrying a credential, plus an explicit
  rejection test. Any review finding that a key can reach this surface is
  blocking.
- **Racing `constrain-set-engine-provider-authority`.** That change owns
  `allowed_providers` and has failed ~5 review rounds. Building a second writer
  of the same field would repeat the "surface-by-surface patch" mistake the host
  rejected in [[unified-authority-derivation-rearchitecture]]. Mitigation: this
  change consumes that boundary; if it has not landed, this change's D2 tasks
  block on it rather than reimplementing it.
- **Decoupling from the drain touches live execution.** D6 changes who may claim
  requester-owned work. Mitigation: requester-owned automations only; the drain's
  own path is untouched; concurrency proof required per §14 before rollout.
- **Two-level policy is more surface than one.** A single universe-wide setting
  would be simpler, but the host's directive is explicit that branches and
  automations carry their own policy — and a long-running automation pinned to a
  model is a real need that a universe-wide switch cannot express.
- **Fail-closed will surface as user-visible errors** where the system
  previously "just worked" by reaching for any provider. That is the intended
  trade: a wrong-provider run is worse than a refused one, and D4/D6 require the
  error to name its cause.
