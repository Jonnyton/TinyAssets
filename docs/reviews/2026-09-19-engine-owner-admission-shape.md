I'll trace the `engine_tools_unavailable` path from the served greeting through the HTTP engine tool client and the universe allowlist gate, then assess the proposed direction.

**Verdict: ADAPT.** The direction is right and the wall is a category error on current main. Two adaptations are required before the flip, and one cited justification for keeping the wall is stale.

## Cause chain

1. OpenRouter is an HTTP provider whose agent execution kind is `engine_inference` at `tinyassets/providers/router.py:474`. The served coordinator opens engine tools before the first inference on that kind, at `tinyassets/agent_turn_coordinator.py:194`. There is no tools-free path in that loop.
2. Opening tools calls the route reader, which returns nothing when the universe is not in the allowlist, at `tinyassets/engine_mcp_http.py:80`. The client turns that into `engine_tools_unavailable` at `tinyassets/engine_tool_client.py:204`.
3. Even if the reader passed, no server exists for the universe. The supervisor only pins servers for allowlisted serving universes, at `tinyassets/engine_mcp_http.py:239`.
4. The claude and codex paths fall back to a stdio spawn when no route exists, at `tinyassets/providers/claude_provider.py:405`. So a claude-served new user gets read tools today and an HTTP-served new user gets a dead greeting. That breaks the every-surface-same rule stated in `tinyassets/served_tools.py:3`.

So an allowlist introduced in August as a confinement on one write verb now decides whether an HTTP-served universe can speak at all. The read handlers never gate on it. Only the six write handlers do, at `tinyassets/engine_mcp_server.py:523`, 1548, 2165, 2376, 2536 and 2629.

## Why the wall exists and what is actually outstanding

- The origin is a Codex ADAPT on the run_graph slice, recorded in the docstring at `tinyassets/engine_mcp_http.py:119`. Each later verb adopted "the same bar" by habit. The connect_compute gate says so explicitly at `tinyassets/engine_mcp_server.py:2530`.
- The owed multi-tenant items are listed at `openspec/changes/served-agent-build-run/proposal.md:56`: branch-to-universe binding, one-use ingress permit, rolling budget. All three are intra-owner or self-protection. None is a cross-user boundary. The floor is cross-user only.
- The served handlers call the same implementation the connector already exposes to every user without an allowlist, for example `tinyassets/engine_mcp_server.py:541`. The served agent acts as the verified owner with the owner's own capabilities. The allowlist limits what the agent may do on the user's behalf, not what the user may do. Its residual value is prompt-injection blast radius, and the per-verb mitigations for that have landed: sanitizer, effect rate limit, admissions ledger, consent on the rail.
- Remix is gated but unreachable, since it is not in the served tool tuple at `tinyassets/served_tools.py:113`. Its gate is moot.

**DISAGREE_EVIDENCE** on the in-process code concern. `docs/concerns/2026-08-28-user-code-runs-in-process.md` is the strongest reason anyone would keep the wall. Its line citations no longer match. Current code fails closed to the OS sandbox and raises `sandbox_unavailable` with no bwrap, at `tinyassets/graph_compiler.py:2003` and `tinyassets/node_sandbox.py:2178`. Re-verify on the production container and correct the concern in place. Do not preserve the wall on it. The separate source-approval allowlist at `tinyassets/api/source_channel.py:197` is a real in-process boundary and must not change.

## Existing primitive for owner-bound general admission

The tenant admission guard already exists in pieces. The serving binding creator must equal the owner at bind time, at `tinyassets/provider_serving_binding.py:547`. Converse rechecks the binding creator against the verified principal at `tinyassets/universe_intelligence.py:1038`. The adapter refuses any identity drift at `tinyassets/interactive_http_agent.py:18`. The route reader matches exact actor and graph and retires on owner change, at `tinyassets/engine_mcp_http.py:97` and 300. PR #3728 is the precedent that bound connections to their owner.

## Smallest cohesive fix

Replace vetted membership with the guard: engine flag on, universe has a serving binding, binding creator equals the universe admin owner, request principal equals that owner.

- **Transport.** Drop the allowlist test from the reader at `tinyassets/engine_mcp_http.py:80` and from the supervisor filter at line 243. Keep the exact actor and secret match and the single-owner rule.
- **Pin to the admin owner, not `created_by`.** The supervisor derives the pinned actor from the binding creator at `tinyassets/engine_mcp_http.py:133`. Once general, that column is load-bearing for every user. Cross-check it against the universe admin ACL and refuse to pin on mismatch. This is the one authority-sensitive addition.
- **Per-verb gates.** Promote run_graph, write_graph, write_brain, connect_compute and source_channel to the same guard in the same change. Their own gates stay intact. The outbound flag and the source-approval allowlist stay separate.
- **Background work.** The work-agent path also requires a route, at `tinyassets/workflow_agent.py:174`. General admission extends engine tools to background runs of HTTP-served universes. Same principal, same pin, so this is correct, but say it in the spec.
- **Env and docs together.** Remove the variable from `.github/workflows/apply-daemon-env.yml:85`, or it becomes inert config. Update the docstrings that cite the allowlist, the boundary in the proposal, gap 2 in the parity concern, and the source-channel comment that says it mirrors the run allowlist.

## Blockers versus deferrable

Blockers before the flip:

- **DISAGREE_CONCERN, resource shape.** One Python server process per serving universe on a 1 vCPU, 2 GiB box is a host-availability risk, and host availability is cross-user. Measure RSS per engine server and multiply by serving universes before enabling. If it does not fit, add idle retire plus start-on-demand in the supervisor. Do not build a single multi-tenant server in this slice, since the server reads identity once from env at `tinyassets/engine_mcp_server.py:48`.
- Owner cross-check against the admin ACL, above.
- Prod verification that code nodes fail closed to bwrap.

Deferrable hardening: branch-to-universe binding, patch compare-and-swap, rolling budget, ingress permit, the workspace disk bound in `docs/concerns/2026-08-31-workspace-admission-claims-are-narrower-than-stated.md`. The disk bound is reachable through the connector today regardless of this change.

## Required regression and live proof

- Rewrite every test that sets `TINYASSETS_ENGINE_RUN_GRAPH_UNIVERSES` to prove the same refusals with the variable absent. The unlisted case at `tests/test_engine_mcp_routes.py:159` encodes the old contract and must flip. The parametrised change at `tests/test_engine_tool_client.py:96` and the fixtures in the interactive and workflow agent tests set it too. Run each new test against the unfixed tree and require red.
- Mutation test: insert a serving binding whose creator is not the admin owner and assert no server is pinned and the reader returns nothing.
- Cross-user: a route for one universe cannot read another universe's entry; a bearer from one server is refused by another; foreign private branch, brain and run reads keep refusing with the allowlist gone.
- Kill switch: engine flag off still darkens every route and handler.
- Live proof, in order: a fresh non-vetted user on their own OpenRouter free model gets a rendered first reply through the live connector, then a read-driven reply, then a brain write. Then that user's agent asked about the founder's universe is refused. Then the deployed-sha gate with the commit. Rendered conversation is the proof; scripts are supporting evidence.

**AGREE** that any user's authorized model should run the same engine capabilities, that the fix is general owner-bound admission rather than env membership, and that no tools-free greeting fallback should be added. Fail loud on missing admission is correct; the admission itself was wrong.

Checked. None of the listed dispatches live in this worktree, and the four finished files belong to another session's worktree. This session is scoped read-only with no dispatch and no implementation, and its deliverable, the ADAPT verdict above, is complete. There is nothing further for me to advance here.
