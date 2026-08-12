# EXACT-HEAD REVIEW RECEIPT

**Commit reviewed: `5a3ce1ea7bc36b1780be49633b5058094ec66881`**
Author: cowork-agent — Tue Aug 11 20:09:30 2026 -0700 — *feat: retire cloud worker fleet*

No tools used; verification is by inspection of the supplied diff plus the attached full-suite evidence.

## Scope confirmation

The prior independent approval stands unchanged. The only post-approval code correction at this head is the `used_tokens`/`used_cost` accumulator in `reserve_served_provider_budget`, applied identically to `tinyassets/provider_assignment.py` and its plugin mirror `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/provider_assignment.py`. Both hunks carry the same blob transition (`fe960c8c..26590afa`) at the same `@@ -173,11 +173,15 @@` anchor, so the mirror is byte-identical to source — no drift introduced. Everything else at head is OpenSpec archive/status/reflection/audit foldback, which does not touch the authority path.

## The correction — does it count finalized `exceeded` actuals?

**Yes.** Row shape is `(status, reserved_tokens, reserved_cost, actual_tokens, actual_cost)`.

- **Before:** only `status == "succeeded"` contributed actuals; an `exceeded` row fell to the `else` and was debited at its *reservation*. Since `exceeded` means the call consumed past its ceiling, actual ≥ reserved by construction — so every exceeded call silently under-debited the authority by exactly the overage, and that overage was recoverable as spendable headroom by the next call. The correction closes that: `row[0] in {"succeeded", "exceeded"}` routes both finalized terminal states to `row[3]`/`row[4]`, so the overage is permanently charged and `remaining_tokens = authority.max_tokens - used_tokens` shrinks by the real amount. Future calls hold at the true ceiling.
- **Symmetric across both meters.** Tokens and cost got the identical predicate; no possibility of a call holding on tokens while leaking on microunits.

## Does it weaken reservation accounting?

**No.** The change is strictly additive on the finalized side and leaves the in-flight side untouched:

- Every non-finalized row still contributes `int(row[1])`/`int(row[2])` — the **full reservation**, not a partial or actual. Live reservations therefore remain fully debited against remaining budget for their whole lifetime, which is what makes the reserve → clamp → finalize/abandon protocol safe under concurrency. The correction cannot cause a reservation to be discounted before it finalizes.
- The `row[3] is not None` / `row[4] is not None` guards fall back to the **reservation**, never to zero. A finalized row missing actuals is charged at reserved rather than forgiven — the conservative direction. This also removes a latent `TypeError: int(None)` that the old code would have hit on any `succeeded` row with unrecorded actuals; the correction is strictly more robust there, not merely equivalent.
- Both branches remain inside the same transaction that already rolled back and raised `ProviderAuthorityHeldError` above, so the hold check still precedes any arithmetic.

## Evidence assessment

`python scripts/ci_required_tests.py --junit junit-fleet-removal-final.xml --exclude-from .github/heavy-test-files.txt --min-ran 10700` → exit 0, ran 11267 (clears the floor by 567), 9 failures all pre-existing known-broken on main, **NEW failures 0**, stale quarantine 0. Targeted `tests/test_provider_served_router.py` → 14 passed / 2 skipped. Ruff clean on changed files. Plugin mirror rebuilt with import probe green. That is the right evidence shape for a change in the debit path: a green targeted suite alone would not rule out ceiling regressions elsewhere, and the full run with a zero-new-failure delta does.

## Residual, below the report threshold (unchanged from prior, plus one new)

- **New — terminal-status coverage.** The predicate enumerates two finalized states. If the schema admits other terminal-with-actuals statuses (`failed`, `cancelled`, a partially-billed abandon), those still debit at reservation. Correct if abandon deletes the row or the surrounding query filters it — which the diff context suggests but does not show. Worth a one-line confirmation; not a hold, since the fallback direction is over-charging.
- Carrier-only branch (`elif invocation is not None`) takes no durable reservation — per-call ceilings only.
- Tunnel token on argv via `--token`; prefer `TUNNEL_TOKEN` in env and drop the flag.
- `seccomp=unconfined` + `apparmor=unconfined` on the daemon lacks a justifying comment.
- Compose header comment says `daemon:8001` over the bridge; service is `network_mode: host`.
- ship-logs prune `file_ts` fallback of `0` fails open toward deletion; `rclone lsf` failure trips `pipefail` post-upload; `--format tp` comment mislabels modtime as size.
- Served branch lacks the `universe_dir.name == served.universe_id` cross-check and a `None` guard before `universe_dir.parent`.

## Verdict

**APPROVE** — commit `5a3ce1ea7bc36b1780be49633b5058094ec66881`.
