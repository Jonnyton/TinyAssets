# Realtime voice Opus implementation review — round 1

Date: 2026-09-03 PT / 2026-09-04 UTC  
Reviewed head: `7a13f08faf3e6615223675dc730a3982f76b9032`  
Base: `33324d05555c5c5245a37dfd0d4355c33b46729c`  
Model: Claude Opus, read-only through `scripts/peer_agent.py`  
Duration: 513 seconds  
Verdict: `ADAPT`

## Findings

1. The active voice control displayed `Stop` while remaining disabled, so the user could not click
   or keyboard-activate it to release the microphone (`tinyassets/onboarding/app.html`, Voice
   `_render`).
2. `create_voice_session` read the binding and SQLite connection/grant authorization on the async
   server thread before offloading only the outbound bridge request
   (`tinyassets/onboarding/realtime_voice.py`).

## Raw conclusion

> The two landing blockers stand and are both small, local fixes:
> - `app.html:1215-1223` — keep `btn-voice` enabled in the active states so the "Stop" label is
>   actually clickable and the mic can be released.
> - `__init__.py:928` / `realtime_voice.py:342-345` — offload the pre-request binding+ledger work to
>   `run_in_threadpool`, matching the sibling status route at `__init__.py:958-961`.
>
> REVIEWED_HEAD: 7a13f08faf3e6615223675dc730a3982f76b9032
> VERDICT: ADAPT

Both findings are addressed in the following implementation commit and receive focused regression
coverage. A new exact-head Opus verdict remains required before landing.
