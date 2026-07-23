<!--
PROVENANCE — this document was NOT authored in this PR.

  Source path      : output/s2-gate/auth-surface-sweep.md  (gitignored; .gitignore:70 `output/`)
  Produced by      : an s2-gate lane, dispatched READ-ONLY, on 2026-07-22
  Audited tree     : origin/main @ 220a1fc8c69d3ae07b7673494e30d1267a220f69 (2026-07-22 01:21:46 +0000)
  Carried by       : claude-code-fleet, 2026-07-22, branch claude/carry-auth-surface-sweep
  Carried at       : origin/main @ 0bc841aade74fdf987b156d7898fc2da7fdddd8a

Everything below the "Carried document" rule is byte-identical to the source
file. This header and the freshness stamp above that rule are the only
additions; no line of the audit body was edited, reordered, or removed.

The lane was instructed READ-ONLY and correctly did not create this file
itself (it says so in its own first paragraph). Nothing carried the result,
so a completed security audit sat in a gitignored directory, invisible to
git, to every other provider session, and to any future checkout.
-->

**Carried, not authored.** This is a completed 345-line auth audit that an
s2-gate lane finished on 2026-07-22 and left in `output/s2-gate/`, which is
gitignored. It is reproduced verbatim below. The freshness stamp is the
carrier's; every finding, claim, and line reference is the original lane's.

## Carrier provenance

| | |
|---|---|
| Source | `output/s2-gate/auth-surface-sweep.md` (untracked — `.gitignore:70` `output/`) |
| Audited sha | `220a1fc8c69d3ae07b7673494e30d1267a220f69` |
| Carried at sha | `0bc841aade74fdf987b156d7898fc2da7fdddd8a` |
| Live deployed sha | `0bc841aa…` — `get_status` → `release_state.git_sha`, deployed `2026-07-22T05:33:56Z` |
| Verdict | **Reject current auth posture for unattended auto-deploy** |
| Body edits | none (byte-identical; verified with `cmp`) |

## Freshness stamp — 2026-07-22, by the carrying lane

Per `AGENTS.md` § *Truth And Freshness*, an audit is stamped before its
prescriptions are dispatched. This is a **carry-and-stamp, not a re-audit**:
the checks below confirm the cited code still reads as the audit describes.
They do not independently re-derive the findings, and they are not a second
opinion on severity.

**Structural check.** `git diff --name-only 220a1fc8..0bc841aa` returns exactly
three paths — `.agents/activity.log`, `AGENTS.md`, `STATUS.md`. No file under
`tinyassets/`, `deploy/`, or `.github/workflows/` changed between the audited
tree and the carried tree, so every line reference in the body still resolves.

**Deployment check.** The live connector's `get_status` reports
`release_state.git_sha = 0bc841aade74fdf987b156d7898fc2da7fdddd8a`, deployed
`2026-07-22T05:33:56Z`. The audited code is therefore what production is
serving right now, in every auth-relevant path.

| # | Finding | Class | Evidence at `0bc841aa` |
|---|---|---|---|
| 1 | Critical — `run_graph` drops universe credential context | `current:` | `tinyassets/api/runs.py` contains no `UniverseContext` reference at all (`grep -n UniverseContext` → no match), while `tinyassets/universe_intelligence.py:430` still constructs `UniverseContext(universe_dir=udir, config=…)`. The asymmetry the finding rests on is intact. |
| 2 | High — "private" Goals anonymously readable | `current:` | `tinyassets/api/market.py:1151` still accepts and stores `visibility ∈ {public, private}`; the list handler at `1377-1416` contains no `visibility`/`private` token; `daemon_server.get_goal` selects `WHERE goal_id = ?` with no visibility predicate. |
| 6 | Medium/conditional — `_current_actor()` is an authorization input | `current:` | `tinyassets/api/engine_helpers.py` `_current_actor()` still ends `return os.environ.get("UNIVERSE_SERVER_USER", "anonymous")`. Independently corroborated by the standing STATUS Concern row citing `engine_helpers.py:192`. |
| 7 | Low — anonymous `read_page` creates durable universe state | `current:` | `tinyassets/api/permissions.py:59-89` `universe_public_read_allowed` still documents "a *missing* rules row means … publicly readable by default"; `tinyassets/api/wiki.py` still calls `_ensure_wiki_scaffold(wiki_root)` after the ACL gate, on every action including reads. |
| — | § Scope and freshness: "Live release receipt SHA: `1605349e…`" | `contradicted:` | Superseded. Live sha is now `0bc841aa…`. This makes the audit **stronger**, not weaker: at audit time the deployed receipt lagged `main` and the lane had to argue the findings still applied; they now apply to the deployed sha directly. |
| — | § Scope and freshness: remaining live-probe lines (anonymous `write_graph` 401, advertised tool list, hidden-`extensions` ToolError) | `unknown:` | Not re-probed by the carrying lane. No exploit or mutating call was made in carrying this document either. |

Findings 3, 4, 5, 8, and 9 were **not** spot-checked. The structural check
above covers them (their files did not change), but no one re-read their cited
lines on 2026-07-22.

---

## Carried document

Audit complete against remote-verified `origin/main` (`220a1fc8c69d3ae07b7673494e30d1267a220f69`). I found one critical host-credential identity leak, two high-severity authorization defects, and several conditional/classification defects.

Per your READ-ONLY instruction, I did not create `docs/audits/2026-07-22-auth-surface-sweep.md`. The following is the ready-to-save document.

---

# Auth surface sweep — 2026-07-22

## Verdict

**Reject current auth posture for unattended auto-deploy.**

The canonical authenticated `run_graph` path loses its universe credential context before provider dispatch. Consequently, a founder’s universe runs using the daemon host’s ambient Codex/Claude subscription credentials instead of failing closed or using that universe’s vault. This is directly reachable through the public MCP endpoint.

The audit also found:

- Goals accepted and stored as `visibility="private"` are anonymously readable.
- Gate-event authority can be forged with caller-supplied actor strings.
- Scheduler ownership is caller-supplied and later trusted from mutable DB rows.
- Request handlers inherit process-global capabilities.
- `_current_actor()` is not attribution-only.
- Several read-classified actions perform durable writes or LLM executions.

## Scope and freshness

Audited tree:

- `origin/main`: `220a1fc8c69d3ae07b7673494e30d1267a220f69`
- Commit time: `2026-07-22 01:21:46 +0000`
- Remote verification: `git ls-remote origin refs/heads/main` matched local `origin/main`.

Live probe of the canonical public endpoint identified by the [TinyAssets site](https://tinyassets.io/):

- Anonymous MCP initialization: HTTP 200.
- Advertised tools: `read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`, `converse`, `get_status`.
- Anonymous `write_graph`: HTTP 401 with OAuth challenge; it did not dispatch.
- Anonymous hidden `extensions` read: MCP ToolError; it did not dispatch.
- Live release receipt SHA: `1605349e888c918dc9ef8fd1452cb40d83a5dc51`.
- No auth/API/provider/runtime files differed between that live SHA and audited `origin/main`, so the findings below apply to the currently deployed auth-relevant code despite the overall release receipt lagging main.
- Live status reported `paid_market_flag_on=false`, host Codex and Claude subscription authentication present, `active_host.host_id="host"`, and the anonymous account actor as `"anonymous"`.

No authenticated exploit calls or potentially mutating successful calls were made.

## Findings ranked by public reachability

| Rank | Severity | Finding | Public reachability |
|---|---|---|---|
| 1 | Critical | `run_graph` drops universe credential context and uses host subscription credentials | Canonical public tool; authenticated |
| 2 | High | “Private” Goals are anonymously readable | Canonical public read; anonymous |
| 3 | High | Gate-event identities and verification authority are caller-supplied | Hidden legacy tool; authenticated |
| 4 | Medium | Scheduler ownership is caller-supplied and trusted from mutable DB rows | Hidden legacy tool; authenticated |
| 5 | Medium, conditional | Every request inherits `UNIVERSE_SERVER_CAPABILITIES` | Hidden legacy tools; authenticated |
| 6 | Medium, conditional | `_current_actor()` env fallback participates in private-branch authorization | Canonical public read; anonymous |
| 7 | Low | `read_page` can create an arbitrary universe wiki scaffold | Canonical public read; anonymous |
| 8 | Medium classification defect | Read-classified extension actions execute LLMs or write ledgers | Hidden legacy tool; authenticated |
| 9 | Latent | Paid-market escrow derives authority through `_current_actor()` | Flag off in live deployment |

## 1. Critical — universe runs fall back to host subscription credentials

### Evidence

The canonical tool forwards the selected universe:

- `origin/main:tinyassets/universe_server.py:646-668`

`_action_run_branch` uses the universe only for ACL/actor derivation, then imports the bare global provider call:

- `origin/main:tinyassets/api/runs.py:529-646`
- `origin/main:tinyassets/api/runs.py:675-686`

It does not construct or pass `UniverseContext`.

The async run core and graph compiler also carry no universe credential context into provider execution:

- `origin/main:tinyassets/runs.py:2104-2250`
- `origin/main:tinyassets/runs.py:2961-3047`
- `origin/main:tinyassets/graph_compiler.py:228-249`
- `origin/main:tinyassets/graph_compiler.py:1180-1208`

By contrast, the correctly scoped `converse` implementation explicitly constructs and passes `UniverseContext`:

- `origin/main:tinyassets/universe_intelligence.py:415-445`

Provider authentication uses a universe vault only when `universe_dir` is supplied. With `None`, the existing subprocess environment remains in force:

- `origin/main:tinyassets/providers/base.py:143-162`
- `origin/main:tinyassets/credential_vault.py:241-260`
- `origin/main:tinyassets/credential_vault.py:396-455`

Production supplies process-global host credentials:

- `CODEX_HOME=/data/.codex`
- `CLAUDE_CONFIG_DIR=/data/.claude`

See `origin/main:deploy/compose.yml:47-55`. The live status probe confirmed both host subscription routes are authenticated.

### Failure scenario

1. Alice authenticates through WorkOS and owns universe `u-alice`.
2. Alice calls `run_graph(branch_def_id="b", graph_id="u-alice")`.
3. The OAuth and universe ACL checks succeed.
4. Execution records `actor="universe:u-alice"`, but the credential context is discarded.
5. Codex or Claude launches with the daemon’s `/data/.codex` or `/data/.claude` credentials.
6. Alice receives work performed on the host’s subscription rather than Alice’s or `u-alice`’s credential.

If the universe has no credential, this should fail closed. If it has a vault credential, that credential should be selected. Using the host credential is an identity and billing-boundary leak.

The policy-router path has the same problem and can bypass even a future context-aware injected provider bridge unless `UniverseContext` is threaded into `call_with_policy_sync`.

## 2. High — Goals marked private are anonymously readable

### Evidence

The write surface explicitly accepts `visibility` values `public` and `private`:

- `origin/main:tinyassets/api/market.py:1151-1158`

Canonical anonymous reads route directly to list, search, and get:

- `origin/main:tinyassets/universe_server.py:427-498`

None of those handlers enforce Goal visibility:

- `origin/main:tinyassets/api/market.py:1377-1416`
- `origin/main:tinyassets/api/market.py:1419-1527`

Storage queries exclude only `deleted`; they include `private`:

- `origin/main:tinyassets/daemon_server.py:2599-2615`
- `origin/main:tinyassets/daemon_server.py:2803-2835`
- `origin/main:tinyassets/daemon_server.py:2855-2895`

The get handler filters private branches but returns the private Goal itself, including its name, description, tags, protocol, author, and canonical/selector metadata.

### Failure scenario

1. Alice calls `write_graph(target="goal", visibility="private", name="Acquisition plan", description="…")`.
2. Mallory connects anonymously.
3. Mallory calls one of:
   - `read_graph(target="goals")`
   - `read_graph(target="goals", query="acquisition")`
   - `read_graph(target="goal", goal_id=<id>)`
4. Mallory receives Alice’s Goal metadata.

There is conflicting historical design material about whether private Goals should exist. That does not make the current behavior safe: the live write contract accepts and stores `private`, creating a false confidentiality promise. The platform must either reject `private` at creation/update or enforce it on every read.

## 3. High — gate-event identity and verification authority can be forged

### Evidence

The extension wrapper forwards caller-supplied identity fields:

- `attested_by`
- `verifier_id`
- `disputed_by`
- `retracted_by`

See `origin/main:tinyassets/api/extensions.py:591-610`.

Handlers prefer those supplied values over the authenticated actor:

- `origin/main:tinyassets/api/market.py:3646-3731`

The model’s only verification restriction is string inequality between verifier and attester:

- `origin/main:tinyassets/gate_events/schema.py:155-174`

Those strings are persisted into mutable DB rows and influence public ranking. Verified events receive extra leaderboard weight:

- `origin/main:tinyassets/gate_events/store.py:145-187`
- `origin/main:tinyassets/gate_events/store.py:332-405`

### Failure scenario

1. Eve authenticates as WorkOS subject `eve`.
2. Eve calls hidden `extensions(action="attest_gate_event", attested_by="alice", …)`.
3. Eve then calls `extensions(action="verify_gate_event", verifier_id="trusted-reviewer", event_id=…)`.
4. The DB states that Alice attested the outcome and `trusted-reviewer` independently verified it.
5. The forged event contributes verified weight to the target branch’s public outcome ranking.

Eve can also dispute or retract another actor’s event by supplying an arbitrary actor string. Authority must be derived from the signed WorkOS subject; actor identifiers should not be public write parameters.

## 4. Medium — scheduler authority is derived from caller-written DB ownership

### Evidence

All scheduler handlers accept `owner_actor` from tool arguments:

- `origin/main:tinyassets/api/runtime_ops.py:365-423`
- `origin/main:tinyassets/api/runtime_ops.py:441-522`

Registration stores that string directly. Pause, unpause, unsubscribe, and removal then treat equality with the stored string as proof of ownership:

- `origin/main:tinyassets/scheduler.py:217-294`
- `origin/main:tinyassets/scheduler.py:320-375`
- `origin/main:tinyassets/scheduler.py:407-477`

No authenticated-subject derivation or universe/branch ACL check occurs.

### Failure scenario

1. Eve authenticates as `eve`.
2. Eve calls `extensions(action="schedule_branch", owner_actor="alice", branch_def_id="b", …)`.
3. The database records Alice as owner even though Eve created it.
4. If Eve knows another schedule ID, she calls `pause_schedule`, `unpause_schedule`, or `unschedule_branch` with `owner_actor="alice"` and controls Alice’s row.
5. If the scheduler is later started, the forged row can execute the chosen branch.

No production code currently starts the scheduler singleton, so automatic execution is dormant. The unauthorized ownership write and cross-owner controls are nevertheless live through the endpoint.

## 5. Medium, conditional — process-global capabilities are inherited by every request

### Evidence

Goal and rollback authorization reads `UNIVERSE_SERVER_CAPABILITIES` directly from the daemon environment:

- `origin/main:tinyassets/api/market.py:70-86`
- `origin/main:tinyassets/api/runs.py:51-67`

`resolve_permission` checks only whether the requested action appears in the supplied grant list. It does not bind those grants to the authenticated actor:

- `origin/main:tinyassets/auth/provider.py:281-325`

Those ambient grants bypass author checks for selector/canonical changes and authorize rollback:

- `origin/main:tinyassets/api/market.py:2100-2108`
- `origin/main:tinyassets/api/market.py:2176-2184`
- `origin/main:tinyassets/api/runs.py:1789-1814`

### Failure scenario

If `/etc/tinyassets/env` contains `set_goal_selector`, `set_canonical_branch`, or `rollback_branch`:

1. Eve authenticates normally.
2. Eve calls the corresponding hidden `goals` or `extensions` action against Alice’s artifact.
3. The handler combines Eve’s actor ID with the process-global grant list.
4. Eve changes Alice’s selector/canonical binding or performs a rollback.

No repository-controlled production default sets this variable, and the live status surface does not expose it, so current exploitation is conditional on host configuration.

## 6. Medium, conditional — `_current_actor()` is an authorization input

The claim that `_current_actor()` is attribution-only is false.

### Evidence

`_current_actor()` falls back to `UNIVERSE_SERVER_USER` when the request identity is anonymous or resolution fails:

- `origin/main:tinyassets/api/engine_helpers.py:177-192`

Private branch visibility compares the branch owner to `_current_actor()`:

- `origin/main:tinyassets/api/branches.py:406-447`

It also participates in capability authorization, Goal ownership checks, rollback attribution/authority, gate authority, and escrow authorization.

### Failure scenario

1. A daemon is configured with `UNIVERSE_SERVER_USER=host`.
2. A private branch is authored by `host`.
3. Mallory connects anonymously and calls `read_graph(target="branch", branch_id=<private-id>)`.
4. `_current_actor()` resolves Mallory as `host`.
5. The private-owner check succeeds and the full branch graph, prompts, node configuration, and source data are returned.

The live probe currently produced `account_user="anonymous"`, so host impersonation was not confirmed under the present live environment. The code path remains configuration-sensitive and is not attribution-only.

## 7. Low — anonymous `read_page` creates durable universe state

### Evidence

`read_page` is advertised with `readOnlyHint=true`:

- `origin/main:tinyassets/universe_server.py:700-756`

For an unknown universe, a missing rules row is treated as publicly readable:

- `origin/main:tinyassets/api/permissions.py:59-89`

After that check, every wiki read calls `_ensure_wiki_scaffold`:

- `origin/main:tinyassets/api/wiki.py:2490-2528`

The scaffold creates directories and writes `index.md`, `WIKI.md`, and `log.md`:

- `origin/main:tinyassets/api/wiki.py:96-132`

There is no target-universe existence check.

### Failure scenario

1. Mallory connects anonymously.
2. Mallory calls `read_page(universe_id="junk-0001")`.
3. The absent rules row is treated as public.
4. `/data/junk-0001/wiki/` and its anchor files are created.

This is an anonymous durable write reachable through a read-classified canonical handle.

## 8. Medium classification defects — read actions execute or persist work

Two extension actions are misclassified:

- `quality_leaderboard` and `recommended_parent_for_fork` default to `read`, but dispatch a selector branch, create a Run, and invoke an LLM:
  - `origin/main:tinyassets/api/extensions_leaderboard_actions.py:55-126`
  - `origin/main:tinyassets/api/quality_leaderboard.py:104-220`
  - `origin/main:tinyassets/api/selector_dispatch.py:512-619`
- `validate_ship_packet` defaults to `read`, but `record_in_ledger=true` writes an auto-ship ledger row:
  - `origin/main:tinyassets/api/auto_ship_actions.py:1-30`
  - `origin/main:tinyassets/api/auto_ship_actions.py:158-290`

Classification derives unknown actions as read:

- `origin/main:tinyassets/auth/provider.py:434-458`
- `origin/main:tinyassets/auth/provider.py:533-588`

The currently deployed WorkOS provider gives every authenticated founder coarse `read`, `write`, and `costly` grants, so these classifications do not presently create a separate WorkOS privilege tier. They remain incorrect security metadata and would become direct scope bypasses under a narrower provider.

## 9. Latent — paid-market authority still uses the env-fallback actor

Escrow authorization calls `_current_actor()` and permits configured host on-behalf actions. Therefore an authless path with `UNIVERSE_SERVER_USER` equal to `UNIVERSE_SERVER_HOST_USER` acquires host money authority.

The live probe confirmed `paid_market_flag_on=false`, and the production worker configuration pins `TINYASSETS_PAID_MARKET=off`. This is not currently publicly exploitable, but it confirms again that `_current_actor()` is not attribution-only.

## Verified non-findings and corrected assumptions

- WorkOS validates RS256 signatures, issuer, expiry, subject, and configured audience.
- Invalid bearer tokens return HTTP 401.
- Anonymous canonical writes are challenged before dispatch. This was confirmed live with `write_graph`.
- Authenticated but under-scoped action failures return tool JSON rather than transport 403.
- `permissions.current_actor_id()` correctly ignores environment fallbacks.
- The six deprecated mixed tools are hidden and still callable by signed-in clients.
- Contrary to the supplied summary, anonymous reads through deprecated mixed tools no longer work. The middleware rejects every anonymous deprecated-tool call with an MCP ToolError. Anonymous reads remain available only through canonical read handles.
- `get_status` is correctly marked non-read-only because authenticated first contact may create a universe.
- Universe-scoped wiki reads now enforce the universe ACL before scaffolding; the remaining scaffold defect concerns unknown universes treated as public.

## Required remediation order

1. Thread a mandatory `UniverseContext` through `run_graph` → async run → compiler → both injected and policy-router provider paths. Fail closed if a universe-bound run reaches a subscription provider without credential context.
2. Decide the Goal contract: reject `visibility=private`, or enforce viewer-aware filtering on list/search/get.
3. Remove public identity parameters from gate events and scheduler actions; derive all actor fields from the signed request identity.
4. Remove process-global capability grants from request authorization. Ambient grants must belong only to an explicitly marked internal daemon principal.
5. Replace `_current_actor()` with `permissions.current_actor_id()` in every authorization or visibility decision.
6. Split argument-sensitive actions into pure-read and write/costly actions.
7. Make wiki scaffolding an explicit authenticated bootstrap operation, or require the universe to exist before any read-side scaffold.

## Verification limitations

This was a read-only source and live-transport audit. No authenticated victim accounts, private production objects, or successful mutation paths were exercised. No independent second-review was run in this turn.