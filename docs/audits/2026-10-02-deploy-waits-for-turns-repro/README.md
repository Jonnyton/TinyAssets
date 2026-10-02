# A merge lands mid-turn: the deploy waits, the turn finishes

**Run:** 2026-10-02 around 01:47Z to 02:00Z, on Windows 11 with Docker Desktop and Git Bash.
**Image:** `tinyassets-linux-oracle:306e17800aee` (Python 3.11.16, FastMCP 3.4.7). The repo
was mounted read-only at `/repo` from the worktree at commit `f61d59dc`.

```
REPRO_IMAGE=tinyassets-linux-oracle:306e17800aee python run.py wait 600
REPRO_IMAGE=tinyassets-linux-oracle:306e17800aee python run.py cap 600
```

## What runs

- **The daemon:** a real FastMCP and uvicorn server. Its `converse` tool holds a real
  interactive seat through `tinyassets.universe_seats.hold`, the same call a chat turn
  makes, for 600 seconds.
- **The deploy check:** the "Wait for in-flight turns" step, extracted verbatim from
  `.github/workflows/deploy-prod.yml`. Only `ssh` and `scp` are swapped for local
  stand-ins. So the real loop pipes the real `scripts/turns_in_flight.py` into the real
  container.
- **The swap:** `docker compose up -d --timeout 20`, as `deploy_fail_safe.sh` does it.

## Results

| variant | wait outcome | waited | turn reply | turn ended before swap | 502 window | new gen serving |
|---|---|---|---|---|---|---|
| wait (cap 2700s) | `idle` | 605s, 102 polls | `TURN_FINISHED gen=1` after 604.8s | yes | 3.6s | 2 |
| cap (cap 20s) | `cap_reached` | 24s, 5 polls | cut off (`RemoteProtocolError`) | no | 21.5s | 2 |

In both runs, `/data/.deploy-pending.json` read `pending: true`, `in_flight: 1` and the
target sha while the step waited.

**The swap got cheaper once it waited.** With no turn left to drain, the 502 window was
3.6s. When the cap forced the swap over a running turn, it was 21.5s, which matches the
20s drain bound from `docs/audits/2026-10-01-deploy-drain-repro/`.

## Rerun after the Codex refute (round 1 fixes)

**Run:** 2026-10-02, about 02:12Z to 02:23Z, same host and image.

This run used the revised probe, which counts seats by holder liveness and also counts
graph runs. The wait now lives in `deploy/wait_for_turns.sh`, and the workflow step only
runs that script, so the repro runs it unchanged.

| variant | wait outcome | waited | turn reply | turn ended before swap | 502 window | new gen serving |
|---|---|---|---|---|---|---|
| wait (cap 2700s) | `idle` | 596s, 105 polls | `TURN_FINISHED gen=1` after 600.0s | yes | 1.4s | 2 |
| cap (cap 20s) | `cap_reached` | 23s, 5 polls | cut off (`RemoteProtocolError`) | no | 21.2s | 2 |

Every busy poll reported the seat as `"holder": "alive"`. That means the flock liveness
probe works inside a real Linux container, against a lock held by the daemon's own process.
