# Scheduled uptime probes remain red despite public handshake/tool success

**Filed:** 2026-09-08. **Verified:** GitHub Actions production probe run
34257452319 (17:29 UTC), read with `gh run view 34257452319 --log` during the
workflow checklist deployment loop. No runtime restart or private-state edit.

The scheduled probe reports handshake=0, tool=0, wiki=0, activity=2 and revert=5.
It is not evidence that every public surface is down, and those three passes do
not establish worker or background-run liveness.

- Last-activity diagnostic: supervisor heartbeat 2,465,453.2 seconds old,
  phase backoff, consecutive crashes 0; last activity was 08:47:42 UTC that day.
  The probe labels this `worker_wedged` and recommends a restart. Establish
  whether this supervisor is still the authoritative execution surface before
  following that recommendation; recent foreground checklist runs completed.
- Revert-loop diagnostic: get_status has no `evidence` block. Returned keys
  include daemon, release_state, identity_evidence and schema_version. Reverify
  the current response contract and source of revert evidence; do not suppress
  the check or fabricate empty evidence to turn it green.
- Layer-2 browser probe exited 13 (`RED_browser_load_error`). Its exact browser
  error remains uninspected; do not equate this with the app's own availability.

Community-loop run 34265772504 at 18:54 UTC carries these failures and open
incident #2824 forward. The issue's original body is September 4, not fresh
diagnostic evidence. Production deploy 34206123316 had passed its authenticated
public canary and protected SHA gate; that narrower deployment gate does not
close the scheduled probe failures.

Next: inspect current status/probe contracts and the authoritative background
executor's liveness independently, and the browser probe's actual error. Repair
the broken surface or diagnostic contract, then prove the scheduled monitor and
rendered client path. Keep separate from PR #3447's automation routing change.
