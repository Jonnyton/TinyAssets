# Explicit model access: implemented browser composition

September 10, 2026, Windows feature worktree following 82168e7a. Applied all
three required ADAPT331s shape corrections before implementation. The picker
uses the server's access-method discriminator and complete accepted map, shows
a positive compatible-model count, asks explicitly about access and reconnecting,
then binds and enables through existing owner/revision-fenced primitives. New
HTTP access remains free-only; existing price ceilings and unrelated members
are preserved. Current choice and saved preferences are not authority changes.

Confirmed legacy bind with unconfirmed enable offers explicitly clicked recovery.
Recovery verifies current home, exact revision and still-configured status before
restoring the same legacy source. Ambiguous writes never automatically retry.
Cancellation, zero eligibility, late signout, changed home/revision and already
serving state are covered. No live account, grant or private workflow was changed.

Verification on September 10, 2026:

- `python -m pytest -q tests/test_app_model_picker.py`: 36 passed in 5.55s;
  these execute the real picker object in Node with synthetic transport/DOM.
- The same 37-file command recorded in app-model-picker-proof.md, Windows
  Python 3.14: 1074 passed, 3 skipped in 96.51s.
- `python scripts/linux_oracle.py --` with that same 37-file selection and
  flags, actual Docker Python 3.11.16/git 2.47.3/bwrap 0.12.0: 1076 passed,
  1 skipped in 87.87s. The real Codex account fixture is not configured;
  Windows's two additional POSIX gaps are covered by Linux.
- The public catalogue/API file now has 21 cases, including real shared
  bind-then-enable composition for legacy conversion and manifest expansion.
- Preserved origin/main's cancellation slot/budget-drain regression verbatim;
  test_http_inference_lifecycle.py is identical to origin/main 41034bf0 and
  passes 15 cases on both Windows and Linux.
- Ruff, regenerated plugin mirrors/import and app checksum, `git diff --check`
  pass. The two separately tracked reset-inventory failures remain excluded,
  unresolved, and are not hidden by this focused group.
- `python output/preview_model_picker.py` passed at 390px and 1280px: native
  confirmation, access/reconnect refresh, selection, fallback reorder, focus,
  Escape and focus return, with no script errors. Both screenshots inspected.
  The actual app markup/script is used with synthetic boot/transport and network
  disabled; this is not live model, account, connector or organic-user proof.

Next: integrate current main, exact release shape/basic-safety review, CI and
verified deployment, then rendered app acceptance. Fully unpowered setup,
explicit native model discovery, non-home controls and complete actual-attempt
telemetry remain open. This slice does not complete the full model-selection goal.
