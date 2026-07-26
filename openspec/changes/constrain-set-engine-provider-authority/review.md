# Independent review

## Opus 5 architecture review — 2026-07-25

Environment: Windows, replacement branch `codex/reconcile-provider-authority`
based on `origin/main` `d182d5f8`.

Claude Opus 5 returned `ADAPT` on the reconstructed #1691 proposal. The review
found five blocking defects in the historical design:

1. `Verified[T]` could authenticate a request but could not mint
   requester-local provider authority.
2. Provider-secret binding did not prove the current principal, universe,
   provider, host, assignment generation, and binding digest at the sink.
3. Universe birth initialized engine state without a matching authority
   invariant.
4. Reciprocal acceptance gates among provider routing, secret custody,
   universe creation, and host activation formed circular dependencies.
5. Cutover could remove the current founder-home path before any replacement
   source was live-ready.

The replacement resolves those findings by:

- defining a server-minted, request-local `ProviderRequestCapability` as
  authenticated transport evidence rather than standalone provider authority;
- requiring fresh sink-side intersection with assignment state and an exact,
  live, non-tombstoned credential binding;
- adding an independent deny-all engine-authority invariant to every universe
  birth;
- publishing one-way dependency interfaces while documenting custody's
  provider-owner acceptance output gate;
- separating credential authority from fulfillment class and dynamic provider
  availability; and
- forbidding cutover until at least one live-ready custody or requester-host
  path preserves existing founder-home service.

This is a planning-only OpenSpec lane. Runtime, tests, deployment, and
packaging remain unchecked and outside this replacement's write set.

## Verification

Fresh Windows evidence on 2026-07-25:

- `openspec validate constrain-set-engine-provider-authority --strict`: valid.
- `openspec validate --all --strict`: 48 passed, 0 failed.

Final status is pending an exact-revision Opus 5 re-review and publication of
the final review disposition.

The initial sibling handoffs were published without making this target spec
wait for sibling acceptance:

- custody: PR #1746 comment `issuecomment-5081176707`;
- universe creation / first-contact authority: PR #1660 comment
  `issuecomment-5081177162`; and
- provider-attempt receipts: merged spec PR #1650 comment
  `issuecomment-5081177511`.

## Exact-revision Opus 5 re-review — 2026-07-25

Opus 5 reviewed commit `aa6a2799` and returned `ADAPT`. Critical findings:

1. Ambient request `ContextVar` state cannot cross the router's documented
   class-level thread pool.
2. Post-response graph/run/schedule, daemon, retrieval, and other background
   provider work had no named authority owner.
3. Source resolution did not cover the shipped domain or make
   `ollama-local` reachable under target authority.

Important findings covered conflicting active universe/receipt deltas,
custody's exact-SHA owner-acceptance gate, dependent-lane tasks that made this
change uncompletable, incomplete `complete()`/policy MODIFIED coverage, dropped
canonical clauses, and newborn deny-all ordering ahead of a rendered setup and
ready-source gate.

The adapted artifacts now:

- explicitly carry the server-minted request capability through
  `call_provider`, synchronous router helpers, and the router pool closure;
- name `harden-background-provider-execution-authority` as durable
  task/thread/process receipt owner and hold those paths before it lands;
- define total shipped/target source treatment, including successor-owned
  `local_model` -> `["ollama-local"]`;
- declare precedence over the conflicting active universe bundle and receipt
  enums;
- move sibling work to published expectations rather than this change's
  completion checklist;
- retain canonical provider `complete(...)` under
  `ProviderExecutor.start(...)`, restore every dropped canonical clause, and
  MODIFIED-cover policy plus both sandbox requirements; and
- gate newborn deny-all and cutover on rendered setup, a live-ready request
  source, and complete background bridge classification.

Final disposition remains pending strict validation, adapted exact-SHA
handoffs, and another Opus 5 review.

Adapted exact-SHA `967b048d` handoffs:

- custody provider-owner acceptance: PR #1746 comment
  `issuecomment-5081288367`;
- universe bundle/provider-set precedence: PR #1660 comment
  `issuecomment-5081288830`; and
- receipt closed-enum precedence: PR #1650 comment
  `issuecomment-5081289120`.

## Second exact-revision Opus 5 re-review — 2026-07-25

Opus 5 reviewed `f2b6e9ef` and returned `ADAPT`. One Critical finding showed
that the live first-contact mapper recognizes only
`AllProvidersExhaustedError` plus non-null chain state, so the new
pre-provider `ProviderAuthorityHeldError` would bypass
`engine_setup_required_payload` and become generic failure prose.

Important findings:

- `activate-requester-host-engines` had no durable lane, leaving the target
  zero-cloud local source owner nominal rather than actionable;
- the universe and receipt changes were already merged-active, so their
  conflict must be resolved before archive/sync rather than before merge;
- auth-health quarantine's canonical local-fallthrough requirement was not
  yet MODIFIED by the authority ceiling; and
- inherited asyncio ContextVars could outlive middleware reset without a
  positive server-checkable liveness binding.

The next adaptation adds:

- a universe-lifecycle requirement and owned RED/GREEN task mapping the exact
  typed hold to the canonical setup payload without requiring exhaustion,
  chain state, or provider attempts;
- one durable STATUS row owning both background-receipt and
  requester-host/local successor change directories;
- explicit archive/sync precedence, including the receipt
  `error/provider_error` carve-out;
- a full MODIFIED auth-health requirement with authority-bounded local
  fallback;
- a private server liveness registry bound to the owning request execution
  scope, synchronously revoked at request end and rechecked at the sink;
- explicit newborn `engine_source=unassigned`; and
- exact `credential_kind` and `authority_class` field names.

Fresh Windows strict validation after these edits: target valid; full tree
48 passed, 0 failed. Final disposition remains pending final-SHA handoffs and
another Opus 5 review.

Handoffs first published at review base `1a2262b9`; the stable comment bodies
remain the current exact-revision binding:

- exact-SHA custody acceptance: PR #1746 comment
  `issuecomment-5081341084`;
- typed-held setup mapping plus universe archive/sync precedence: PR #1759
  comment `issuecomment-5081342047`; and
- receipt exception carve-out plus archive/sync precedence: PR #1756 comment
  `issuecomment-5081343125`.

## Third exact-revision Opus 5 re-review — 2026-07-25

Opus 5 reviewed clean commit `1e41d6b0` and returned `ADAPT`. Critical: the
host/local successor wrote engine assignments but did not own interactive
request capability minting for unauthenticated stdio/SSE, so Tier-2 tray,
Tier-3 OSS, and Claude-plugin local surfaces could remain permanently held.

Important findings:

- the canonical setup-required contract was split between
  `identity-auth-and-access-control` and `universe-lifecycle-and-soul`, while
  the merged universe change still mandated raw BYOC/accepted-market paths;
- `_DEFAULT_ENGINE_SOURCE` and `universe_has_assigned_engine` would interpret
  new `engine_source=unassigned` as an assigned engine on the legacy
  exhaustion branch; and
- cutover proved that setup prose rendered, not that any advertised path was
  completable on the user's actual surface.

The next adaptation:

- extends `activate-requester-host-engines` into
  `identity-auth-and-access-control` and gives it the separate,
  session-scoped `ProviderHostRequestCapability` for attested same-user
  stdio/local-SSE/tray/plugin execution;
- moves the typed-held setup contract into
  `identity-auth-and-access-control` under the same requirement name as the
  merged universe change, with explicit archive/sync supersession;
- requires `_DEFAULT_ENGINE_SOURCE=unassigned` and readiness-derived
  `universe_has_assigned_engine`, including legacy exhaustion proof; and
- requires Tier-1 connector-completable accepted-market setup plus
  surface-specific local setup for tray, OSS stdio, and Claude plugin before
  cutover. Raw BYOC and unavailable desktop-only paths are not advertised.

Final disposition remains pending validation, refreshed exact-SHA handoffs,
and Opus 5 approval.

The durable handoff comment IDs used from the second exact-revision re-review
onward remain stable; earlier SHA references and earlier comment triples are
historical review bases, not the current acceptance binding.

## Fourth exact-revision Opus 5 re-review — 2026-07-25

Opus 5 reviewed clean commit `2b5f7a00` and returned `ADAPT`. Critical: the
post-migration engine-readiness rule had no compatibility mode, so landing
optional fields/default changes ahead of migration could classify every
credentialed universe as engine-less and could swallow bare policy/pin/router
faults into onboarding.

Important findings:

- the Tier-1 accepted-market connector gate had no named change owner;
- the merged-active universe change's same-named setup requirement had no
  visible STATUS archive/sync dependency; and
- setup classifier/enforcement tasks did not explicitly bind to a dark
  default-false deployment gate.

The next adaptation:

- adds optional assignment fields plus
  `TINYASSETS_PROVIDER_AUTHORITY_V2=false`; while dark it preserves the shipped
  LLM-vault route, explicit non-default sources, unreadable-state fail-safe
  true, `_DEFAULT_ENGINE_SOURCE=byo_api_key`, and the null-chain bare
  exhaustion carve-out;
- flips defaults/newborn deny-all only after a complete migration manifest and
  every surface gate;
- names `activate-connector-requester-authority` across identity, paid market,
  distributed execution, and the live connector, with an exact-files STATUS
  successor claim; and
- adds `#1784 setup precedence` directly to the active universe-creation
  STATUS row.

Final disposition remains pending validation, refreshed exact-SHA handoffs,
and Opus 5 approval.

## Fifth exact-revision Opus 5 re-review — 2026-07-25

Opus 5 reviewed clean commit `3f57a82f` and returned `ADAPT`. Critical: the
universe-lifecycle delta still required target unassigned/empty-ceiling birth
fields before the global cutover, which would break legacy readiness and bare
exhaustion behavior.

Important findings:

- target enforcement needed one global default-false qualifier so individual
  routing requirements could not partially activate;
- the originating live `set_engine` fallback leak needed a safe narrow fix
  before the three full-authority successors and migration were ready; and
- review artifacts contained multiple historical SHAs without clearly
  separating them from the current acceptance binding.

The next adaptation:

- gates every target birth field on
  `TINYASSETS_PROVIDER_AUTHORITY_V2=true` and adds explicit pre-cutover birth
  preservation;
- states one global dark gate across authority, carriers, assignment state,
  holds, routing, launch, birth, and setup;
- allows only an authenticated explicit legacy raw-BYOC `set_engine`
  assignment to narrow atomically to its canonical singleton destination
  while the full gate remains false; existing records and newborns remain
  untouched; and
- makes the connector successor name an action carried by one of the seven
  canonical live handles in its own OpenSpec, records the currently advertised
  deprecated setup path, and clarifies that the three successor directories do
  not yet exist.

Current exact-revision authority lives in the bodies of these four durable
handoff comments, which task 1.24 requires to match the final PR head before
merge:

- custody acceptance: `issuecomment-5081341084`;
- unified setup contract / universe archive-sync precedence:
  `issuecomment-5081342047`;
- receipt archive-sync precedence: `issuecomment-5081343125`;
- and hidden-action retirement residuals: `issuecomment-5081688386`.

Historical SHA mentions above identify only the artifacts reviewed in that
round. Final disposition remains pending strict validation, exact-head handoff
refresh, and Opus 5 approval.

## Sixth exact-revision Opus 5 re-review — 2026-07-25

Opus 5 reviewed clean commit `caa5e6b4` and returned `ADAPT`. Critical: the
pre-cutover bare singleton ceiling governed every role, not only writer, so an
Anthropic assignment would empty judge/extract/embed chains; accepted service
aliases and five other cloud services were also unspecified.

Important findings:

- the config write can atomically bind source/preference/ceiling, but the
  preceding credential deposit is not rolled back before the later transaction
  task lands;
- identity/auth target clauses needed their own explicit effective-gate
  qualifier;
- surface acceptance under wholly dark enforcement could not prove post-flip
  behavior; and
- hidden legacy `set_engine` is unreachable to Tier-1 chatbot users and needs
  an explicit handoff to the legacy-tool retirement owner.

The next adaptation:

- uses role-complete pre-cutover ceilings
  `["claude-code", "ollama-local"]` and
  `["codex", "ollama-local"]`, normalizes Claude/Codex aliases, and leaves
  other accepted cloud services on disclosed shipped behavior/Q6.3 residual;
- states the credential/config transaction boundary exactly;
- qualifies identity/auth with the same effective gate;
- adds a server-owned, default-empty, isolated-universe canary set that applies
  the complete post-flip contract before global cutover without allowing
  caller opt-in or migrating existing user universes; and
- names the hidden action's retirement handoff while retaining the Tier-1
  connector successor as the only chatbot-ready owner.

Final disposition remains pending strict validation, refreshed exact-head
handoffs, and Opus 5 approval.

## Seventh exact-revision Opus 5 re-review — 2026-07-25

Opus 5 reviewed clean commit `89f69df5` and returned `ADAPT`. It approved the
role-complete cloud-plus-local compatibility ceiling, alias/residual coverage,
config-write boundary, identity gate, exact action authority, and current
comment binding.

Remaining findings:

- one carrier/sink paragraph and task 7.1 still keyed on the bare global flag,
  preventing isolated canaries from exercising the launch boundary;
- universe-ID-only canary configuration could not pre-list generated public
  and first-contact birth IDs;
- the narrow exception accidentally changed three shipped non-BYOC source
  writes while dark; and
- the legacy-tool retirement obligation was unpublished and incorrectly
  framed as preserving a writer whose removal strictly reduces exposure.

The next adaptation:

- replaces every bare/global dark qualifier with the effective per-universe
  gate;
- adds a default-empty server-owned isolated test-principal bootstrap:
  preflight requires no existing home/universe, generated birth IDs register
  before target initialization/visibility, and later enforcement keys only on
  the registered ID;
- preserves self-hosted, market-rented, and host-daemon writes/readiness while
  dark, applying typed pre-mutation refusal only when effectively gated; and
- reframes and publishes retirement residuals: pre-slice unrestricted records
  remain task-8.1 migration work, while local surfaces need the host successor
  after the hidden action disappears.

Final disposition remains pending strict validation, four refreshed exact-head
handoffs, and Opus 5 approval.

## Eighth exact-revision Opus 5 re-review — 2026-07-25

Opus 5 reviewed clean commit `42ab3799` and approved the effective carrier
gate, generated-ID principal canary, dark non-BYOC compatibility, retirement
handoff, assignment-global wording, Q6.3 expansion, config-parse guard, and all
four exact-SHA comments. It returned `ADAPT` on the remaining
flag-independent legacy slice.

The deployed image has no Ollama service, so the proposed Anthropic
cloud-plus-local ceiling was role-member-complete but not reachable for
judge/extract. More importantly, PR #1592 already fail-closes credential
recovery for universe-scoped calls, while the process-global/no-universe path
that can inherit maintainer authentication remained outside the slice until
the full gate.

The final adaptation applies the simplification ladder:

- delete the flag-independent deprecated-action requirement and all
  compatibility implementation tasks rather than add a second kill switch,
  live-image reachability subsystem, and rollback path;
- preserve every shipped `set_engine` source/service/config/readiness and
  destination behavior while the effective gate is dark;
- state the true residual: universe-scoped credential access is fail-closed,
  but unchosen destination choice plus the ambient/no-universe maintainer-auth
  path remain until effective V2 enforcement; and
- bind exact owner/timing to gated R2-1a after the three ready-path successors,
  hidden-action retirement, and migration of every legacy
  `allowed_providers=None` record in task 8.1.

Final disposition remains pending strict validation, four refreshed exact-head
handoffs, and Opus 5 approval of the simplified target.

## Ninth exact-revision Opus 5 re-review — 2026-07-25

Opus 5 reviewed clean commit `27e4bfe2`. It approved deletion of the
flag-independent shortcut, exact ambient residual, effective gate, generated
ID canary, successor/retirement direction, global-default carve-out, registry
reaping, sandbox sync order, and all four handoffs. It returned `ADAPT` on two
remaining target-side gaps:

- a bare cloud singleton could be marked ready even though it empties
  canonical judge/extract/embed roles; and
- the shipped completion-based `_AUTH_PROBE_PROMPT` viability call was
  incorrectly grouped with zero-output host-local probes.

The adaptation requires role-complete readiness: every ready ceiling
intersects writer/judge/extract/embed and carries a current provider-specific
binding entry per destination. Anthropic/OpenAI custody alone persists its
cloud binding and writer preference but stays `held + []`; an atomic
cloud-plus-attested-requester-owned-local composition may become ready.
Maintainer local compute never supplies the role supplement, and cutover
exercises the live editorial judge and ingestion extract callers.

The host-local subscription probe is now non-completion credential inspection
only. `_AUTH_PROBE_PROMPT` is background maintenance and holds until
`harden-background-provider-execution-authority` supplies its exact bounded
receipt or a zero-output replacement lands.

Final disposition remains pending strict validation, four refreshed exact-head
handoffs, and Opus 5 approval.

## Parallel exact-42ab Opus 5 re-review — 2026-07-25

A separate Opus 5 invocation also reviewed clean commit `42ab3799`. It
confirmed strict validity and the four exact-head handoffs, then returned
`ADAPT` on three additional implementation-contract issues:

1. FastMCP 3.2 dispatches canonical synchronous tools through
   `anyio.to_thread.run_sync`. Requiring the current execution scope to equal
   only the middleware task would therefore hold every legitimate Tier-1
   provider call; accepting copied Context alone would instead recreate the
   detached-child authority defect.
2. Its local/development `set_engine` concern described the deleted
   flag-independent slice. Commit `352d1d44` already removed that slice, but
   the target now states explicitly that dark mode adds neither a production
   authentication requirement nor a development-mode auth requirement.
3. The closed host-local probe text incorrectly claimed that
   `subscription_auth_probe` performs no model call or spend, while canonical
   subscription health deliberately uses one bounded fixed private live
   viability completion.

The adaptation:

- adds a server-registered, non-serializable, one-shot
  `ProviderRequestDelegate` for the exact FastMCP synchronous handler
  invocation while its transport parent structurally awaits it, with
  worker/result/request revocation and detached/nested/copied-context refusal;
- preserves the simplified no-pre-cutover-write design and clarifies shipped
  production-auth versus development-mode dispatch behavior; and
- preserves the bounded host-operator subscription probe outside ordinary
  provider routing while forbidding requester prompt/quota, universe content,
  and user workload use.

The minor review asks are also folded into tasks: document the three V2
environment variables and require registered executable role coverage at
cutover rather than treating an absent local provider as ready.

Final disposition remains pending a fresh exact-head Opus 5 approval, strict
validation, and refreshed handoff evidence.

## Tenth exact-revision Opus 5 review — 2026-07-25

Opus 5 and an independent verifier reviewed exact pushed commit `c40409bd`.
They confirmed strict validity, dark-mode compatibility, and the factual
subscription-probe correction, but returned `ADAPT` after measuring the
installed FastMCP 3.2 stateful streamable-HTTP task topology:

1. The outer ASGI auth task awaits `transport.handle_request`; it does not
   structurally parent the per-message task or synchronous tool worker in the
   long-lived session task. An owner-ASGI-task lease therefore rejects every
   legitimate Tier-1 call.
2. Later stateful-session tool calls can inherit the initialize request's
   Context snapshot after that ASGI request's `finally` has already revoked
   it. Initialize/prior-message Context cannot be current request authority.
3. AnyIO selects the worker inside `to_thread.run_sync`; a contract that binds
   worker identity before submission has no implementable TinyAssets seam.
4. A completion-based auth-health probe remains a provider spend. The
   role-complete adaptation correctly moved it behind bounded background
   maintenance authority rather than leaving requester-triggerable host quota.

The measured adaptation keeps stateful HTTP and re-anchors authority to two
owned seams:

- TinyAssets FastMCP `Middleware.on_call_tool` re-derives bearer identity from
  the current HTTP message via `get_http_request()`, reserves a one-shot token
  bound to principal/session/request/tool, and structurally awaits
  `call_next`.
- The TinyAssets wrapper created by `_register_structured_tool` atomically
  claims that reserve on worker entry after AnyIO has selected the actual
  thread. Wrapper and message `finally` revoke before result release.

The outer ASGI task and initialize/prior-message Context are explicitly
non-authority. Copied reserves, second claims, detached/nested execution,
stale messages, and caller-supplied identities cannot claim the server lease.

Final disposition remains pending exact-head Opus 5 approval, strict
validation, and refreshed handoff evidence.

## Eleventh exact-revision Opus 5 review — 2026-07-25

Opus 5 reviewed exact commit `73d3f9d7`, including the message-dispatch and
role-complete adaptations. It verified the four exact handoffs, current
provider chains and ten BYOC services, zero-output sandbox probe, dark
compatibility, FastMCP one-shot delegation, advisory admission, canary
reaping, and absence of a Village/web dependency. It returned `ADAPT` on four
remaining boundaries:

1. requester-owned `ollama-local` needed its endpoint and executor-host
   identity to select transport, rather than the process-global maintainer
   instance;
2. readiness needed to cover roles with live call sites, not dormant `embed`,
   so Tier-1 and cloud-only Codex did not acquire a desktop prerequisite;
3. accepted-market setup needed target source `accepted_market` and a named
   successor-owned pre-routing B2/B13 remote-dispatch seam; and
4. `_AUTH_PROBE_PROMPT` needed a closed universe-less maintenance receipt
   bound to host/operator principal, exact operation, fixed private prompt,
   and bounded lifetime.

The adaptation derives local transport only from the attested requester
endpoint, inventories live roles at startup/CI, holds the first dormant-role
caller until covered, routes accepted-market `converse` outside ordinary
provider chains, and defines the maintenance receipt without universe, run,
branch, requester identity, requester quota, or requester content. Startup
canary reaping now requires provable universe absence; unreadable state holds
and preserves the entry. Residual BYOC services remain explicitly owned by
custody retirement, and the extract proof names
`tinyassets/ingestion/indexer.py`.

Final disposition remains pending strict validation, four refreshed
exact-head handoffs, and Opus 5 approval of task 1.30.

## Twelfth exact-revision Opus 5 review — 2026-07-25

Opus 5 measured the installed FastMCP 3.2 request helper against exact pushed
commit `87a553fe` and returned `ADAPT`: `get_http_request()` can fall back from
the per-message MCP request to an inherited `_current_http_request` or to a
synthetic request reconstructed from `_task_http_headers`. That fallback is
not current-message authority even when its bearer is valid. Task-augmented
calls can also run after middleware revocation and must not inherit request
authority.

The target now reads only
`mcp.server.lowlevel.server.request_ctx.get().request`, mints nothing when it
is absent, explicitly forbids both FastMCP fallback branches, and holds every
task-augmented/deferred call until the separate background owner issues a
durable receipt.

The earlier parallel-review wording about preserving a host-local live
subscription probe is superseded by the ninth and tenth normative adaptation:
completion-based `_AUTH_PROBE_PROMPT` is background maintenance and cannot use
`HostLocalProviderCapability`.

Final disposition remains pending current-main merge, strict validation,
refreshed exact-head handoffs, and a fresh Opus 5 approval.

## Post-twelfth independent and current-main review — 2026-07-25

An independent Codex reviewer found three remaining contract contradictions:
the proposal still said every tool call minted request authority, the design
still said every cloud-only binding held despite current Codex live-role
coverage, and accepted-market readiness had no legal assignment-state
encoding. A current-main merge audit also found two new composition duties:
main's anonymous wiki-canary authority must remain canary-only, and remote
HTTP provider binding must consume rather than duplicate the outbound
connection grant/credential-blind proxy.

The adaptation adds closed `remote_ready + []` state for a current
`accepted_market` B2/B13 grant, exact invalid-grant repair/renewal behavior,
non-deferred-only request minting, conditional cloud readiness, explicit
wiki-canary non-authority, and an outbound-ledger/proxy handoff. The market
path remains target-only behind its successor; no ordinary chain or runtime
activation is added here.

Final disposition remains pending merge to current main, strict validation,
refreshed exact-head handoffs, and fresh Opus 5 approval.
