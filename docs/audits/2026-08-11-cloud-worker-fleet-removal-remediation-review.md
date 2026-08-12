## Verdict summary

**CHANGES REQUIRED.** Eight of the twelve original blockers are genuinely closed. Two are closed only in one of the two modules that share the failure mode, one is incomplete, and one is partially enforced. Findings below are ordered by severity.

---

## BLOCKER

### B1 — Assigned-credential path never enforces `allowed_operations` / `allowed_roles`
`router.py::ProviderRouter._call_authorized`, assigned branch.

`AssignedCredentialAuthority` carries `allowed_operations` and `allowed_roles` (populated from the binding row in `_assigned_credential_state`), and the two sibling paths *do* enforce scope — `served` hardcodes `operation != "converse" or role != "writer"`, the carrier path calls `carrier.validate_for_call(role=role, operation=operation)`. The assigned branch checks only `universe_dir.name == assigned.universe_id`, positive budgets, and the token ceiling. `operation` and `role` are never compared against the binding's allowed sets.

Failure: a binding issued with `allowed_operations=("converse",)` authorizes a `run_graph` call, or a `writer`-only binding authorizes a `judge`/`critic` role, as long as the universe id matches. `bind_assigned_provider_call` hardcodes `operation="run_graph"`, so the only enforcement of that value would have to live in `bind_universe_provider_call` — but `_call_authorized` is the documented exact-authority chokepoint and is reachable with any `(role, operation)` pair from any caller that populates `UniverseContext.assigned_credential`.

Second clause, same site: the carrier cross-check is `invocation.provider != assigned.provider`. `binding_id`, `binding_generation`, and `binding_digest` are all carried on both objects and none are compared, so a stale carrier armed against a superseded binding of the same provider passes.

### B2 — "Complete ambient stripping" is not complete
`providers/base.py::AMBIENT_PROVIDER_AUTH_ENV_VARS`.

Missing, at minimum:
- **`ANTHROPIC_AUTH_TOKEN`** — the direct functional sibling of `ANTHROPIC_API_KEY` (bearer-token auth honoured by the Anthropic SDK and Claude Code). `ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL` are both stripped; this one is not.
- **`OPENAI_BASE_URL` / `OPENAI_API_BASE`** — `ANTHROPIC_BASE_URL` is stripped but the OpenAI/codex equivalent is not, so an ambient endpoint override survives into the long-lived daemon.
- **`GOOGLE_API_KEY`** — accepted as a Gemini credential by `google-genai`; only `GEMINI_API_KEY` is listed.
- Bedrock/Vertex routing vars (`CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`, `ANTHROPIC_VERTEX_PROJECT_ID`, `AWS_*`) if those code paths exist.

The provider *subprocess* is protected independently by the `_PROVIDER_CHILD_INHERITED_ENV_VARS` allow-list, so blast radius is the daemon/tray process itself, not the CLI child. But the tuple is the sole mechanism behind the stated invariant ("Every long-lived platform process removes this complete ambient authority surface before launching") and behind the tray's `env.pop` loop, and it does not hold.

### B3 — Exception-chain leak fixed in one module, still live in the other
`assigned_credential.py`, both `assigned_credential_availability` and `resolve_assigned_credential`:

```python
except (KeyError, LookupError, OSError, PermissionError, RuntimeError,
        sqlite3.DatabaseError, ValueError) as exc:
    raise NoRequesterOwnedExecutor() from exc
```

`from exc` sets `__cause__`, and standard traceback rendering emits `str(exc)` under "The above exception was the direct cause of…". In `resolve_assigned_credential` the guarded block includes `snapshot_llm_subscription_credential(...)` — i.e. the function that materializes the plaintext credential. A `ValueError` from a credential parser quoting the offending value lands in the chain.

This is precisely the pattern `providers/base.py` documents and deliberately avoids (`_safe_resolution_reason` allow-list, plus raising `failure` *outside* the `except` block so `__context__` is never attached). That implementation is correct; it just wasn't applied here. Fix: `raise NoRequesterOwnedExecutor() from None`, or assign-and-raise-after-the-handler as in `subprocess_env_for_provider`.

---

## HIGH

### H1 — `CLOUDFLARE_TUNNEL_TOKEN` is the only required secret with no `:?` guard
`compose.yml`, `cloudflared.command`.

`TINYASSETS_IMAGE` uses `${...:?message}` in both services. `command: tunnel run --token ${CLOUDFLARE_TUNNEL_TOKEN}` does not. Compose interpolation reads the shell env / `--env-file` — **not** a service's `env_file` — so if the token lives only in `/etc/tinyassets/env` and that file isn't passed as `--env-file`, the variable renders empty and the command becomes `tunnel run --token` with the next token consumed as the argument, or a bare flag. Daemon health is unaffected, so the stack reports up with a dead public ingress. Use `${CLOUDFLARE_TUNNEL_TOKEN:?...}`.

### H2 — `ship-logs.sh` collection is coupled to Docker's dual-logging cache, and truncation is reported as success
`compose.yml` sets `driver: fluentd` on `daemon` and `cloudflared`; `ship-logs.sh` collects via `docker logs "${container_id}" --since "${LOG_SINCE}"`. The fluentd driver has no read API — `docker logs` only works via the engine's local dual-logging cache.

Two consequences:
- If `cache-disabled` is set true in `daemon.json` (or per-container), `docker logs` returns *"configured logging driver does not support reading"*, the new strict check fires `ERROR: logs for required container tinyassets-daemon are unreadable`, and the **entire offsite archive exits 1 on every run** — nothing is shipped, including for the containers that would have worked. The underlying cause is swallowed into `${log_file}`, which the `EXIT` trap then deletes, so the operator sees only the generic message.
- With the cache enabled (default), it is size-bounded (`cache-max-size`/`cache-max-file`, ~20m×5 by default). A busy daemon's `--since 24h` window is silently truncated to whatever the cache still holds, while the manifest row and the `${lines} lines (since ${LOG_SINCE})` line both assert a full 24h capture. That is exactly the class of untruthful status the strict-fail hardening was meant to eliminate.

The compose comment "otherwise logs are captured by compose stdout (journald) only" is false for these two services for the same reason.

Fix: either add `local`/`json-file` as the read path, or have the collector assert the window is actually covered (oldest captured timestamp vs. the requested `--since`) and record a `truncated` column in the manifest.

---

## MEDIUM

### M1 — Credential snapshot leaks on construction failure
`assigned_credential.py::resolve_assigned_credential`. `snapshot = snapshot_llm_subscription_credential(...)` happens inside the first `try`, but `authority = AssignedCredentialAuthority(...)` is built *between* that block and the `try/finally` that owns `cleanup_llm_credential_snapshot`. Any exception from the 18-kwarg construction (including `snapshot.directory` attribute access) leaves the plaintext snapshot directory on disk with no cleanup. Move the snapshot acquisition so everything after it is inside the `finally`-guarded region.

### M2 — Served/armed token ceilings accept `0`
`router.py::_call_authorized`. The assigned branch rejects `cfg.max_tokens < 1`; the served and invocation branches use `cfg.max_tokens < 0`. `max_tokens=0` therefore validates, reserves 0 output tokens via `reserve_served_provider_budget`, and is passed to the provider — where 0 is either rejected or, for CLI/SDK paths that treat 0/absent as unset, means *unbounded*. Overspend would then only be observed after the fact in `finalize_served_provider_budget`. Make all three branches `< 1`.

### M3 — `estimated_input_tokens` is a byte count
`router.py`: `max(1, len((f"{system}\n\n{prompt}" if system else prompt).encode()))`. Bytes, not tokens — roughly 4× over-reservation against the served budget for typical English text, more for anything non-ASCII. The reservation is reconciled on finalize, but until then it can spuriously exhaust a binding's budget and deny calls that would have fit.

### M4 — Reservation lifecycle holes
Same `try` block:
- `except ProviderAuthorityHeldError: raise` precedes the generic handler, so any `ProviderAuthorityHeldError` raised *after* `reservation` is assigned (e.g. from `finalize_served_provider_budget`) skips `abandon_served_provider_budget` and dangles the hold until TTL.
- If `finalize_served_provider_budget` partially succeeds then raises anything else, the generic handler calls `abandon_served_provider_budget` on an already-finalized reservation — double release.
- `except BaseException` catches `asyncio.CancelledError` and `KeyboardInterrupt`, applies `COOLDOWN_OTHER` to a healthy provider, and (from the visible control flow, though the excerpt truncates at `attempts.append`) converts them into `AllProvidersExhaustedError`. Swallowing `CancelledError` breaks asyncio cancellation. Re-raise `CancelledError`/`KeyboardInterrupt` after abandoning.

### M5 — Fence identity gate validates the revision but not the image
Workflow snippet: `active_revision` is checked against `^[0-9a-f]{40}$`, but `active_image` gets no equivalent check. In the Python gate, `len(images) != 1` is satisfied by a single `None` or `""` — `print(next(iter(images)))` then emits `None`, `readarray` assigns `active_image="None"`, and "active fleet identity is not exact" passes. Apply the same `CANONICAL_IMAGE_RE`-style assertion the fence module uses on `_configured_image()`.

### M6 — `_SAFE_RESOLUTION_REASONS` omits one of the module's own sentinels
`providers/base.py`. `"credential snapshot is unavailable"` is raised in three places in `subprocess_env_for_provider` (missing/non-dir snapshot, symlinked/non-file token, empty token) but is not in the allow-list, so the most common containment failure logs as a bare `ValueError` with no distinguishing detail. Conversely `"auth overlay is not universe-contained"` is in the list but never raised in the supplied code. The allow-list and the sentinel set have drifted.

### M7 — Raw `str(exc)` returned in the status payload
Status module: `return json.dumps({"error": "config_load_failed", "detail": str(exc), ...})`. Same hazard class as B3, on a caller-facing surface: an arbitrary config-load exception message is returned verbatim. Parse errors commonly quote the offending line. Reduce to a type name plus an allow-listed reason, as `_safe_resolution_reason` does.

### M8 — Stale comments contradict the code they document (truthful-status regressions)
- `slack-agent`: *"Note what is absent: no `env_file`"* — the service has `env_file: - /etc/tinyassets/app-ingress.env`. The later paragraph gets it right; the earlier one reads as a hard invariant and is false.
- `slack-agent`: *"the daemon check probes the node-claim queue this service never touches"* — the daemon healthcheck runs `mcp_public_canary.py` against `/mcp`. (Also `"the the daemon check"`.)
- Status module: *"Priority chain mirrors the provider-router's preference order: local/subscription endpoints beat API-key-only providers"* — the router is now *"Launch exactly the provider named by server-resolved authority"* with no preference order and no fallback. The comment describes retired behaviour on the surface whose job is to report actual behaviour.

### M9 — `security_opt: seccomp=unconfined` + `apparmor=unconfined` on the daemon
Unexplained, in a file where every other non-obvious decision carries a rationale paragraph. This is the container that mounts the durable data volume and drives provider CLIs; disabling both syscall filtering and MAC is a material weakening of the containment story the rest of the packet is built around. Either document the specific syscall that required it (and scope to a custom profile) or drop it.

### M10 — Prune regex is not anchored to the archive prefix
`ship-logs.sh`: `grep -oP '\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}'` matches the timestamp *anywhere* in the filename; the comment claims extraction "from tinyassets-logs-…". Any object at `${LOG_DEST}` whose name embeds an ISO-ish timestamp — another job's artifact in a shared bucket path — is deleted once it ages past `LOG_RETAIN_DAYS`. Anchor to `^tinyassets-logs-(...)\.tar\.gz$`.

### M11 — `rm -rf` on an operator-supplied, possibly pre-existing directory
`ship-logs.sh`: `mkdir -p "${LOG_DIR}"` followed by `trap 'rm -rf "${LOG_DIR}"' EXIT`. `LOG_DIR` is a documented override. If it points at an existing directory the script did not create, that directory is destroyed on exit. Refuse a non-empty pre-existing `LOG_DIR`, or `mktemp -d` inside it and only clean up what was created.

### M12 — Queue-risk baseline is sampled while the daemon is still running
Fence preflight: `preliminary_risk = inventory_queue_risk(volume_dir)` is taken before `_set_restart_no` / boot fence / unit masking / `docker stop`; `final_risk` is taken after quiescence, and any difference raises `"queue work changed during writer quiescence"`. Ordinary queue progress by the still-live daemon during that window therefore aborts the deploy. Whether this is a real flake depends on what `inventory_queue_risk` counts (not in the packet) — if it counts at-risk/in-flight items rather than total depth it is fine. Direction of failure is safe; availability is the concern. Worth confirming, and worth a comment stating which quantity is expected to be stable across a live-to-quiesced transition.

---

## Low (not blocking)

- `rclone lsf --format "tp"` is `modtime;path`; the comment says `"size;path"` and the variable is named `_size`. Cosmetic, works.
- `DRY_RUN=1` claims to "validate env" but returns before the `LOG_DEST`, `docker`, and `rclone` checks — it prints `LOG_DEST=` and exits 0.
- `file_ts` falls back to `0` on unparseable dates, which sorts *below* any nonzero cutoff and selects for deletion. Currently unreachable (the strict regex gates it, and if `date -d` works for one it works for both), but the fail direction is toward deletion.
- `LOG_CONTAINERS` word-splitting runs without `set -f`, so a glob metacharacter in a container name would expand.
- `ensure_assigned_daemon_claim_context` passes `model_name=authority.provider` — the provider name is recorded as the model.
- Tray launcher: `log = open(...)` is handed to `Popen` and never closed in the parent on the success path — one leaked fd per daemon start.
- `_provider_invocation_carrier` rejects `operation is None` but lets `""` through to `validate_for_call`; the served branch uses `not operation`. Harmless if the carrier rejects empty, but the two guards should match.
- `slack-agent` logs are never archived by `ship-logs.sh` under any default; adding the container to `LOG_CONTAINERS` makes the archive hard-fail whenever the profile is stopped. Consider an explicit `LOG_OPTIONAL_CONTAINERS` list.
- No `fluentd-buffer-limit` on the logging anchor — default ~1MB, silently dropped while Vector is down.

---

## Original-blocker verification

| # | Blocker | Status |
|---|---|---|
| 1 | Valid compose | **Fixed** — parses clean; anchors, profiles, `network_mode: host`, `depends_on` conditions all well-formed. Caveat H1. |
| 2 | Expected daemon count | **Fixed** — `slack-agent` no longer mounts `tinyassets-data` and no other service does, so `expected_containers == {"tinyassets-daemon"}` genuinely holds against the compose. Caveat M5. |
| 3 | Queue preserved | **Fixed** — `preliminary_risk`/`final_risk` compared, `FenceError` on drift, returned `queue_work_preserved: True` is unreachable unless the raise didn't fire. Caveat M12. |
| 4 | Transactional binding/custody + admission held through run | **Fixed** — `BEGIN` … binding rows … `current_serving_authority(conn, …)` … `rollback()` gives one snapshot; the `yield` sits inside `provider_assignment_admission().shared(universe)`, so rotation can't race the post-transaction snapshot. Caveat M1. |
| 5 | Binding and carrier budgets | **Partial** — `ceiling = min(assigned.max_tokens, invocation.max_tokens)` is correct, but M2 (zero accepted) and B1 (scope fields unenforced). |
| 6 | Exact carrier operation | **Fixed** — `type(carrier) is not ProviderInvocationCarrier`, `operation is None` rejected, `validate_for_call(role=…, operation=…)`. |
| 7 | Complete ambient stripping | **Not fixed** — B2. |
| 8 | Optional Slack logs | **Fixed** — `tinyassets-slack-agent` is out of the default `LOG_CONTAINERS`, so the profile-gated service can't trip the new required-container hard-fail. |
| 9 | Truthful status | **Partial** — collection status is now real (missing container, unreadable logs, and generation change all hard-fail; `status` recorded verbatim per container). Undercut by H2 truncation, M7, M8. |
| 10 | Retired kwargs | **Fixed** — `**_retired_options` → `TypeError` naming the offenders. |
| 11 | Claude snapshot | **Fixed** — snapshot resolved through `_resolved_universe_child` (resolve-then-containment, so symlink escapes are caught), non-dir rejected, `.oauth-token` symlink/non-file/empty all rejected, `CLAUDE_CONFIG_DIR` always overridden and `CODEX_HOME` pointed at an empty dir. |
| 12 | No exception chain leak | **Partial** — correct in `subprocess_env_for_provider` (raise outside the handler, allow-listed reason); unfixed in `assigned_credential.py` (B3) and `str(exc)` still returned by the status tool (M7). |

**CHANGES REQUIRED.** B1, B2, and B3 are the gating items; H1 and H2 should land in the same pass.
