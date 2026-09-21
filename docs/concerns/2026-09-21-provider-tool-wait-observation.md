# Tool-wait post-deployment observation

September21,2026, production89b47e00f26d: rendered single native WebFetch
completed successfully with an independently measured42.126s tool start/result
gap. Ordinary sequential, parallel and60s workspace runs also completed first
attempt. Full scope and evidence: ../reviews/2026-09-21-provider-tool-wait-deployment.md.

No organic owner use after deployment observed as of20:14UTC. Check fresh
ordinary-user evidence when available, not repeated artificial smoke tests.
One successful call does not prove whether provider tool-progress heartbeats
were emitted. Controlled real-reader tests establish the missing-heartbeat
pending-tool mechanism separately; the live result proves user-facing survival.

Historical6ffec5e973734074 lacks tool-phase evidence: its exact cause remains
unknown. Do not replay it, infer cause from a retry, or retire the broader
intermittent sequential/parallel issue from these successful samples. If a new
failure occurs, inspect its recorded safe phase/age/error evidence before action.
