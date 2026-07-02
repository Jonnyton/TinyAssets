# Codex opposite-provider review — founder-identity slice 4 (creation contract)

- **Date:** 2026-06-30
- **Writer:** Claude Code (`claude/founder-identity-allslices`)
- **Reviewer:** Codex (`codex exec`, read-only, via `scripts/codex_review.py` background dispatch; verdict `slice4-codex-review.md`).
- **Scope reviewed:** slice-4 diff `56b972d5..a7c52477` (ULID id helper, optional `universe_id`, OKF 13-file bundle seeder, stop notes.json/activity.log).
- **Verdict:** `reject` → **2 real in-scope bugs fixed**, 1 correctly-held item, 2 out-of-scope (auth-slice) follow-ups captured.

## Fixed (real slice-4 bugs Codex caught; my tests had missed them)

1. **Invalid YAML frontmatter.** `_frontmatter()` wrote unquoted values, so
   `body.md`'s `description: Learned embodiment: surfaces...` (a `: ` inside the
   value) failed `yaml.safe_load` — violating OKF's "parseable YAML frontmatter"
   requirement. My test used a naive colon-splitting parser that masked it.
   **Fix:** `_frontmatter` now uses `yaml.safe_dump`; the test helper uses real
   `yaml.safe_load` + a new `test_all_frontmatter_parses_as_yaml` across all 13
   files.
2. **Ledger lost the generated id.** `_extract_create_universe` read
   `kwargs["universe_id"]`; for a server-generated id that kwarg is empty, so the
   ledger row got `target: ""` / `summary: "created "`. **Fix:** prefer
   `_result["universe_id"]` (the generated id) + a regression unit test
   (`test_create_universe_ledger_uses_generated_id`).

## Correctly held (not a defect — intentional slice scope)

- **`POST /v1/universes` still creates universes.** This is the D1 breaking
  removal, explicitly HELD for host live-proof gates (canary + `ui-test`). This
  branch does not claim D1 done — see `tasks.md` preamble (3.1 held). No action.

## Follow-ups (real, but auth-slice scope — NOT slice-4 regressions)

These belong to the WorkOS auth slice (slice 1 / tasks 2.0/2.0a), predate slice
4, and were surfaced by Codex running WorkOS-mode repros:

1. **WorkOS mode does not enforce the create/write auth boundary.**
   `WorkOSAuthProvider.is_auth_required()` returns False, so
   `require_action_scope()` is bypassed and an anonymous WorkOS-mode caller can
   create a universe with `founder_id: ""`. Contradicts D0/D0b (anonymous
   read-only; OAuth-gated creation). Needs the planned resolve-always mode
   (anon reads allowed; named scopes enforced for write/create/costly/admin) +
   WorkOS-provider tests proving anonymous create/write is rejected.
   (`tinyassets/auth/workos_provider.py`, `tinyassets/auth/middleware.py`.)
2. **WorkOS discovery not wired.** In WorkOS mode
   `protected_resource_metadata()` still advertises TinyAssets as its own AS and
   the app 404s on `/.well-known/oauth-protected-resource`. Per WorkOS AuthKit
   MCP docs, PRM must list the AuthKit domain and the well-known routes must be
   mounted/WorkOS-aware. (`tinyassets/auth/wellknown.py`,
   `tinyassets/universe_server.py`.)

## Disposition

Slice-4's non-breaking creation contract is correct after the two fixes
(re-verified: 119 focused tests green). F1/F2 are tracked as a WorkOS
production-auth hardening follow-up needing a host go-ahead (production auth
mode + live surface).
