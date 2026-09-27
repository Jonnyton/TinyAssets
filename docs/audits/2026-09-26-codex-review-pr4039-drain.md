**DISAGREE_EVIDENCE — hold landing.** The central HTTP-lifetime claim fails in a reproducible shutdown test. The increased Docker grace can preserve worker execution, but it does not preserve the MCP reply.

Reviewed head `b74fa73d` against `f4763e8f`.

1. **The three claims**

   **Claim 1 — AGREE, with a first-rollout exception.** [`restart_stack:329`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/deploy/deploy_fail_safe.sh:329) runs `compose up -d`, which stops the old container before starting its replacement.

   **DISAGREE_EVIDENCE:** The newly staged grace does **not** govern the old container during this first rollout. Compose v5.1.3 passes the optional CLI timeout to `ContainerStop`; without `--timeout`, that value is nil. The new `stop_grace_period` becomes the **new container’s** stored `StopTimeout`. An existing container created without it still has the old/default bound. Subsequent recreates benefit. See [Compose recreation:621–622](https://github.com/docker/compose/blob/v5.1.3/pkg/compose/convergence.go#L621), [timeout selection:147–152](https://github.com/docker/compose/blob/v5.1.3/cmd/compose/create.go#L147), and [container configuration:222](https://github.com/docker/compose/blob/v5.1.3/pkg/compose/create.go#L222).

   **Claim 2 — AGREE for uvicorn itself.** It closes listeners, closes idle keep-alives, and waits for active responses and tracked ASGI tasks. [Uvicorn shutdown behavior](https://www.uvicorn.org/server-behavior/).

   **Claim 3 — DISAGREE_EVIDENCE, P1.** The actual chain is:

   `MCP lifespan-owned session runner → awaited AnyIO worker thread → synchronous converse → writer → asyncio.run(coordinator.run())`

   Repository citations: [`universe_server.py:226`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/tinyassets/universe_server.py:226), [`:2866`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/tinyassets/universe_server.py:2866), [`universe_intelligence.py:1051`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/tinyassets/universe_intelligence.py:1051), [`providers/call.py:116`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/tinyassets/providers/call.py:116). The coordinator awaits inference and tools at [`:279`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/tinyassets/agent_turn_coordinator.py:279) and [`:356`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/tinyassets/agent_turn_coordinator.py:356); those operations are not detached there.

   **The break occurs in the transport:** [`universe_server.py:4173`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/tinyassets/universe_server.py:4173) uses FastMCP’s default SSE response mode. MCP creates `EventSourceResponse` without a shutdown-grace override. **sse-starlette intercepts uvicorn shutdown and cancels the SSE response immediately.** See [sse-starlette’s exit handler and response cancellation](https://github.com/sysid/sse-starlette/blob/v3.4.5/sse_starlette/sse.py#L212).

   Local reproduction, using a two-second synchronous MCP tool and five-second uvicorn grace:

   ```text
   HTTP disconnected after 0.486s; tool_finished=False
   server exited after 1.992s; tool_finished=True
   ```

   Disabling automatic SSE termination preserved the complete reply after approximately two seconds. Thus **execution can continue after its response has already been lost**. This directly refutes the claimed request-lifetime guarantee.

2. **`timeout_graceful_shutdown` — DISAGREE_EVIDENCE concerning clean exit**

   The parameter bounds uvicorn’s wait for connections and tracked request tasks. Expiry cancels those tasks; it does **not** force the process to exit or bound subsequent application lifespan shutdown. See [`uvicorn/server.py:287–301`](C:/Users/Jonathan/AppData/Roaming/Python/Python314/site-packages/uvicorn/server.py:287).

   FastMCP’s synchronous worker is awaited through AnyIO. In the same reproduction, setting the uvicorn timeout to **0.25s** still allowed worker/lifespan execution until approximately **1.98s**.

   Therefore [`GRACEFUL_SHUTDOWN_S < stop_grace_period`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/tests/test_deploy_drains_in_flight_turns.py:75) does not establish the asserted clean-exit guarantee. Docker remains the ultimate bound.

   **AGREE:** Ordinary idle keep-alive connections do not consume 290 seconds. An open SSE GET is an active response, but the present SSE shutdown behavior closes streams early—the opposite failure from the proposed idle-connection concern.

3. **Validator refactor — AGREE on the mechanics; DISAGREE_EVIDENCE on enforcement**

   No defect found in moving the image filter. The previous predicate is preserved, `None` becomes empty lists before iteration, and changed diagnostic ordering does not change acceptance. The single heredoc invocation explicitly supplies `MIN_DAEMON_STOP_GRACE_S` at [`:583–585`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/deploy/deploy_fail_safe.sh:583). No missing export found.

   Both rollback routes bypass validation: [`:1208`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/deploy/deploy_fail_safe.sh:1208) and [`:1333`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/deploy/deploy_fail_safe.sh:1333). The new check does not block restoring an older bundle.

   **P2 defect:** [`daemon_block_lines`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/deploy/deploy_fail_safe.sh:659) includes nested descendants, and [`grace_lines:689`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/deploy/deploy_fail_safe.sh:689) accepts any indentation. This passes validation:

   ```yaml
   daemon:
     environment:
       stop_grace_period: 300s
   ```

   My reproduction removed the actual service setting, placed it under `environment`, and obtained **exit 0**. Docker would have no service stop grace. Validate the effective service property, or constrain the source check to direct children.

4. **Duration parsing — DISAGREE_EVIDENCE, P2**

   [`:698`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/deploy/deploy_fail_safe.sh:698) rejects valid equivalent five-minute durations:

   | Source value | Local Compose v5.1.4 | Validator |
   |---|---|---|
   | `300s` | Accepts; renders `5m0s` | Accepts |
   | `5m0s` | Accepts | Rejects |
   | `300.0s` | Accepts | Rejects |
   | `300000ms` | Accepts | Rejects |

   Compound durations are documented Compose syntax. [Docker service reference](https://docs.docker.com/reference/compose-file/services/#stop_grace_period).

   This is a maintenance foot-gun, although **the current `300s` source passes**, and reading source avoids automatic refusal merely because Compose renders `5m0s`.

   Conversely, bare `300` and quoted `"300"` pass the extracted validator but fail actual Compose validation. The preceding Compose command catches them. The new tests’ claim to cover every accepted duration form is inaccurate.

5. **Job budget — DISAGREE_EVIDENCE, P1**

   The configured allowances exceed the job limit:

   ```text
   forward drain       300s
   forward health      180s
   rollback drain      300s
   rollback health     180s
                       ----
                       960s > 900s
   ```

   Evidence: [`timeout-minutes: 15`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/.github/workflows/deploy-prod.yml:68), [`HEALTH_TIMEOUT=180`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/.github/workflows/deploy-prod.yml:345), forward converge/accept at [`:1306`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/deploy/deploy_fail_safe.sh:1306), rollback at [`:1349`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/deploy/deploy_fail_safe.sh:1349). Even substituting 290-second drains gives **940 seconds**.

   Pull, import, validation, snapshot, startup and canary add overhead. Image build is actually a separate workflow.

   **DISAGREE_CONCERN:** Exact remote behavior when Actions terminates SSH remains unverified. I cannot prove cancellation necessarily interrupts bundle installation. But the only EXIT trap performs temporary-file cleanup at [`:405`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/deploy/deploy_fail_safe.sh:405); it does not guarantee transactional recovery.

6. **Watchdog/systemd — DISAGREE_EVIDENCE, with pre-existing defects distinguished**

   **The shared-lock premise is false in checked-in code.** Deploy locks [`/var/lock/tinyassets-host-mutation.lock`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/deploy/deploy_fail_safe.sh:178). The daemon watchdog locks [`/run/tinyassets-daemon-watchdog.lock`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/deploy/daemon-watchdog.sh:18). Autoheal’s [`ExecStart`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/deploy/tinyassets-autoheal.service:18) takes neither lock. This predates the PR, but a longer drain enlarges the overlap window. Live overrides were not inspected.

   **AGREE:** `LOCK_WAIT=120` is an acquisition timeout, not a lease expiry. It never releases another process’s lock after 120 seconds.

   **Additional deadline mismatch:** [`tinyassets-daemon.service:88`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/deploy/tinyassets-daemon.service:88) allows only **200s for ExecStart**. Env changes use that unit through [`apply-daemon-env-remote.sh:83`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/deploy/apply-daemon-env-remote.sh:83), so a 300-second recreate can exceed its controller deadline. The daemon-watchdog service allows only [90s](C:/Users/Jonathan/Projects/wf-drain-before-recreate/deploy/daemon-watchdog.service:19).

   These timeouts affect host control commands; they do not prove systemd directly SIGKILLs the Docker-managed daemon. Normal deployment invokes Compose outside the unit first. There is no daemon `ExecStop`, so a short `TimeoutStopSec` is not the normal-deploy problem.

7. **Other stop routes — AGREE; no additional shorter-timeout bypass found**

   Watchdog and autoheal use plain `docker restart`; [`backup-restore.sh:282`](C:/Users/Jonathan/Projects/wf-drain-before-recreate/deploy/backup-restore.sh:282) uses plain `docker stop`. These honor the container’s stored stop timeout once the new setting has been installed. [Docker restart timeout semantics](https://docs.docker.com/reference/cli/docker/container/restart/#stop-container-with-timeout--t---timeout).

   The first-rollout caveat and controller deadlines above remain relevant.

Verification on **2026-09-26, local Windows/Python 3.14**: the two PR-focused modules passed **52 tests**, and SSE keepalive tests passed **3**. The shutdown reproduction used FastMCP 3.2.0, MCP 1.28.0, uvicorn 0.49.0 and sse-starlette 3.4.5; production versions were not inspected.

I recorded findings in `docs/concerns/` and saved the [shutdown reproduction](C:/Users/Jonathan/Projects/wf-drain-before-recreate/docs/audits/2026-09-26-pr4039-drain-repro.py) plus validator/Compose reproductions. Production code is unchanged.