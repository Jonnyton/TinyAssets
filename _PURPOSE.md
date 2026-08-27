# Purpose

Make the outbound credential broker's startup failure name its cause.

The founder's `Hello World` post to X has failed since 2026-08-25 behind the
fixed string `outbound proxy failed to start`, with no cause reachable by the
founder, the universe, or the host. This branch does not fix the outage — it
makes the next run say why.

- PR: #2596
- Concern: `docs/concerns/2026-08-27-outbound-proxy-start-failure.md`
- Cross-family review: Codex ADAPT, acted on in `7315bd46`
