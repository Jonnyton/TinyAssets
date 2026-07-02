# Codex opposite-provider review — founder-identity ACL (reconcile + slice 3)

- **Date:** 2026-06-30
- **Writer:** Claude Code (`claude/founder-identity-allslices`)
- **Reviewer:** Codex (`gpt-5.2-codex`, read-only, thread `019f1b30-8090-7de2-8c2c-f29bbaa64a71`)
- **Scope reviewed:** `5ece1a1e` (ACL synthesis — `permissions.py` + `universe.py` delegation + D0a) and `c1cc3f3f` (slice 3 — cross-surface write gates in `wiki.py`/`runs.py`/`auto_ship_actions.py`).
- **Verdict:** `reject` — one in-scope bug (fixed) + four broader-ACL-model gaps (pre-existing, out of slice-3 scope, captured here).

This satisfies the AGENTS.md "Project Skills" opposite-provider-review gate for
auth/ACL work before merge/live-rollout, and the CLAUDE.md "dispatch to Codex
before a done claim" reflex.

## Non-findings (Codex confirmed correct)

- `universe_access_allows(..., write=True)` never returns True without a
  `write`/`admin` grant. The write-boundary primitive itself is sound.
- `universe_public_read_allowed()` fails **closed** on real exceptions;
  `KeyError → True` is only the missing-rules-row (public-by-default) convention.
- `permissions.current_actor_id()` has **no** env fallback — no
  `UNIVERSE_SERVER_USER` can confer write authority via this path.
- `auto_ship_actions._require_universe_write()` skipping the gate on an invalid
  `universe_id` is safe: both `validate_ship_packet` and `open_auto_ship_pr`
  re-resolve and fail before any ledger row / PR is created.

## Finding 4 — FIXED (`88a69b51`), in-scope slice-3 bug

`_extensions_impl` built `run_kwargs` **without** `universe_id`, so the real MCP
route never delivered a universe to `_branch_run_scope_error`. Effect: an
authenticated caller's *own* branch run would be wrongly denied
(`branch_run_requires_universe`), and the slice-3 run gate was effectively dead
on the real path. The direct-call unit tests missed it because they invoked
`_dispatch_run_action` with `universe_id` already in kwargs.

Fix: port the WIP's one-line `run_kwargs["universe_id"] = universe_id`
(`tinyassets/api/extensions.py`) + a real-route regression test
(`test_run_branch_via_extensions_forwards_universe_id_to_gate`).

## Follow-up gaps (real; pre-existing; NOT slice-3 regressions)

Slice 3 only added the write gates the salvaged WIP specified — it raised the
write posture and introduced no regression. These are broader
universe-ACL-model gaps that predate this lane and were never in the WIP:

1. **[F1] Wiki scaffold runs before auth/ACL.** `wiki.py:2411`
   `_ensure_wiki_scaffold(wiki_root)` fires before `_dispatch_scope_error`
   (2437) and the write gate (2445). Any read/denied-write to an arbitrary
   `universe_id` creates that universe's `wiki/` dirs + anchor files
   (`index.md`/`WIKI.md`/`log.md`). Low severity (empty anchors, no content
   disclosure) but a cross-universe side-effect. Fix: resolve/authorize the
   target before scaffolding.
2. **[F2] Private-universe wiki READS are not visibility-gated.** The wiki gate
   only covers `WIKI_WRITE_ACTIONS`; `read/search/list/since/lint` for a
   `public_read=False` universe reach the handler behind only coarse OAuth
   scope. The `universe` tool gates reads via `_universe_acl_error`; `wiki` does
   not. **Design decision needed** — read-gating must not break public-universe
   discovery/remix ("others' to admire"), so scope it to private universes only.
3. **[F3] Other run mutations bypass `permissions.py`.**
   `_branch_run_scope_error` gates only `run_branch`/`run_branch_version`.
   `attach_existing_child_run`, `record_run_receipt`, and `cancel_run` mutate
   durable run state without a universe ACL check (they authorize by run-level
   actor only). Decide whether these need universe-scoped gating or whether
   run-level ownership is the correct boundary.
4. **[F5] `engine_helpers._current_actor()` keeps a `UNIVERSE_SERVER_USER`
   fallback** and `resume_run` authorizes by raw actor-string equality
   (`tinyassets/runs.py`). Not reachable via the hardened `permissions.py`
   path, but if a subject can be spoofed as `universe:<uid>` it could satisfy a
   downstream ownership check. Audit the run-layer actor model separately.

## Disposition

- Slice 3 (cross-surface **write** gates) is correct and verified after the
  Finding-4 fix. F1–F3/F5 are tracked as a follow-up ACL-completeness lane; they
  need a host steer (esp. F2's read-gating design tradeoff) before build.
