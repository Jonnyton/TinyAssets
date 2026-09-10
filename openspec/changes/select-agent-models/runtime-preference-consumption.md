# Consume preferences at the real conversational boundary

September10 2026, next integration of tasks2.1/2.2/2.4. Existing change and
approved policy/authority stores, not a new proposal or claim of activation.

## Verified gaps

universe_server.converse currently accepts message/graph/input-method and calls
universe_intelligence.converse without selection. That sink constructs a genuine
request carrier but no model_selection or plan. Saved preferences therefore do
not affect real turns. Separately, provider_serving_binding.set_serving calls
_current_serving_authority, which rejects every assignment with manifest_digest.
The composition fixtures bypass that readiness gate internally. No user-facing
completion claim may rely on those fixtures alone.

## One request plan, not two competing choices

Add optional model_choice to canonical converse and its internal sink, carrying
the existing versioned ModelPreferences document. None means use saved settings;
an explicit document replaces the entire current order for this turn only.
Automatic explicitly clears the saved primary for this turn. No implicit append
of the old saved default, no save side effect, no cross-tab/global current state.
Unknown fields/types and unsupported versions fail before provider work. Reuse
the existing codec rather than invent a second reference/order format.

After genuine carrier minting, capture saved preferences from the current-home
guarded store using the verified principal and universe, never body identities.
Capture generation once. Missing row and missing override preserve the legacy
binding path exactly. A corrupt/unavailable row is held, not treated as absent.
An override or saved policy on a legacy assignment cannot expand model authority:
report that its accepted model scope needs updating through the existing binding
flow. No implicit publication or grant extension. Saving preferences alone still
does not alter assignments or credentials.

Build the plan from current accepted assignment members. Reuse _served_request_agent
and _current_selected_member_authority for owner, agent revision, current home,
accepted binding, custody and grant checks. No SQLite transaction or assignment
lock spans discovery IO. Re-read the same authoritative chain after IO, and the
router still validates it before EVERY launch. The captured plan is advisory.
The sink sets model_selection from this plan's first candidate; the runner rejects
a contradictory plan/selection pair rather than silently overriding it.

Discovery uses each connection's existing protocol contract. Preserve fresh
capability/privacy evidence and all accepted model/price restrictions. Filter
advisory candidates per member with the existing eligibility kernel, not the
definition's legacy model string. A plan-wide price ceiling must not relax a
member's ceiling; if using a combined advisory ceiling, pre-filter each member
under its own exact bounds and revalidate actual attempts independently. Retain
unfiltered choices and exclusion reasons for the eventual UI. Ranking source is
trusted boundary configuration; never a client-selected benchmark name.

## Native default and mixed-source correctness

Do not label every non-HTTP member unavailable and silently choose OpenRouter.
The automatic path must include genuinely available accepted native/local sources
and prefer their default as required by PLAN. Native execution stays native,
without a fabricated HTTP SelectedModel or cost/context facts. An empty native
model reference means provider default; fresh explicit selections alone may set
a native per-request model argument. Do not activate previously ignored model
fields in definitions or mutate process environment/global provider objects.

Native discovery/selection needs an executor-bound contract, with unsupported
discovery honestly distinguished from provider-default execution. No core model
release lists or inferred account independence. Unknown native turn effects keep
the existing no-replay rule; do not restart a CLI turn merely to traverse a
fallback list. Mixed-source continuation is allowed only with a proved safe
inference boundary and portable known progress. HTTP-only support is an interim
implementation stage, not a substitute for the requested mixed-source behavior.

## Serving activation

Keep _current_serving_authority's legacy-only execution guard. Add the reviewed
multi-model readiness path in set_serving using current accepted member authority,
not a fabricated legacy assignment. At least one supported eligible candidate
under the captured policy must be usable before enabling. Discovery occurs before
the exclusive mutation transaction; recheck assignment, agent revision, preference
generation, home and custody in that transaction before set_binding_serving.
No network call under the transaction and no automatic rewrite of explicit pins.
Readiness is not launch authority: the next genuine request still revalidates.

## Verification and delivery

Use real authenticated converse -> stored policy -> accepted assignment -> serving
enable -> writer -> actual selection paths in tests; don't monkeypatch the new
resolver or manually set serving in those acceptance cases. Cover absent legacy
preferences, saved automatic, saved explicit/empty tail, one-turn override without
save, two owners, changed generation during activation, rebind/deletion/revocation,
paid-model exclusion and per-member limits. Native default must win over HTTP in
mixed automatic mode; explicit HTTP must win when the user selects it. Preserve
all old CLI tests. Windows, Linux oracle and independent review precede landing.
The optional public MCP argument requires both-client rendered pre-merge checks.
UI exposes current choice separately from saved policy only after runtime works.
