## 1. Effector

- [x] 1.1 `authenticated_external_call`: `apply_body_transforms` applies the
      five reserved `$ta.*` operators recursively over `request.body` before
      the wire request; an unknown `$ta.*` spelling, a wrong type, an
      unfenced/unresolvable path, non-UTF-8 bytes, nesting past 32, a working
      set past 32 MiB (charged as produced) or a body past 8 MiB refuse the
      whole call with `invalid_body_transform`; nothing is sent. (Codex rounds
      1–2: bare `$ref` read the whole state; no in-run byte path; header
      exfiltration via `$ta.effect`; memory amplification before the size
      check; a RecursionError on deep plain bodies; unnamespaced operators.)
- [x] 1.2 `effectors.run_effects_for_branch` fences `$ta.ref` to each node's
      declared `input_keys` ∪ state_schema-defaulted keys (narrower than the
      compiler's render view, deliberately), keeps each generic-call result in
      memory for later nodes' `$ta.effect` (response.body / response.status
      only; storage order), and persists `bounded_evidence(...)` — a 4 KiB
      preview + size + sha256 — so a fetched file does not re-enter a model
      through `read_graph`.
- [x] 1.3 Guidance reaches the SERVED agent: `engine_mcp_server.write_graph`'s
      outbound-node docs carry the two-node fetch→write pattern ("store fetch
      before write", "UTF-8 text files", "never generate base64 or re-type a
      file"); the `control_station` row says the same for the connector.

## 2. Proof

- [x] 2.1 Unit (`tests/test_authenticated_external_call_effector.py`, through
      the real broker + SSRF driver to a loopback): encoded by the effector;
      the two-node fetch→write chain via `run_effects_for_branch` yields the
      exact fetched bytes plus the line while the persisted fetch evidence is
      a bounded preview; a write stored before its fetch is refused with only
      the fetch sent; `$ta.ref` fenced; headers unreachable through
      `$ta.effect`; a user's `$ref` passes through; `$ta.bas64` refused; deep
      plain bodies refused, not crashed; the working-set budget refuses a
      repeated reference; identity on plain bodies; depth and size bounds.
- [ ] 2.2 Live (the naive test that filed this): "append one line to README
      and open a PR" through the app lands a commit whose README differs from
      `main` by exactly the appended line, in ONE run — run id, branch and
      commit sha recorded here; then delete
      `docs/concerns/2026-08-29-file-writes-need-model-generated-base64.md`.
