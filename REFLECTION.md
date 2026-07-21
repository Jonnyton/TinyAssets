What surprised me: the deploy workflow already had nearly all facts needed for a release receipt; the gap was mostly that none of them were written into a machine-readable runtime artifact.

Pattern worth capturing: release observability should be deploy-published and status-read-only. That keeps `get_status` safe while still making live drift checkable by chatbots and local tools.

One thing I would do differently: start by adding the deploy workflow structure test before editing YAML, because this repo already has strong workflow-contract tests and they make the intended step ordering explicit.

---

What surprised me: merging the connector slice onto the broker world exposed privacy requirements beyond storage itself; rendered bindings could still escape through events, checkpoints, provider errors, and logs.

Pattern worth capturing: private runtime values need one ingress boundary and a complete egress audit. In-memory execution, recursive redaction, author-scoped lookup, and destination-resolved credentials form one invariant rather than separate fixes.

One thing I would do differently: run the binding concurrency and persistence scans immediately after establishing the canonical binding write path, before expanding the connector surface tests.

---

What surprised me: S4's isolated tests hid two integration contracts—the retired plaintext vault made every live client unusable, and a valid merge packet without universe storage crashed before it could fail closed.

Pattern worth capturing: credential integration is complete only when production factories consume rotating broker bindings and cross-slice contract probes exercise the same factories; static-token test helpers are not evidence of live wiring.

One thing I would do differently: add the broker-backed live-client and no-universe effector probes before resolving the larger merge, so those architectural mismatches become the first red tests.

---

What surprised me: replacing a synthetic concurrency proof with real branch orchestration exposed both an SQLite connection-order race and a migration test pointed at the wrong database filename.

Pattern worth capturing: load proofs should enter through the canonical orchestration boundary and assert exact persisted identities and effects; aggregate counts and hand-built rows can conceal integration gaps.

One thing I would do differently: make the first §14 test execute real bound runs and drain the real outbox, then audit whether every migration fixture targets the production path.

---

What surprised me: making terminal failures visible also needs durable ownership of the visibility event; idempotently annotating the run alone does not prevent duplicate daemon logs under concurrent drains.

Pattern worth capturing: bounded workers need one shared budget across primary execution and recovery scans, plus a storage compare-and-set for externally emitted terminal events.

One thing I would do differently: include concurrent recovery workers and more-than-one-batch terminal history in the first observability regressions, alongside the ordinary head-of-line fairness test.

---

What surprised me: a successful post-mutation head check still left a race because the reviewed generation was not carried into the durable work that ran afterward.

Pattern worth capturing: close remote-state TOCTOU at durable consumption boundaries. Bind the expected generation into every effect and task, then revalidate immediately before each downstream mutation or execution.

One thing I would do differently: model externally visible failure reporting as an at-least-once leased outbox from the start; a permanent acknowledgment cannot also serve as the pre-emission concurrency claim.

---

What surprised me: terminalizing a failed decision is only recoverable if replaying its leased failure report cannot erase the replacement decision.

Pattern worth capturing: generation failure and projection reopening must be one atomic first-transition operation; later failure-report deliveries are observability replays, not state transitions.

One thing I would do differently: include “recover, then replay the old terminal report” in the initial cap-out regression, alongside the ordinary `DecisionLocked` check.

---

What surprised me: deleting the compose workers was not sufficient; the
provider-auth keepalives, deployment credential seeding, and LLM-binding canary
still encoded platform compute as an uptime requirement.

Pattern worth capturing: compute ownership must be verified negatively at every
production boundary: service topology, credentials, health checks, alarms, and
orphan cleanup.

One thing I would do differently: begin with a repository-wide inventory of
executor credentials and executor-green alarms alongside the worker entrypoint
search, then write the absence contract before touching compose.

---

What surprised me: the retired cloud worker was both production machinery and
a test driver for surviving engine-binding invariants, so deleting the driver
silently deleted coverage that still belonged at the binding and launch seams.

Pattern worth capturing: when retiring an execution harness, classify every
test assertion by invariant owner and rewrite surviving contracts at their
lowest stable boundary. Also patch shared process state once outside concurrent
workers; overlapping thread-local mock contexts can restore out of order and
pollute an otherwise unrelated full suite.

One thing I would do differently: inventory deleted test names before accepting
the removal diff, then run mutation checks against the surviving boundary as
the first proof that replacement coverage is load-bearing.

---

What surprised me: isolating `APPDATA` protected TinyAssets fallback writes but
also moved Python's Windows user-site, breaking subprocess imports and DPAPI
tests that were unrelated to application storage.

Pattern worth capturing: test-root isolation must separate application data
resolution from interpreter and OS-profile resolution. Preserve
`PYTHONUSERBASE` when redirecting `APPDATA`, and compare full-suite failure node
sets rather than trusting aggregate counts.

One thing I would do differently: run one subprocess import probe immediately
after introducing a global environment fixture, before the first full suite.

---

What surprised me: the original "sealed" custody test exercised only friendly
attribute names, while Python's real reconstruction paths and mangled key
attributes remained reachable.

Pattern worth capturing: authority-wrapper tests need an explicit adversary
matrix. Prove the DML boundary, refuse cheap copy/pickle/subclass construction,
avoid exporting a module-level mint helper, and demonstrate rather than conceal
the arbitrary in-process Python boundary.

One thing I would do differently: enumerate signed fields and reconstruction
vectors from the gate repro before trusting either an aggregate field count or
a friendly public-API custody test.

---

What surprised me: closing provider dispatch at the graph boundary still left
an independently spawned live-auth probe, while the BYO scratch directory could
create the exact legacy-vault sentinel that later credential resolution rejects.

Pattern worth capturing: provider processes need a source-enforced spawn choke
with an explicit environment, and engine-owned runtime artifacts must live only
in namespaces that credential migration guards do not interpret as legacy state.

One thing I would do differently: begin each control-plane review with an AST
inventory of every process primitive under the provider package, then exercise
two consecutive bound calls before treating one successful BYO call as durable.

---

What surprised me: the lease fence itself was sound, but side effects and legacy
entry points around it still created independent authorities that the fence could
not protect.

Pattern worth capturing: single authority must be proved at every reachable
boundary. Put claim side effects after the winning CAS in its transaction, keep
validation above the sole fenced mutation primitive, and make retired routes fail
loud until their callers are fully migrated.

One thing I would do differently: start an authority review with a repository-wide
caller inventory and a cross-path race test, then inspect the transactional
ordering inside the surviving authority.

---

What surprised me: four rounds of receipt and event hardening could never
authenticate completion because a fresh-generation event remained insertable;
the missing primitive was verification of the signed lease and fence.

Pattern worth capturing: decide trust at the narrowest durable boundary. Resolve
the verification key from platform-owned state, authenticate the stored body at
completion, and retain receipt/event guards only for consistency properties that
a signature does not provide.

One thing I would do differently: begin by enumerating each actor's exact write
capabilities and mutate one guard per property before adding any corroborating
count, index, or receipt layer.

---

What surprised me: signing the enrolled key identifier at grant time closed the
reported row selector, but a hostile registry-row substitution could still
replace the verifier unless the public key bytes were signed too.

Pattern worth capturing: a cryptographic assignment grant should bind both the
logical identity and the verification material. Mutable registries may revoke
or advance epochs, but they must not select the key used to authenticate the
assigned generation.

One thing I would do differently: include two-real-key and registry-remap
mutations in the first trust-root test matrix, before treating an authenticated
identifier lookup as equivalent to a signed verification key.

---

What surprised me: binding the device key and lease generation still left a
policy-oracle gap because a legitimately granted device could sign whichever
execution policy mutable result metadata told completion to expect.

Pattern worth capturing: enumerate every positive acceptance input before
designing the signature envelope. Identity, generation, policy, and content
selectors need one explicit provenance map; reject-only durability checks must
be labeled separately so mutable evidence never quietly becomes authority.

One thing I would do differently: start the adversarial matrix with one
independent mutation per selector plus an all-selectors forge, then require the
grant schema and issuer/verifier types to make the trust boundary visible in
code rather than relying on deployment discipline.

---

What surprised me: removing event reads was insufficient by itself. A forged
one-shot audit row could still make the store's later audit insert violate a
unique index and roll back an otherwise valid signed/CAS transition.

Pattern worth capturing: an audit-only channel must be non-authoritative in
both directions. Its contents cannot prove acceptance, and attacker-authored
duplicates cannot veto a transition whose cryptographic and CAS checks pass.

One thing I would do differently: test every audit surface twice—once as a
forged positive proof and once as a preinserted negative veto—when drawing the
initial authority map.

---

What surprised me: the positive signed-replay test initially obscured the
original fix-9 attack. A genuine reset row with an attestation must replay, while
the same mutable projection without that artifact must fail closed.

Pattern worth capturing: authority regression tests need paired mutation
probes—one proving that mutable state cannot mint authority and one proving that
an immutable signed artifact still works when its mutable projection is reset.

One thing I would do differently: reproduce each gate forge verbatim before
adding the intended success path, then keep both tests adjacent so the security
boundary cannot be weakened by an apparently reasonable replay assertion.

---

What surprised me: the first real run-to-job attempt exposed that ordinary run
IDs are 16 hex characters while the B2 protocol requires canonical UUID job
IDs; isolated lease tests had hidden the seam completely.

Pattern worth capturing: an authority subsystem is not proven by component
tests until one normal producer-created record crosses every signed and durable
boundary through terminal replay.

One thing I would do differently: start hardening with one thin normal-producer
end-to-end test, then attack the authority boundary that test actually reaches.

---

What surprised me: several old tests treated attacker-inserted high-fence audit
events as harmless noise, but the approved monotonic-floor design intentionally
turns that exact mutation into a fail-closed denial. The conflict surfaced only
when the complete focused suite ran after the isolated RED/GREEN loops.

Pattern worth capturing: mutation proof is strongest when each security test
targets one missing guard and the final suite separately checks changed
invariants against older expectations. Signed-field accounting must also live
in an immutable domain registry, not merely move from a method argument to a
constructor argument that another caller could still neutralize.

One thing I would do differently: enumerate tests that deliberately inject
higher generations before implementing a monotonic floor, and reject any
"immutable" contract design that still exposes a caller-supplied construction
seam during the first API sketch.
