All adversarial cases behave correctly — spoofed prefixes can't reach the canonical field, non-allowlisted categories emit nothing, and fullmatch rejects trailing garbage. Review complete.

---

# Review verdict: **APPROVE**

**Exact head reviewed:** `cee3baf1d3bc0a51d999b118be71af8b118d0aad` on `fix/oauth-cimd-persistence`, 3 commits ahead of `origin/main` (`625b858f`), merge-base equal to origin/main — no stale-lineage diff inflation. The 12-file diff stays inside the STATUS row's declared Files.

Process note: I deliberately did not dispatch the Codex reflex — the lane author is `codex-gpt5-desktop`, so this session *is* the cross-family review, and the brief forbids delegation.

## What I independently verified

- **Focused tests:** 95 passed across the four lane test files (`test_oauth_discovery_contract`, `test_sanitize_systemd_startup_diagnostics`, `test_diagnose_prod_startup_workflow`, `test_workos_provider`) on Windows/Python 3.13. **Ruff:** clean. **OpenSpec:** `repair-chatgpt-connector-oauth-continuity` valid under `--strict`, and `openspec/specs/` is untouched — tasks 1.2/2.2 remain honestly unchecked with evidence annotations, no premature sync.
- **The historical immutable-window proof is real and exact.** `gh run view 30681363132`: completed successfully at head `f4a6251f78b79a0c320345f0a3ec86a7619e84e5`, window `2026-08-01T02:57:00Z–02:58:00Z`, and the log's sanitized report reads `oauth_rejection_categories=["malformed"]`, `oauth_rejection_envelope_shapes=["canonical"]`, `input_truncated=false`, `raw_lines=44` — matching the audit and brief verbatim. The only "Authorization"/bearer-shaped string in the entire public log is GitHub checkout's own masked header; no raw journal text appears. Empty-window run 30680168689 also verified (success, exact main `7932b333`).
- **Live checker reproduces:** I ran `scripts/check_oauth_discovery_contract.py` against production myself — exit 1 with the single issue `cimd_not_advertised`, everything else green. The screenshot artifact shows exactly what's claimed (ChatGPT Advanced OAuth forced to DCR, "CIMD is unavailable" banner, `https://tinyassets.io/mcp`) and contains no secrets.
- **Sanitizer leak-safety, adversarially probed.** Every emitted value is enum-bounded (allowlisted categories, fixed shape labels, canonical container names). My live probes confirm: a bare warning without prefix → signal-only `bare`; a hostile prefix imitating Compose (`evil daemon-1 | …`) → signal-only `prefixed`, **never canonical**; trailing garbage → no match (fullmatch); a non-allowlisted category → nothing emitted, nothing leaked. The exact Compose-prefix canonical matcher (`sanitize_systemd_startup_diagnostics.py:57-77`) is a strict superset of the prior timestamped envelope (it also adds `tinyassets-daemon-1`), so existing behavior is preserved.
- **Evidence honesty on the two brief-flagged claims:** the audit and `user_sim_session.md` both state explicitly that empty categories "do not prove no request or accepted bearer reached the server," and CIMD enablement is framed as "the smallest supported control-plane experiment… not yet proof that missing CIMD caused the old DCR credential to expire," with an explicit revert-and-rediagnose branch and a no-JWT-changes prohibition. The prior review's two required adaptations (live positive control; attribution-confound line in "Next evidence gate") are both folded in.

## Findings by severity

**L1 (low) — trailing-slash asymmetry in the resource check.** `scripts/check_oauth_discovery_contract.py:26,35` rstrips the expected resource but compares the advertised `resource` raw, so a semantically-equal `…/mcp/` advertisement would false-fail as `resource_mismatch`. Carried over from the preserved review; live matches exactly today. Fix opportunistically.

**L2 (low) — hostile metadata shapes crash rather than classify.** A non-string `authorization_servers[0]` (`check_oauth_discovery_contract.py:102`) or non-string `issuer` (`:39`) raises `AttributeError` with a traceback instead of a clean issue code. Consistent with the fail-loudly norm and both documents are first-party, so low.

**Info — the signal matcher accepts arbitrary prefixes by design** (`sanitize_systemd_startup_diagnostics.py:78-80`). A hostile full-line log echo could inject an allowlisted category into `oauth_rejection_signal_categories`, but never into the canonical field and never any raw text. The docs already treat signal as corroboration-only; keep it that way.

**Info — test-count wording.** The brief cites 103 author-run focused tests; my independent run of the four core lane files finds 95, all passing. No failing test either way; the delta is presumably a different file set, not an evidence problem.

None of these gate the merge or the bounded host-action next step (enable AuthKit CIMD, retain DCR, fresh ChatGPT registration, then the immediate + later rendered authenticated calls). The diagnostic work is exact, leak-safe, honestly documented, and independently reproducible.
