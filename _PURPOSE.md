# Purpose
P1 docs/concerns/2026-08-23-byo-llm-refresh-token-store.md: seal the app refresh-token
store at rest (AES-GCM, daemon-only key) and rotate handles so no caller-chosen handle is
ever written. Google sign-in went public 2026-08-29; the deferral expired.
