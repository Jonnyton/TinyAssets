# Design — foreground run provider authority

Cross-family review: Codex, 2026-08-26 (ADAPT before the first build). Ownership
transferred to Patches on 2026-09-03 after bound-agent live proof still failed.
The follow-up implementation requires a fresh opposite-family review before
landing, or the documented hard-provider-limit independent-review fallback in
`docs/reference/quality-gates.md` when that provider is unavailable.

## The primitive
A user-authorized run must NOT carry a served request capability. A request capability represents
one live ingress turn: it is revoked when the MCP request completes while the run executes
asynchronously, it is bound to a serving-agent binding authorizing only `converse`/`writer`, it
carries a two-invocation limit incompatible with an N-call graph, and forwarding it would let the
authoring agent convert conversational authority into recursive execution authority.

Instead: **admission freezes the run subject without requiring provider authority. On the first
actual provider attempt, the executor mints the durable, server-owned run authority, then one
pid-bound, one-use `ProviderInvocationCarrier` per provider attempt.** A run that never attempts a
provider call creates no run receipt and retains its previous provider-free behavior.

## Binding (all exact; any mismatch fails closed)
Authenticated principal + actor; exact universe; exact `run_id`; exact branch definition plus
immutable version/snapshot digest; the ACTIVE serving assignment and its owner, provider, assignment
generation/digest; serving binding id/generation/digest/revocation generation; exact
credential-reference digest; operation `run_graph` and permitted roles; aggregate
invocation/token/cost ceilings no wider than the serving binding. Prefer a run-class CHILD work
binding derived from the ACTIVE serving binding — never treat the long-lived serving binding itself
as launch authority.

## Expiry
Earliest of: run deadline, claim lease, run cancellation/terminalization, serving-binding expiry.
Rotation, revocation, credential change or assignment-generation change stops all further launches.

## Provider kinds
The ACTIVE serving assignment is authoritative for both subscription-backed
and registered open providers. A subscription provider receives only a sealed,
run-scoped credential snapshot. An open provider receives no subscription
snapshot; its existing connection-grant custody is revalidated and the router
fresh-resolves the content-addressed provider definition instead of trusting a
same-name object in its mutable registry, then uses the credential-blind
outbound proxy. A fresh-resolution refusal settles the armed reservation as
cancelled before launch. Both kinds use the same run receipt, claim, one-use
invocation carrier, budget reservation, exact provider fence, and settlement
path. Open registration alone is never enough: the provider must be the current
serving assignment for this owner and universe.

## N provider calls
Mint N distinct pid-bound one-use carriers — one per actual provider ATTEMPT, not one per run and
not one per node. Each reservation carries a unique run/call ordinal and prompt/attempt identity;
parallel calls reserve independently.

## Budget lifecycle
Reserve invocations/max-tokens/max-cost transactionally → arm and mint immediately before launch →
success persists actual input/output tokens and cost and releases the unused reservation. Definitive
pre-launch refusal → `cancelled_before_launch`. Confirmed provider failure → `failed` with known
actuals. Timeout/crash after possible dispatch → `indeterminate`, conservatively charged until
reconciliation. Terminal run → release the claim and cancel still-unarmed reservations.

**Do not copy the background lane unchanged:** its one-use carrier is sound for provenance, but its
durable actual-usage settlement is still unfinished (the strict xfail in
`tests/test_background_budget_finalization_e2e.py`). This lane needs generic reservation settlement.

## Refuse (each one is an escalation, not a shortcut)
- Restoring caller-populated `served_provider`, an in-process registry, sentinel, secret or
  "trusted dataclass" fallback.
- Minting or forwarding a `ProviderRequestCarrier` for `run_graph`.
- Treating "actor is founder" or universe WRITE access as compute-launch authority.
- Letting the authoring agent supply a carrier, binding, credential reference, provider, budget,
  principal or run identity.
- Reusing one carrier across a run.
- Letting `llm_policy` widen beyond the ACTIVE serving provider or fall through to another
  enrolled/ambient provider.
- Rejecting an ACTIVE, owner-authorized registered open provider merely because
  it is not a subscription provider.
- Treating provider registration, the X credential or outbound consent as LLM authority.
- Giving the X credential to the LLM subprocess, or combining compute and effect authority.
- Special-casing the founder's universe/run ids, posting from the control plane, or rewriting the
  branch as effect-only to dodge the broken LLM path.
- Auto-retrying an X POST after an indeterminate external result.

## First slice admission
Own-universe branch authored by the authenticated principal only.
This restriction is evaluated lazily when the run first attempts provider execution; it is not a
precondition for provider-free execution.
