## 1. Effector

- [x] 1.1 `authenticated_external_call`: `apply_body_transforms` applies
      `$base64` / `$from_base64` / `$ref` / `$concat` recursively over
      `request.body` before the wire request; any malformed transform yields
      the secret-free `invalid_body_transform` error and nothing is sent.
      (The reference and decode operators were added after the live "repair"
      re-typed the file with 36 differences: the model must author only the
      delta.)
- [x] 1.2 Packet docstring and the spec delta describe the transforms; the
      `control_station` prompt's tool table tells the agent to write text,
      reference fetched bytes, and never generate base64 or re-type a file.

## 2. Proof

- [x] 2.1 Unit (`tests/test_authenticated_external_call_effector.py`, through
      the real broker + SSRF driver to a loopback): `$base64` encoded by the
      effector; append-one-line via `$ref`/`$from_base64`/`$concat` yields the
      exact fetched bytes plus the line; five malformed shapes refused with
      nothing sent and no values in the error; bodies without transforms are
      the same object; `$ref` traverses JSON strings and lists.
- [ ] 2.2 Live (the naive test that filed this): "append one line to README
      and open a PR" through the app lands a commit whose README differs from
      `main` by exactly the appended line — run id, branch and commit sha
      recorded here; then delete
      `docs/concerns/2026-08-29-file-writes-need-model-generated-base64.md`.
