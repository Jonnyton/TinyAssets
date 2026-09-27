# Checked-in host recovery paths do not share the deploy mutation lock

**Filed:** 2026-09-26
**Verified:** 2026-09-26, static PR #4039/base comparison and deploy/scripts/workflow search on Windows.
**Severity:** P1

**Source (verbatim review finding):** The claimed shared lock does not serialize
the checked-in daemon watchdog and autoheal with deploy.

This predates PR #4039. `deploy/deploy_fail_safe.sh:178,238` locks
`/var/lock/tinyassets-host-mutation.lock`; `deploy/daemon-watchdog.sh:18,180-181`
instead locks `/run/tinyassets-daemon-watchdog.lock`. Its restart at line 81 can
therefore overlap deploy. `deploy/tinyassets-autoheal.service:18` directly runs
docker restart without taking either lock. `scripts/watchdog.py:185` also issues
a systemctl restart without the deploy lock. No checked-in override connects
these locks; live systemd drop-ins and env overrides were not inspected.

LOCK_WAIT=120 is an acquisition deadline, not an expiry: a lock is not released
after 120 seconds. The problem is distinct lock participation, not that value.

`deploy/tinyassets-daemon.service:79,88` runs compose in ExecStart with a 200s
TimeoutStartSec. `deploy/apply-daemon-env-remote.sh:83` uses this unit to recreate
after an env change, so a 300s drain can outlast the unit's start budget. The
daemon watchdog service itself has a 90s start budget
(`deploy/daemon-watchdog.service:19`). These timeouts kill host control commands;
they do not establish that systemd directly SIGKILLs Docker-managed containers.
The main deploy drives compose outside this unit first, and the unit has no
ExecStop, so a short TimeoutStopSec is not the normal-deploy issue.

Use the shared lock for every actual mutator and align controller deadlines with
the drain. Plain docker stop/restart without an explicit shorter timeout uses
the container's stored StopTimeout, so those commands are not intrinsically a
ten-second bypass after the container has been recreated with the new setting.
