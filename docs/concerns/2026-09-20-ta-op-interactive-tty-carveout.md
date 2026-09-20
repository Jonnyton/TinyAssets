# `ta-op` gate: the interactive-TTY carve-out is unadjudicated

**Filed:** 2026-09-20
**Verified:** 2026-09-20, `python scripts/check_drop_first_exec.py` on
`codex/drop-first-ops` @ `023f5af55da24a0a487f970f8910d53087daa6f3` (exit 0,
254 files, 8 modes, 1 note emitted).
**Severity:** P2 — a stated scope limit, not a live defect. It becomes P1 the
day production flips to root-start.

## The concern

`scripts/check_drop_first_exec.py` fails any repo-authored `docker exec` into
the daemon container that does not go through `/usr/local/libexec/ta-op <mode>`
— with one exception. An exec that allocates a TTY (`-t`, `-it`, `-ti`) is
reported as a **note** and does not fail the gate.

Today that exception matches exactly one shape, in two files:

- `deploy/DEPLOY.md` — `claude auth login --claudeai` on a fresh volume
- `deploy/tinyassets-env.template:148` — the same command, as a comment

## Why it exists, and why that is not sufficient

The carve-out is **structural**, not a callsite allowlist: a TTY allocation is
something no workflow, timer or CI runner can use, so it cannot be reached by
automation. The coordinator disposition directs that ad-hoc admin SSH is
outside the repo gate, and any holder of `~/.ssh/tinyassets_deploy_ed25519`
already has arbitrary root SSH on the droplet — so this exception grants an
admin nothing they did not already hold.

**But that reasoning is about *today's* rootless posture.** The reviewed
eight-mode table (`deploy/native/ta_op_modes.tsv`) has no interactive mode,
and I did not have authority to invent a ninth one, so I did not. After a
root-start flip, an unwrapped `-it` exec is exactly the "generic root recovery
shell" that `openspec/changes/workspace-node/memory-containment-production-adaptation.md:148-152`
forbids. The structural argument does not survive that flip; the file would
still be green.

## The decision owed

One of:

1. **Add a ninth fixed mode** (e.g. `claude-login` → `/usr/local/bin/claude auth
   login --claudeai`, fixed argv, no caller data, TTY inherited after the drop)
   and delete the carve-out. Cheapest, and keeps "no exceptions" literally true.
2. **Replace the interactive login in the runbook** with the non-interactive
   seeding path already referenced in `deploy/tinyassets-env.template`
   (`TINYASSETS_CLAUDE_AUTH_*`), and delete the carve-out.
3. **Keep the carve-out** and make it conditional on the rootless posture, so it
   turns into a hard failure as part of the root-start change.

Options 1 and 2 are both small. Option 3 is the one that must not be forgotten,
because it is the only one where the gate stays green through the flip.

## Related, and not to be confused

`output/claude-handoff-reaping-result.md` (Fable's lane, commit `714e9683`)
records `app-pulse` manual exit **1**. That is a `network none`, token-less
fixture container, and the failure is a missing `git_sha`, not missing
authorization. **It is not evidence about the production `--pulse-only`
healthcheck** that `ta-op pulse` now wraps, and must not be cited either way in
the D2 rollback-ordering regression.

## Resolve by

Deleting this file, in the same change that picks one of the three options.
