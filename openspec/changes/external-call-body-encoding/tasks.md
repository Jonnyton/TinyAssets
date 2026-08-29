## 1. Effector

- [ ] 1.1 `authenticated_external_call`: apply `{"$base64": <str>}` → base64
      text recursively over `request.body` (dicts and lists) before the wire
      request; a non-string value yields the effector's secret-free error dict.
- [ ] 1.2 Packet docstring and `openspec/specs` delta describe the transform;
      `control_station` / node-authoring guidance says "never generate base64".

## 2. Proof

- [ ] 2.1 Unit: a body with the sentinel is sent with the encoded field and no
      sentinel; nested and list positions; non-string refused; a body without
      the sentinel is byte-identical to today.
- [ ] 2.2 Live (the naive test that filed this): "append one line to README
      and open a PR" through the app lands a commit whose README differs from
      `main` by exactly the appended line — run id, branch and commit sha
      recorded here; then delete
      `docs/concerns/2026-08-29-file-writes-need-model-generated-base64.md`.
