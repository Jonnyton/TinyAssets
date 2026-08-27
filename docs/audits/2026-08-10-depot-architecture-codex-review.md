# Depot Architecture Research — Opposite-Provider Review

**Date:** 2026-08-10  
**Reviewer:** Codex (opposite-provider review of Claude-authored note)  
**Reviewed note:** `docs/design-notes/2026-08-10-arch-research-depot.md`  
**TinyAssets baseline:** `origin/main` at `7b451b2c98abb9b411d35b32def96a319d721594`  
**Overall verdict:** ADAPT

The note identifies useful patterns, but its deploy recommendation is unsafe as
written, its vault diagnosis is stale relative to current main, and a few Depot
claims overreach their evidence.

## 1. Fact review — ADAPT

| Claim | Verdict | Review |
|---|---|---|
| Cloud Hypervisor microVMs, JIT, no warm pool, about 0.6 s P50 | Approve with scope | Depot explicitly reports Cloud Hypervisor/KVM, on-demand scheduling without pre-warming, and 0.6 s P50 microVM boot. That is platform boot evidence, not an end-to-end Claude-agent launch SLO. |
| Immutable, lazily chunk-served root images | Adapt | OCI-backed root disks/snapshots and on-demand missing-chunk reads are explicit. Immutability of each active root disk is not: Depot also describes read/write caching. “Immutable deploy unit” is an inference, not a reported property. |
| Bare-metal fleet | Approve with wording | Depot says its CI and Sandboxes run on Metal, implemented with AWS EC2 bare-metal instances. Do not imply Depot owns a physical-datacenter fleet. |
| Genuine Claude Code CLI wrapper | Approve | The first release executed the installed `claude` binary and synchronized Claude's JSONL session state; the current CLI passes unrecognized flags through to Claude Code. |
| Org-scoped, write-only agent secrets injected as environment variables | Adapt | Organization scope, setup-token/API-key creation, environment injection, and non-display of values are documented. KMS envelope encryption, log masking, write-only management, and scoped variants are documented for Depot CI secrets; the note must not silently attribute that implementation to the agent-secret store. |
| $0.01/minute run-only metering | Approve | Depot documents per-second accounting at $0.01/minute while the agent is actively processing, with no minimum. This does not establish total storage or support cost. |
| Dashboard list/resume/fork | Adapt | Dashboard list, start, resume, full conversation, and sandbox execution history are documented. Fork is documented through the CLI, not the dashboard. |
| V1 was a `$HOME/.claude` session-sync daemon | Approve | The genealogy is explicit: watch the Claude JSONL file, upload it, restore it, then invoke Claude Code resume. |
| Containers were rejected | Approve with scope | Depot says its Sandbox SDK prototype outgrew containers because it needed machine-like behavior, Docker, nested virtualization, and a full syscall surface. That is not evidence that every TinyAssets workload needs a microVM, nor proof of the historical reason for every remote-agent product change. |

Primary sources: [microVM boot](https://depot.dev/blog/optimizing-microvm-boot-times),
[Depot Metal](https://depot.dev/blog/announcing-depot-metal),
[Sandbox SDK](https://depot.dev/blog/now-available-the-depot-sandbox-sdk),
[remote agent launch](https://depot.dev/blog/now-available-remote-agent-sandboxes),
[V1 sessions](https://depot.dev/blog/now-available-claude-code-sessions-in-depot),
[Claude Code quickstart](https://depot.dev/docs/agents/claude-code/quickstart),
[agent CLI reference](https://depot.dev/docs/cli/reference/agents), and
[Depot security](https://depot.dev/docs/security).

## 2. TinyAssets implications

### 2a. Vault mechanics — ADAPT

Adopt management-plane non-display/write-only-after-creation, redaction, trusted
scope selection, and fail-closed resolution. Adapt the proposal because current
main already builds explicit-universe provider environments from an empty base
and fails closed on missing or invalid credentials. R2-1 should close the
remaining host-local/unthreaded authority and legacy engine-ceiling paths, not
rebuild the landed universe isolation.

Do not make the internal provider resolver “write-only”; a runtime must retrieve
the secret. More importantly, the proposal omits Depot CI's strongest lesson:
TinyAssets still needs at-rest envelope encryption and key separation before
customer token custody. Map variants to trusted TinyAssets dimensions such as
provider account, universe, actor/agent binding, role, operation, destination,
and purpose—not blindly to CI branch/workflow selectors.

### 2b. Prove-new-before-stop-old deploy — REJECT AS WRITTEN; ADAPT THE GOAL

A fully active candidate cannot safely start against the current shared writable
`/data` volume before the old stack is fenced. The issue is broader than SQLite
locking: old and new schedulers, workers, queue claimers, migrations, and
side-effecting startup code could overlap; the current exact-five/empty-inventory
fence explicitly proves the old receipt-writing population is gone. Fixed names
and the public port also prevent a second canonical Compose stack.

Shared SQLite is not a categorical one-writer constraint—the current canonical
containers already coordinate multiple writers. The missing primitive is
single-active-writer/side-effect authority across *versions*.

Two safe directions exist:

1. Start a side-effect-disabled candidate on an alternate port with no production
   volume, a read-only volume, or a consistent snapshot; run boot/health/load
   checks; then stop/fence old and start the canonical writer. This shortens the
   outage but cannot prove live-write activation before cutover.
2. For a genuinely zero-gap cutover, add an explicit leader lease/fencing token,
   rolling-compatible schemas, deferred migrations, and traffic handoff. The
   candidate may observe production before cutover but cannot obtain write or
   external-side-effect authority until old has surrendered it.

Per-universe isolation would reduce blast radius and make rolling replacement
easier, but it is not a logical prerequisite. A designed active/standby authority
protocol is the prerequisite for same-volume overlap. The current mechanism
must not be changed to “start active new, then fence old.”

Also correct the note's framing: current deploys already use immutable digest
image references and include bounded automatic rollback; they do not mutate a
container root filesystem in place.

### 2c. Sessions as first-class objects — ADAPT

Approve the concept, but do not equate a conversation fork with a public remix.
`conversation_store` is a turn ledger, while current main also has first-class
owner-scoped authoring sessions and a private conversation-custody model. Add a
session aggregate that references turns, runs, artifacts, custody threads,
universe/owner, status, budget, retention, and lineage. Reuse authoring-session
identity and isolation conventions.

Define three separate operations: private conversational branch, authoring
remix/version lineage, and execution rerun. A private transcript must not become
commons lineage or be copied across authority boundaries implicitly.

## 3. Module-table review — ADAPT

- **Vault:** “fails open into host credentials” is stale as a blanket statement.
  Explicit-universe provider calls now use isolated environments and fail closed;
  host-local/unthreaded and legacy ceiling paths remain concerns.
- **Sessions:** `conversation_store` landed on current main with record/load/sync
  primitives, and authoring sessions already support owner-scoped list/inspect/
  resume lineage. Conversation browsing and conversation-level fork are absent.
- **Deploy:** “mutate in place” is inaccurate. Images are digest-pinned; the host
  Compose/config lifecycle is replaced in place after an exact-five drain/fence.
- **Depot MCP:** “no MCP servers inside sandboxes” is false. Depot's remote-agent
  launch explicitly supports user-specified MCP servers through Claude CLI flags
  and config. Depot's *control plane* is CLI/web/API rather than MCP-native.
- **Async-only:** stale/imprecise because the CLI has a wait mode, although Depot
  still lacks an interactive mid-turn remote terminal/chat surface.
- **Engine sandbox:** TinyAssets has a fail-closed execution-admission seam and an
  unavailable backend, but no active OS isolation backend. Calling it merely a
  denylist misses that landed structure.
- **Provider fleet wedge:** the exact `compatible_worker_count=0` failure cited by
  the older audit should not be presented as current without a fresh production
  reproduction; later main changes hardened runtime authority/lifecycle.

## 4. Organization-pooled OAuth caveat — APPROVE, STRENGTHEN

Depot's continued operation is observational evidence, not contractual clearance
for subscription pooling. Current Anthropic guidance treats plan usage as belonging
to the subscriber and states that third-party Agent SDK credits are per-user and
must not be pooled across teammates.

Depot docs prove an organization-scoped secret namespace, not that multiple people
actually share one OAuth subscription. Therefore “one token per organization” is
too categorical. TinyAssets' per-universe authority binding and aggregate budget
per underlying provider account are complementary: the former prevents authority
bleed, while the latter prevents one account's limits from being multiplied by
creating universes.

Sources: [Anthropic account-login policy](https://support.claude.com/en/articles/13189465-log-in-to-your-claude-account),
[Agent SDK plan-credit policy](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan), and
[Claude Code plan guidance](https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan).

## 5. Material omissions

1. **Vault cryptography and operator blindness:** envelope encryption, a key
   hierarchy, rotation/revocation, and audit semantics are prerequisites for
   customer-token intake.
2. **Side-effect-safe candidate mode:** HTTP health is insufficient; a candidate
   must not migrate schemas, claim queues, schedule work, or contact external
   systems before it owns the writer lease.
3. **Session privacy lifecycle:** retention, deletion/export, consent, pagination,
   ownership transfer, and private-transcript/public-remix boundaries need specs.
4. **Provider session files are adapters, not a portable core contract:** copying
   `$HOME/.claude` is provider-specific, unstable, and potentially sensitive.
5. **MCP distinction:** Depot supports MCP inside Claude sandboxes even though its
   own orchestration surface is not MCP-native.
6. **Rented-sandbox custody:** data region, egress policy, source/transcript
   retention, secret delivery, auditability, and attestation need explicit gates.
7. **Isolation-envelope fit:** Depot needed Docker/nested-VM/full-syscall support;
   that does not prove a microVM is necessary for every TinyAssets inference task.
8. **Shared-state recovery:** backups, snapshot consistency, schema compatibility,
   and per-universe blast-radius reduction matter as much as launch latency.
9. **Economics:** active-minute price alone is not a durability or unit-economics
   model; idle storage, snapshots, egress, transcripts, and support remain.
10. **Documentation conflict:** Depot's current Metal announcement says all
    Sandboxes run on Metal while older agent docs still say “container”; the note
    should label this terminology/freshness conflict explicitly.

DEPOT_VERDICT: ADAPT
