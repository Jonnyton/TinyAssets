# Claude-family review — provider-generic credential vault design

**Reviewer:** Claude Fable 5 (latest), 2026-07-16. **Author:** Codex gpt-5.6-sol. **Verdict: APPROVE (build-ready) with 3 adaptations.** Independent basis: I derived the same 4-layer architecture from primary sources before reading Codex's note (`credential-vault-modular-spec.md`); the two converge, which raises confidence this is the standard, correct shape rather than a bespoke invention.

## Convergence (both derivations agree — build on these)
- Envelope encryption, per-record DEK + KEK wrap, versioned key id for rotation/rewrap. ✓
- Two custody backends behind one broker: `platform_encrypted` + `daemon_local` (DPAPI). ✓ (host's hybrid decision)
- Opaque `SecretRef`, `SecretScope(founder/universe/provider/destination/purpose)`, fail-closed `CredentialUnavailable` — never ""/None/ambient. ✓
- Broker put/get/delete + CAS + **per-ref exclusive lease serializing refresh** (the known concurrent-refresh CVE class). ✓
- OAuth connect/disconnect from chat, state+PKCE, tinyassets.io callback; GitHub App PEM = crown jewel, 1h in-memory installation tokens, 8h/6mo serialized user-token refresh. ✓
- Attestation = per-store write/read/wrong-scope-fail/delete probe (not a static env assert). ✓
- Legacy `.credential-vault.json` → quarantine + re-deposit, never auto-promote. ✓
- Redaction enforcement points enumerated + canary scan tests. ✓
- PLAN.md commons-first replacement wording drafted. ✓

## Adaptations (fold into the build)
1. **Adopt Codex's crypto primitive over my AES-GCM suggestion.** XChaCha20-Poly1305-IETF AEAD with the canonical scope/ref/version as **AAD on both the DEK-wrap and the payload** is stronger than plain AES-256-GCM — the AAD binding is what makes ciphertext/wrapped-DEK swapping fail authentication. Use Codex's primitive.
2. **Keep my explicit interface-layer framing as the module boundaries** so "modular" is enforced by structure, and name the reference implementations for future maintainers: the design IS the Nango model (open-source Zapier-auth layer), and the `VaultBroker` seam is deliberately HashiCorp-Vault-Transit-shaped ("encryption as a service"; app never holds the key) so swapping the local-envelope backend for Vault/KMS later is a backend change, not a rewrite. Record both refs in the design note.
3. **Adopt Codex's process-isolation detail** (separate vault-broker process: reads root-only KEK mount at boot, drops to a dedicated vault UID + drops caps before opening its socket; untrusted job sandboxes never mount DB/KEK/socket) — my spec had the interface but not the process boundary. This is the right hardening.

## Host decision to surface (non-blocking for the core build; needed before the X adapter)
Codex's honest finding: **X/Twitter is not free** — current X pricing is pay-per-use ($0.015/request, $0.20 with a URL), no guaranteed free write tier. Hard-$0 therefore requires each user to bring **their own X developer project + credentials + billing**; a platform-owned X app is disabled unless the host accepts spend. The connect UI must not promise free posting and must fail before a write when the user's project has no allowance. GitHub has no such issue. → Ask the host at X-adapter time: users-bring-own-X-creds (hard-$0) vs platform accepts X spend.

## Build order (Codex's seams, endorsed)
Core first (broker types/errors, XChaCha AEAD SQLite backend, DPAPI backend, per-store probe, redaction/canary tests, multiprocess concurrency + single-refresh-race load proof) — this is INDEPENDENT of the slice gates, start now. Then integration seams: S2 (target_repo public, credential value → SecretBinding), S5 (replace credential_vault.py resolvers with broker refs), S4/E4 (GitHub adapter consumes the three github_* kinds; effectors get leases). Then OAuth connect/list/status/disconnect actions + refresh/revocation scheduler + rendered-chatbot ui-test. Release gates: crash-injected CAS/rotation, 100+ concurrent put/get/delete + single-refresh races, stolen-volume-without-KEK, restart/DR, secret canary scan.

**PLAN.md amendment requires host approval before it lands** (design may reference it; the actual PLAN edit is host-gated).
