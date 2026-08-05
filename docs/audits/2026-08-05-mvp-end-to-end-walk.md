# MVP end-to-end walk — live production, 2026-08-05

**Environment:** `https://tinyassets.io/mcp`, production serving
`release_state.git_sha = 868153bdc5be646f35e2cca65bcfc82f6dbb44b2` (= `origin/main`
HEAD), deployed `2026-08-04T23:00:39Z`, `forward_canary_status: passed`.
Hard Rule 14 satisfied — this walk exercised the code production actually runs.

**Verdict: the golden path cannot be walked end to end.** It stops before step 5
of 8. Three blockers, none of which is a defect in the code that exists.

> Scope note: this is **supporting evidence, not final chatbot-surface proof**.
> Per AGENTS.md, final acceptance needs a browser-rendered connector
> conversation (`ui-test`). These were direct MCP calls. The blockers below are
> reachable-state facts, not UX claims.

## What works — verified live

| Step | Result | Evidence |
|---|---|---|
| Public surface health | **pass** | `mcp_public_canary.py --assert-handles` exit 0. Mutation-probed first: a bogus URL exits 2, so the green is real rather than a silent no-op |
| 1. Discover a public agent | **pass** | `read_graph target=agents` → 3 definitions |
| 2–3. Remix + customize | **pass** | Published a real 2-parent remix `agent_01kz7kn4vpqz0fp8w6ytq6et9t`; lineage recorded per component with `parent_definition_id`, `credit_share`, `generation_depth: 1`, and both definition and component fingerprints |
| 4. Private binding | **pass** | `agent_binding_01kz7knr5haptc4mzb7f59513z` created; the public `portable_definition` carried **no** provider, destination, or binding reference — the public/private boundary held |

An earlier definition ("V1 Intelligence Agent") describes itself as a remix but
has `lineage: []`. That is a prior test artifact published via `publish` rather
than `remix`, **not** a lineage defect — a fresh `remix` records lineage
correctly, as above.

## Blocker 1 — a user cannot give their universe an engine

`converse` returns:

```
status: held · reason: setup_required · missing: ["compute", "model_access"]
setup_paths[0].how = "Engine assignment is not exposed by the advertised handles."
note: "Ask the host to use the internal engine-assignment surface."
```

**This is correct behaviour, not a bug.** The universe refuses to think on
anyone else's credentials — the fail-closed posture that
[[ambient-credential-fallback-is-an-identity-leak]] exists to enforce.

Cross-family review (Codex, read-only, verdict `adapt`) confirmed there is no
user-reachable path, with citations:

- `write_graph(target="universe")` always *creates* a universe and **ignores
  `operation`** — it cannot dispatch `set_engine` (`universe_server.py:738`).
- The real setter exists only on the deprecated `universe(action="set_engine")`
  (`api/universe.py:5915`), hidden from `tools/list` (`universe_server.py:2451`).
- `bind_provider` writes *cloud-work* authority from a server-side enrollment
  manifest (`api/cloud_automations.py:419`, `provider_work_enrollment.py:82`)
  and never touches universe config or the vault. `converse` independently
  loads `UniverseContext` and calls its configured writer
  (`universe_intelligence.py:520`). **Two credential surfaces at different
  readiness**: automations are provisioned, conversation is not.
- The only self-serve OAuth flow is GitHub-destination-only
  (`api/cloud_connections.py:108`).

### Do not "fix" this by exposing a handle

Two landed decisions forbid the obvious repair:

- **`retire-mcp-provider-secret-deposit`** is an explicit **BREAKING** change
  prohibiting provider-key deposit through MCP: it "crosses the
  chatbot/control-plane boundary before the requester-controlled executor can
  protect the secret" and can make a shared-universe admin a confused deputy.
- **`constrain-set-engine-provider-authority`** records `set_engine` as an
  unresolved boundary that has drawn `ADAPT` across roughly five review rounds.

The sanctioned repair already has an owner: **`STATUS.md` row 13**,
`activate-requester-owned-cloud-compute-binding` — *"expose a phone-safe
provider enrollment/bind path … no maintainer or market fallback"* —
`claimed:codex-gpt5-desktop`. Its files are off-limits to other lanes.

**The unresolved question is a host decision, not an engineering task:** the
approved demo promises a browser-only user with *no daemon install*, while the
retirement change requires requester-supplied keys to live in a
**requester-controlled executor's OS secret store**. Those two cannot both hold
for a BYO-key user. Either the browser-only user's engine arrives by
subscription enrollment (server-side manifest, no secret crossing MCP — the
shape `bind_provider` already uses for automations), or the demo needs a local
executor. That choice gates steps 5–8.

## Blocker 2 — no Slack connection exists

`read_graph target=connections` → exactly one: `provider: github`,
`connection_class: pull-request-writer`, destination `jonnyton/tinyassets`,
cap 1 PR. The approved demo requires Slack conversation **and** scheduled Slack
delivery, so GitHub cannot substitute (confirmed by the same review). Steps 5
and 7 have no transport. Requires host-supplied Slack workspace + app
credentials.

## Blocker 3 — the workflow-iteration successor does not exist

Step 6 (draft → test → evaluate → revise → approve) needs
`enable-custom-agent-workflow-iteration`, whose admission gate
(`activate-custom-agent-runtimes` task 2.3) has **six preconditions, all
unmet** — three of them naming hardening changes that have never been created.
Recorded in `docs/handoffs/2026-08-04-custom-agent-mvp-handoff.md` §2 (PR #2289,
merged `884011ca`).

## Correction to an earlier claim in this walk

An interim version of this analysis asserted "**0 runs have ever executed** in
universe `u-01kxm1vszd8hwp7em418asq8h9`." **That is unsupported and is
retracted.** `read_graph target=runs` *ignores* `graph_id`
(`universe_server.py:502`) and filters inaccessible private runs afterward
(`api/runs.py:882`), so an empty result means "no runs this caller may see",
not "no runs exist". The blocker stands on the `held/setup_required` response
and the absent Slack connection alone. Caught by cross-family review, not
self-review.

## Unrelated finding surfaced during this walk — `main` is red

`main`'s own CI at `868153bd` reports **`NEW failures: 10`** against its own
quarantine baseline, including
`tests/test_cloud_automation_api.py::test_phone_rebinds_and_rolls_back_to_published_branch_versions`
(`KeyError: 'status'`). Exactly one commit landed between the last green gate
(PR #2289, 22:37) and that state:

```
git log --oneline 884011ca..868153bd
→ 868153bd fix: admit the universe id prefix production actually mints (#2291)
```

#2291 is a correct and valuable fix — admitting the `u-` prefix production
mints is what unblocks real cloud-automation creation — but it moved execution
past a rejection path several tests asserted, and the quarantine list was not
updated. **Every PR cut after it inherits all 10 as "NEW failures."** Triage
belongs to #2291's lane, not to whichever PR happens to notice.

## Test artifacts left on production

No delete operation is exposed on the canonical handle set:

- `agent_01kz7kn4vpqz0fp8w6ytq6et9t` — "E2E Walk Test Agent (2026-08-05)" (public definition)
- `agent_binding_01kz7knr5haptc4mzb7f59513z` — its private binding

## What would unblock the demo, in order

1. **Host decision:** does a browser-only user's engine arrive via subscription
   enrollment, or does the demo assume a local executor? Everything below waits
   on this.
2. **Row 13 lane** (`codex-gpt5-desktop`) lands the phone-safe provider
   enrollment/bind path for the conversational surface, not only cloud work.
3. **Host action:** provision a real Slack workspace + app credentials and a
   Slack destination grant.
4. Clear the six task-2.3 preconditions, including creating the three
   hardening changes that do not exist.
5. Re-walk, then perform the `ui-test` rendered-connector proof.
