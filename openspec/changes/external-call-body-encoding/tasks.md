## 1. Effector

- [x] 1.1 `authenticated_external_call`: `apply_body_transforms` applies
      `$ta.base64` / `$ta.from_base64` / `$ta.ref` / `$ta.effect` /
      `$ta.concat` recursively over `request.body` before the wire request;
      any malformed transform yields the secret-free `invalid_body_transform`
      error and nothing is sent. Operators are namespaced (a user's `$ref`
      is never hijacked); nesting is bounded at 32 and the transformed body
      at 8 MiB. (Codex round 1: the first cut's bare `$ref` read the whole
      final state and had no in-run path from a GET response to a write —
      both P0s.)
- [x] 1.2 `effectors.run_effects_for_branch` fences `$ta.ref` to each node's
      declared `input_keys` ∪ state_schema-defaulted keys ∪ its own output
      keys, and hands each effector the evidence of earlier nodes' generic
      effects so `$ta.effect` can chain a fetch into a write in ONE run.
- [x] 1.3 Guidance reaches the SERVED agent: `engine_mcp_server.write_graph`'s
      outbound-node docs carry the two-node fetch→write pattern and "never
      generate base64 or re-type a file"; the `control_station` row says the
      same for the connector.

## 2. Proof

- [x] 2.1 Unit (`tests/test_authenticated_external_call_effector.py`, through
      the real broker + SSRF driver to a loopback): encoded by the effector;
      the two-node fetch→write chain via `run_effects_for_branch` yields the
      exact fetched bytes plus the line; a reference to a later node is
      refused with only the fetch sent; `$ta.ref` fenced; a user's `$ref`
      passes through; six malformed shapes refused with nothing sent and no
      values in the error; identity on plain bodies; depth and size bounds.
- [ ] 2.2 Live (the naive test that filed this): "append one line to README
      and open a PR" through the app lands a commit whose README differs from
      `main` by exactly the appended line, in one run — run id, branch and
      commit sha recorded here; then delete
      `docs/concerns/2026-08-29-file-writes-need-model-generated-base64.md`.
