**Note on scope:** the prior B1–B3/H1–H2/M1–M8 finding text isn't in this context window, so I'm verifying the snippets directly against the architectural invariant and the checklist you enumerated rather than diffing against remembered wording.

## Checklist verification

**1. Assigned branch — confirmed on all five axes.**
- Canonical serving scope: `"converse" not in assigned.allowed_operations or "writer" not in assigned.allowed_roles` → held. The requested `role`/`operation` are deliberately *not* constrained here, which is the invariant as stated (assignment is validated by the canonical serving binding; internal workflow role is model behavior). The served branch, by contrast, is strict `operation == "converse" and role == "writer"` — correct asymmetry.
- Universe binding: `universe_dir is None or universe_dir.name != assigned.universe_id` → held.
- Carrier match: provider, `assignment_generation`, `assignment_digest`, `credential_reference_digest` (custody), `binding_revocation_generation` — all four axes compared, mismatch → `ProviderAuthorityHeldError`.
- Min ceilings: assigned `max_tokens`/`max_cost_microunits` ≥ 1, carrier ≥ 1, `ceiling = min(assigned.max_tokens, invocation.max_tokens)`, and caller `cfg.max_tokens` rejected on `bool`/non-`int`/`<1`/`>ceiling`.
- Durable reservation: reserve → clamp `cfg` to `reservation.output_tokens` → finalize on success; abandon on `ProviderAuthorityHeldError`, on `CancelledError`/`KeyboardInterrupt`, and on `BaseException`. No exit path leaves a reservation dangling. Snapshot is pinned via `replace(cfg, credential_snapshot_dir=assigned.credential_snapshot_dir)`.

**2. Ambient list — comprehensive for the enumerated surface.** API-key set, subscription config dirs, OAuth token, both b64 injection vars, the opt-in flag, Bedrock/Vertex, GCP ADC, AWS static/session/profile/bearer. More load-bearing than the list itself: children start from `_PROVIDER_CHILD_INHERITED_ENV_VARS` (PATH/OS/locale/TZ only), so an unlisted var still cannot reach a provider child.

**3. Resolver — confirmed.** Both `assigned_credential_availability` and `resolve_assigned_credential` re-raise the typed hold first, then map the full `(KeyError, LookupError, OSError, PermissionError, RuntimeError, sqlite3.DatabaseError, ValueError)` tuple with `from None`. `cleanup_llm_credential_snapshot` sits in a `finally` that wraps the `yield`, so it runs on normal exit, on caller exception, and on authority-construction failure.

**4. Tunnel token required.** `${CLOUDFLARE_TUNNEL_TOKEN:?...}` in `command` — compose refuses to render unset.

**5. Fluent cache supports 2h hourly collection.** `cache-disabled: "false"` with 256m × 4 ≈ 1 GiB dual-logging ring per container; `LOG_SINCE=2h` on an hourly timer gives 2× overlap, no gap.

**6. Queue baseline after quiescence.** Both `inventory_queue_risk` reads follow `docker stop` and `phase = "quiesced"`, and `final_risk != preliminary_risk` raises `FenceError`, so the receipt's hardcoded `"queue_work_preserved": True` is unreachable unless the equality actually held.

**7. Status exceptions sanitized.** `"detail": type(exc).__name__`; `endpoint_hint` is a provider name; `api_key_vars_present` carries names, never values. In `subprocess_env_for_provider`, `_SAFE_RESOLUTION_REASONS` is a fixed allow-list with a type-name fallback, and the generic `ProviderUnavailableError` is raised *outside* the `except` block so no `__context__`/`__cause__` drags upstream text (the `secret=do-not-leak` vector) into a traceback.

## Remaining blocker/high

**None.**

## Residual, below the report threshold

- **Carrier-only branch** (`elif invocation is not None`) takes no durable reservation and sets no `credential_snapshot_dir` — per-call ceilings only, and any snapshot-backed provider fails closed in `subprocess_env_for_provider`. Fine if the store debits the carrier at mint; worth confirming if cumulative caps matter.
- **Tunnel token on argv**: `--token ${CLOUDFLARE_TUNNEL_TOKEN}` is readable via `/proc/<pid>/cmdline` and `docker inspect` to any local or docker-group user. cloudflared reads `TUNNEL_TOKEN` from the environment — rename the var and drop the flag.
- **`seccomp=unconfined` + `apparmor=unconfined`** on the daemon carries no justifying comment; if it's for in-container bwrap, say so and prefer a tailored seccomp profile over full unconfined.
- **Comment drift** in compose: the header says cloudflared reaches the daemon at `daemon:8001` over the bridge; the service actually runs `network_mode: host` against loopback.
- **ship-logs prune** fails open toward deletion — `file_ts` falling back to `0` makes an archive look older than cutoff. Unreachable in practice given the strict `grep -oP` regex, but `continue` is the safer fallback. Also, `rclone lsf` failure trips `pipefail` into a nonzero exit *after* a successful upload, and the `--format tp` comment says "size;path" where it's modtime;path.
- **Served branch** has no `universe_dir.name == served.universe_id` cross-check mirroring the assigned branch, and `universe_dir` isn't None-checked before `universe_dir.parent` in the reservation call (both fields come from the same context, so this is defense-in-depth / crash-shape only).

## Verdict

**APPROVE.**
