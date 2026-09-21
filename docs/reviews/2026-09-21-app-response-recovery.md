# App response recovery: implementation evidence

Base: deployed c12db274365958d81768ac24a4206649940fbb7b, September 21, 2026.
The original checklist request ended with a persisted provider idle failure
while its sending tab remained thinking. No network capture proves the exact
transport failure. Provider idle and the parallel node's 300-second timeout
remain separate unresolved issues; this patch does not alter their bounds.

## Independent shape review

Claude Fable session31431 completed successfully in347s, verdict ADAPT:
consume matching terminal JSON-RPC frames without waiting for SSE EOF, bound
missing headers/byte silence, and preserve uncertain requests without replay.
Root rejected the proposed text/time-matched history reconciliation because
another tab can send the same words. Saved history is instead an explicitly
uncorrelated, read-only snapshot. No API/storage/authority change is introduced.
Review brief/result are retained in the root task's output directory as
app-terminal-recovery-shape-brief.md and app-terminal-recovery-shape.md.

## Build and verification

Root red commits2d4acf62/7161926c reproduced open-SSE EOF waiting and foreign-ID
acceptance (2failed), while the existing32 transport tests passed in173.22s.
Claude Opus builder1076 reached its780s bound without a terminal success.
Its saved draft was preserved; no approval or completion is inferred from it.
Root independently added actual JSON/fragmented UTF8/multiline tests, caught
and corrected JSON compatibility, and completed safe history/held-queue behavior.
The queue stays held through later inspection questions until explicit resume.

Windows September21: `python -m pytest -q tests/test_onboarding_terminal_frames.py
tests/test_app_stream_liveness.py tests/test_app_live_turn_recovery.py
tests/test_onboarding_mcp_session_recovery.py --tb=short --disable-warnings`
gave59passed in13.13s. The existing app suite gave133passed plus one structural
assertion naming the old voice timestamp expression; that assertion is updated
to the captured send timestamp and must be rechecked before release.
The old test guard's five-second timer is now cleared on settlement; no liveness
assertion was removed. `tests/test_mcp_sse_keepalive.py` gave3passed in7.02s.
Origin keepalives do not prove delivery through the production tunnel.

Final combined Windows run September21, session80214 terminalexit0:
`python -m pytest -q tests/test_onboarding_app.py tests/test_onboarding_terminal_frames.py
tests/test_app_stream_liveness.py tests/test_app_live_turn_recovery.py
tests/test_onboarding_mcp_session_recovery.py --tb=short --disable-warnings`
gave193passed in40.89s (no skips). Ruff and strict onboarding-web-app spec
validation passed. Plugin build/import and mirror parity passed496files.

## Release gate

Exact-head independent review, required CI, deployed revision/public canary and
ordinary rendered app acceptance remain required. No deployment is claimed here.
Rollback is the normal reviewed revert/redeploy of this client-only change;
there is no server migration or provider-policy change to undo.
