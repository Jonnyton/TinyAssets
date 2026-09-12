# One authorized workflow model-authority correction review

Review the platform model-selection correction at local0325b840. The owner
explicitly authorized ONE additional independent review after the release
feature reached its three-review limit and real workflow integration failures
were discovered. This consumes that exception; it is not permission to dispatch
more reviewers or to review the owner's background-self project. No user
workflow, default, grant, credential or project may be changed.

HARD CONSTRAINTS ON HOW YOU WORK:
- Do NOT dispatch sub-agents. No peer_agent.py, claude/codex subprocess or new
  worktree. Review it yourself, read-only. Do not edit or commit anything.
- Do NOT run the full suite or CI helpers. Source reasoning is sufficient;
  no tests are required for this shape review.
- Budget roughly ten minutes. Focus on the exact cited seams, not a whole-repo
  audit or unrelated hardening. No provider/API/production calls.

Required user capability: independently select the provider/model for a main
agent and for individual agents, workflows or tasks, including mixed-provider
parallel workflow nodes. Provider defaults remain defaults; explicit pins and
an explicitly empty fallback list must survive. A user's authorized alternative
must not depend on an unrelated anchor credential. Nothing grants new access
merely because a provider is installed, discovered, preferred or named in JSON.

Read openspec/changes/select-agent-models/workflow-selection-correction.md,
authority-seam.md and connection-model-authority.md for the existing accepted
shape and newer unresolved correction. Then inspect:
- tinyassets/provider_work_authority.py: ProviderWorkBinding,
  ProviderUniverseWorkReceipt (versions1-3), ProviderInvocationReservation
  (versions1-2), ProviderInvocationCarrier and its store-minted one-use seal.
- tinyassets/storage/provider_work_authority.py: schema, receipt issuance,
  claim/reserve/arm/settle, run and background carrier helpers.
- tinyassets/foreground_run_provider.py: _admit, _validate_receipt_parent,
  _authorize_attempt and _call; tinyassets/background_served_provider.py:
  _authorize_launch and its provider-call wrapper.
- tinyassets/provider_serving_binding.py: legacy-only authority guard,
  current selected-member validator, bind publication and inventory correction.
- tinyassets/providers/model_selection.py, served_model_plan.py and router.py:
  selected model validation, source policy, config clearing and carrier use.
- tests/test_run_provider_session.py: the two actual manifest bind/enable/run
  expected-success failures; inventory tests now pass. These are synthetic
  platform tests, not changes to the owner's project.

Current evidence:0325b840's focused scheduler inventory5pass; expanded real
foreground/consumer/background50pass/2fail on WindowsPython3.14, zero skips.
Both failures occur on native-manifest foreground launch. Linux not yet run
for this correction. Existing remote PR3832 is draft and must not deploy.

Review the necessary correction shape, not whether to erase the guard:
1. Keep ONE aggregate work budget/immutable subject/claim across every provider
   and retry. No multiplied per-node/source receipts or invented work IDs.
2. Reuse the existing assignment manifest/current-member/custody validators,
   shared source/model policy and provider execution contracts. Snapshot
   discovery outside locks and revalidate exact authority before launch.
3. Persist/seal exact selected provider, model/executor, accepted-member fence,
   custody, role/operation and model/cost evidence per reserved invocation;
   settlement and crash recovery stay bound to that exact attempt.
4. Retain legacy record parsing and semantics. A new representation must not
   disguise a manifest digest as a credential, use a fictional provider, or
   keep depending on anchor custody merely to satisfy old fields.

Return an implementation-ready decision on the smallest honest representation
in the existing stores: exact record versions/fields, whether a work binding
must gain a separate aggregate-authority variant, required SQL migration (or
why none), and how legacy readers fail closed. Contrast a structural-anchor
receipt plus per-attempt member facts against a typed aggregate work authority;
reject any option that hides provider dependence or copies authorization logic.
Explain transaction/lock ordering, budget arithmetic (aggregate AND member
limits), replay/settlement/revocation handling, and the minimal end-to-end tests.
Identify which existing reviewed seams can be reused unchanged and which changes
genuinely need new authority semantics. Do not broaden this into tool mounting,
the user's background self, generic app UI or unrelated native discovery work.

Give structured disagreements: AGREE / DISAGREE_EVIDENCE with source citations /
DISAGREE_CONCERN. Separate pre-build blockers from later nonblocking concerns.
State explicitly whether the correction design is ready to implement and what
this review does NOT prove; no approval of unimplemented code. End with exactly
one line: VERDICT: APPROVE|ADAPT|REJECT.
