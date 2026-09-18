# Model connection clarity: shape review and live diagnosis

September16,2026. Fable5.1 independent read-only review, source6aea3f4e
(runtime shipped in7a802644). Exact local review session
9b0048d8-4f88-40ae-821a-e8cbadb69fdd. Completed exit0 in445s.
The old dispatch wrapper captured only a stop-hook recap; recovered the initial
assistant review from that same session, not a replacement dispatch.

## Review disposition (summary of recovered review)

- AGREE: custody renewal must make a newly deposited credential eligible; the
  health key includes generation/digest. This is not evidence of authentication.
- DISAGREE_EVIDENCE: stale snapshot hypothesis. Each launch reads current vault
  material and verifies custody digest; no Claude token memoization exists.
- DISAGREE_EVIDENCE: ambient endpoint hypothesis. Child env is allowlisted and
  snapshot auth uses the exact token. Project settings remain a hypothesis only.
- DISAGREE_CONCERN: typed authentication failure does not prove token revocation.
  Canonical llm_deposit accepts arbitrary nonempty UTF8; base.py interprets a
  non-sk-ant value as credential-directory material, leaving the child without
  a usable token. No cause was established from code alone.
- AGREE: prominent next/current control, selectable models separate from full
  unavailable inventory, explicit tab-local versus durable selection labels.
- ADAPT: global discovery still blocks both picker and execution; row-local
  freshness/server-side split merits its own bounded change.

Verdict on proposed UI shape: ADAPT, not implementation approval.

## Lead verification and bounded implementation

Read-only live metadata02:07UTC: owner replacement was stored01:56:28UTC,
Claude custody generation2. Only shape booleans emitted: no sk-ant prefix,
contains #, shorter than128characters, no whitespace/JSON/base64 token wrapper.
Consistent with browser authorization code, not final setup-token. No credential
value, digest, owner identity or auth path emitted. This establishes malformed
replacement, not the original correctly-shaped credential's failure cause.

Rendered original-owner history:18:58Automatic/Claude failed;18:59Automatic/Codex
replied. Operator19:00explicit Claude greeting failed19:01. Operator restored
saved default, then owner19:02resend answered Codex. Scoped read-only journal
corroborates current vs Automatic choices and different providers. No automatic
whole-turn replay is added, and no private workflow is edited.

Patch: canonical deposit rejects non-token shapes before mutation; instructions
distinguish browser code from terminal token; success says credential saved, not
provider verified. Picker promotes control, trims unavailable dropdown entries
without removing their inventory, closes on applied choice, distinguishes tab
choice/default, clears old tab override only after a confirmed default save.
Still-fresh snapshots are reused when reopening; expiry and failed refresh remain
strict. Row-local admission/server discovery splitting is deliberately deferred:
this patch does not claim first-open latency fixed or weaken freshness gates.

Rollback: revert this code-only patch through normal reviewed deployment if
selection/deposit regresses. No schema migration, stored credential rewrite,
grant/default migration, or private workflow mutation to reverse. Deployment
and rendered acceptance remain required; this document is not live success.
