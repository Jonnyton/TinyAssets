Blunt verdict: your end-of-run reading is correct. The theoretical happy-path minimum is **2 `run_graph` calls**, not five. But the goal is **not reliably achievable today** with the stated primitives: production egress is currently broken, and prompt-only nodes have no deterministic way to transform and reproduce this 97,551-byte file exactly.

### 1. End-of-run firing

Yes.

The compiled graph completes at [`runs.py:2452`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/runs.py:2452>), its result becomes final `output` at [`runs.py:2641`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/runs.py:2641>), and only then `_run_external_write_effectors` is called at [`runs.py:2683`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/runs.py:2683>). Results are appended afterward at [`runs.py:2696`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/runs.py:2696>).

Resume behaves the same way: resume the graph, wait for completion, then fire effectors at [`runs.py:3811`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/runs.py:3811>).

### 2. Minimum `run_graph` count

Absolute happy-path minimum: **2**.

| Run | Calls |
|---|---|
| 1 | GET file contents and GET `heads/main`, independently |
| 2 | POST ref → PUT contents → POST pull, in that exact `node_defs` order |

The second grouping works because dispatch is synchronous: it iterates `node_defs` in order at [`effectors/__init__.py:86`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/effectors/__init__.py:86>), and each `proxy.request` completes before the next node is processed at [`authenticated_external_call.py:463`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/effectors/authenticated_external_call.py:463>). The later requests need the earlier side effects to exist, but do not need values from their responses.

Important qualification: this is a **blind happy-path chain**. If create-ref fails, PUT and PR still fire. For evidence-gated progression, use **4 runs**:

1. Both GETs.
2. Create ref; inspect status.
3. Update contents; inspect status.
4. Open PR.

For a race-free snapshot, first GET main’s commit, then GET contents pinned to that exact SHA, adding another run. Your parallel GETs can observe different revisions of `main`.

### 3. Missed chaining mechanisms

There is one runtime mechanism, but the agent cannot use it:

- A blocking `invoke_branch_spec` starts a child run and maps the completed child output—including `external_write_results`—back into parent state at [`graph_compiler.py:2437`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/graph_compiler.py:2437>) and [`graph_compiler.py:2455`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/graph_compiler.py:2455>).
- The served `write_graph` surface explicitly rejects `invoke_branch_spec`, version invocation, and `await_run_spec` at [`engine_mcp_server.py:556`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/engine_mcp_server.py:556>).

Everything else is unavailable or unhelpful:

- Graph cycles iterate model/state, but effectors still wait until final completion.
- `run_graph` exposes no resume/run-id parameter: [`engine_mcp_server.py:322`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/engine_mcp_server.py:322>).
- Cloud automation is not reachable through this served writer; it accepts branches or pending requests, not automations: [`engine_mcp_server.py:874`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/engine_mcp_server.py:874>).
- There is no inline effector-call node.
- Reading the completed run and manually supplying evidence to the next run is the supported continuation path: [`engine_mcp_server.py:239`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/engine_mcp_server.py:239>).

### 4. GitHub shortcuts

REST has no combined branch-and-commit operation:

- Creating a ref requires a commit SHA.
- Updating contents requires the **complete Base64 file**, the existing blob SHA, and an existing target branch. [GitHub Contents API](https://docs.github.com/en/rest/repos/contents)
- Creating a PR requires a named head branch; a commit SHA alone is not accepted. [GitHub Pull Requests API](https://docs.github.com/en/rest/pulls/pulls)

There is a GraphQL compression trick: one POST to `/graphql` can contain serial top-level `createRef`, `createCommitOnBranch`, and `createPullRequest` mutations. GitHub documents all three, and GraphQL executes top-level mutation fields serially. [Git references](https://docs.github.com/en/graphql/reference/git), [commit mutation](https://docs.github.com/en/graphql/reference/commits), [PR mutation](https://docs.github.com/en/graphql/reference/pulls), [GraphQL serial execution](https://spec.graphql.org/September2025/).

But:

- `/graphql` must be allow-listed.
- It still needs an earlier read for base OID and complete modified file contents.
- It is not transactional across the three mutations.
- Allow-listing one generic GraphQL endpoint exposes every mutation the PAT permits, weakening the exact endpoint boundary.

It therefore does not reduce the overall minimum below two runs.

### 5. Reasons not to attempt it yet

1. **Live egress is presently broken.** The dated concern identifies `outbound proxy failed to start` as the current shared `authenticated_external_call` blocker, not an X-specific failure: [`outbound-proxy-start-failure.md:54`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/docs/concerns/2026-08-27-outbound-proxy-start-failure.md:54>). The landed diagnostic only reveals the underlying exception; it does not fix the outage: [`outbound-proxy-start-failure.md:79`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/docs/concerns/2026-08-27-outbound-proxy-start-failure.md:79>).

2. **The file-update payload is the real substrate dead end.** On 2026-08-27, `Get-Item tinyassets/onboarding/app.html` reports 97,551 bytes. GitHub therefore needs about 130,068 Base64 characters. The changed variable is at [`app.html:15`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/onboarding/app.html:15>). The transport’s 5 MiB response cap is sufficient, but a `prompt_template` node must make an LLM reproduce the entire file exactly. GitHub offers no patch/diff parameter. That is theoretically stochastic, not a supported “must succeed” transformation.

3. **HTTP failure is easy to misread as success.** GitHub 4xx responses are returned as ordinary responses, and the effector marks transport completion as `delivered: true` at [`authenticated_external_call.py:493`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/effectors/authenticated_external_call.py:493>). Inspect `response.status`; run status alone proves nothing.

4. **The quota is shared.** It is 20 admissions per hour at [`engine_mcp_server.py:67`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/engine_mcp_server.py:67>), and served `write_graph` consumes the same ledger at [`engine_mcp_server.py:937`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/engine_mcp_server.py:937>). Two branch builds plus two runs consume four admissions.

5. The PAT needs both repository **Contents: write** and **Pull requests: write** permissions.

My recommendation: **do not spend the runs yet**. First fix and deploy generic egress. Then provide a deterministic patch executor—an approved code node, a narrowly scoped pre-existing GitHub Action, or a real inline continuation primitive. Without that, opening this particular PR is possible only by gambling that an LLM can losslessly rewrite and Base64-encode a ~98 KB file. After merge, deployment still requires [`deployed_sha.py --assert-contains`](</C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/AGENTS.md:226>), not merely a merged PR.