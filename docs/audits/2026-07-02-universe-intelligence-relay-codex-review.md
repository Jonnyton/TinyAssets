# Codex opposite-provider review — Universe Intelligence + Relay reshape

- **Date:** 2026-07-02
- **Reviewer:** Codex (via `scripts/codex_review.py`, `--cwd` = worktree `permissions-fail-closed`, branch `claude/founder-identity-allslices`)
- **Subject:** `docs/design-notes/2026-07-02-universe-intelligence-relay-architecture.md`
- **Verdict:** **ADAPT**
- **Raw output:** `$CLAUDE_JOB_DIR/tmp/codex_reshape_review.md`

## Character of the review

Codex did **not** refute the reshape's core claims — the embody→relay reversal,
the feasibility (recomposition) argument, and the swarm/zero-daemon tension
resolutions were left standing. It focused instead on concrete, *reproduced* code
issues. So the design-level stress test was **thin**; a focused design-refute
pass (reversal soundness, singleton-gap blast radius, handle-canary) is owed
before build (gate carried forward).

Source check: Codex confirmed the WorkOS RS approach is sound against current
WorkOS AuthKit MCP docs + MCP auth spec (2025-11-25) + RFC 9728 + RFC 8707
(resource-indicator ↔ PRM `resource` ↔ `aud` binding; `resource_metadata`
challenge). Invariants must survive the fallback paths.

## Findings + disposition

1. **[CRITICAL — reshape design constraint] Daemon-scoped actions fail the WorkOS
   scope gate.** `_DAEMON_SCOPED_ACTIONS` bypasses only the ACL; `_dispatch_scope_error`
   runs *first* (`tinyassets/api/universe.py:4971`). Codex reproduced
   `daemon_memory_capture` → `auth_scope_required` with a resolve-always
   (WorkOS-like) provider + no founder token.
   **Disposition: FOLD into the design as a named prerequisite.** The universe
   intelligence is a daemon-class actor that takes all actions; it needs an
   explicit non-user auth/actor path evaluated *before* user-OAuth scope gating.
   This concretizes design open-Q3 (credential custody). Also an independent
   foundation blocker (daemon memory currently broken under WorkOS).

2. **[CRITICAL — foundation merge-blocker] WorkOS deploy fallback is fail-OPEN.**
   With `WORKOS_AUTHKIT_DOMAIN` absent, deploy sets `UNIVERSE_SERVER_AUTH=optional`;
   optional mode exits the scope gate (`tinyassets/auth/middleware.py:257`) and
   `create_universe` is ACL-exempt (`universe.py:142`). Codex reproduced anonymous
   `write_graph target=universe` creating a universe + returning a birth card.
   **Disposition: real. Must fix before any merge** (the reshape merges *with* the
   foundation). Fix = fail the deploy when WorkOS config absent, OR make remote
   optional mode deny anonymous create/write. Add regression for anon
   `write_graph target=universe` under fallback.

3. **[REQUIRED — foundation test debt] Rename orphans.**
   `tests/test_get_recent_events.py` = 3 failed / 10 errored / 8 passed; tests
   still monkeypatch `tinyassets.api.universe._default_universe` (branch removed
   the module symbol). **Disposition: confirmed (matches prior triage). Fix =
   update callers/tests to `_request_universe`, then full-suite rerun.**

4. **[REQUIRED] Rebase on origin/main** — worktree 3 commits behind.
   **Disposition: do before final foundation review.**

5. **[INFO] Passing suites:** `test_workos_provider` + `test_require_auth_challenge`
   + `test_multi_tenant_isolation` = 55; `test_first_contact` = 17;
   `test_action_scopes` = 5; `test_daemon_brain_api` = 2.

## Net

Reshape **design survives** review (not refuted) with **one substantive
adaptation**: the universe intelligence requires a daemon-class auth path
evaluated before user-OAuth scope gating (Codex proved it is broken today).
Findings #2–#4 are foundation-merge blockers, independent of the reshape but
on the same merge path per the host's "merge foundation + new shape together."
Carry-forward gate: a focused design-level refute before build.
