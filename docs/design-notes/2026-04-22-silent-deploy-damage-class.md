---
status: research
---

# Silent deploy-damage: class-of-bug + 24h-asleep-host survivability

*Date:* 2026-04-22. *Author:* navigator. *Triggering incident:* ~18h dark on
`tinyassets.io/mcp` starting 07:22 UTC 2026-04-21, rooted at `deploy-prod.yml`'s
`sudo sed -i` silently regressing `/etc/tinyassets/env` from `640` to `600` —
unit runs as `User=workflow`, file became unreadable, `docker compose`
crash-looped 67 times, cloudflared never came up. Zero alarms paged the host.

Scope per lead: *what does the platform need to survive the host being asleep
for 24h?* Not a full ops redesign.

Three-layer chain-break reading: this is a clean *Interface-1* break — System
clobbered its own critical-path file in a way the Chatbot and User can never
see or route around. Every layer downstream was healthy but starved. The
platform's uptime promise to Tier-1 chatbot users failed because the system
stopped telling the truth about itself *and* stopped noticing it had.

---

## (a) Audit — where else does this pattern live?

Pattern signature: **root-owned, group-readable file whose perms matter for a
non-root daemon to run, mutated by `sudo sed -i` / `tee` / temp-file-and-rename
/ recreate-from-template, without an explicit `chown` + `chmod` + read-assert
follow-up.**

### Confirmed matches (same umask shape)

1. **`deploy-prod.yml:136` Deploy new image** — *original P0 site.*
   Now patched (`deploy-prod.yml:142-152` has chown + chmod + `sudo -u workflow
   test -r` assertion + a second out-of-band assertion step `:162-172`).
   This is Task #1. The fix is correct for this one call site.

2. **`deploy-prod.yml:127-131` Scrub legacy Windows WIKI_PATH** — same `sudo
   sed -i` shape. **Patched in the same commit** (chown + chmod follow the
   sed, line 131) but has **no `test -r` assertion**. If sed succeeds but
   chmod fails (e.g. transient sudo/`visudo` regression, disk full, readonly
   FS), the scrub step exits 0 and the next step deploys onto a broken file.

3. **`deploy-prod.yml:209` Rollback on failure** — same `sudo sed -i` on
   `/etc/tinyassets/env`. **Patched** (chown + chmod at 210-211, no `test -r`).
   Same concern as #2: missing read-assert. **Rollback is the worst place for
   a silent regression** — it fires only when something is already wrong, so
   a second silent break here extends an outage instead of shortening it.

4. **`p0-outage-triage.yml:98-102` Attempt compose restart** — does not
   mutate env, but does `docker compose ... --env-file /etc/tinyassets/env`.
   If env perms are already bad (as in the 04-21 incident), compose silently
   re-fails. Triage path has **no env-readable precheck** — it would have
   looped the same failure the deploy did. This is why the auto-triage
   never closed the issue during the 18h window (assuming the label fired).

### Not matches but nearby

5. **`hetzner-bootstrap.sh:195-200`** — env creation path has *explicit*
   `chown` + `chmod` immediately after `cp`. Correct. The risk is only on
   the *first bootstrap*; not a re-entrant mutation hot-path.

6. **`hetzner-bootstrap.sh:248-256`** — sudoers file install uses
   `echo > ... && chmod 0440 && visudo -c -q`. Correct: perms are set
   explicitly *and* verified. Good template.

7. **`backup.sh` / `backup-restore.sh`** — no `/etc/tinyassets/env` mutation.
   `backup-restore.sh:133` does `rm -rf ${VOLUME_DIR:?}/*` before extract,
   which is aggressive but on the restore volume, not critical-path config.
   Out of scope.

8. **`ship-logs.sh`, `workflow-*.service/timer`** — no env-file mutation.
   Clean.

9. **`dr-drill.yml`** — only `chmod`s SSH keys (`600`/`700`), which is the
   correct target mode for those files. No /etc/tinyassets/env touches.

### Latent risk the patch doesn't cover

Any **future** script that edits `/etc/tinyassets/env` (or its sibling files
under `/etc/tinyassets/`) has no structural reason *not* to drop perms. The
knowledge "sed -i on this file breaks the daemon" lives in a comment at
`deploy-prod.yml:121-126` — a tribal-knowledge defense, not a structural one.

---

## (b) Structural fix beyond the point patch

The Task #1 patch is correct but it is **a point fix on one call site of a
class of bug**. Three layers of structural defense, each cheap and each
catching a different failure mode:

### 1. Editor helper — `deploy/edit-env.sh`

A single sanctioned mutator for `/etc/tinyassets/env` (and any future
permission-sensitive config under `/etc/tinyassets/`). Takes a sed expression
or key-value pair. Contract:

- `sed -i` against a tempfile in `/etc/tinyassets/` (same filesystem, atomic rename).
- `chown root:workflow` + `chmod 640` on the temp before rename.
- `sudo -u workflow test -r /etc/tinyassets/env` **after** rename.
- Any failure = exit non-zero + `ls -l` the file to stderr.

Every GHA step that currently calls `sudo sed -i` on env becomes
`sudo /opt/tinyassets/deploy/edit-env.sh KEY=VALUE`. The structural invariant
moves from tribal-knowledge comment into executable code that exists on the
box and is test-covered. Bootstrap installs it as part of Row D.

Cost: ~40 LOC of bash + one unit test. Payoff: no future call site can
accidentally recreate the P0.

### 2. Pre-commit / CI invariant — "no raw `sed -i` on /etc/tinyassets"

A simple grep-level lint added to pre-commit + GHA PR gate: fail if any
shell / YAML file outside `deploy/edit-env.sh` itself contains `sudo sed -i
.*/etc/tinyassets`. This is the `invariant-5` pattern already in use for env
var reads (per AGENTS.md "Configuration — environment variables"). Cheap,
structural, self-documenting.

### 3. Startup self-check in the daemon

`compose.yml` / container entrypoint: at boot, if the `EnvironmentFile`
was supplied but is unreadable from inside the container, fail **loudly** —
log a distinct error marker (`ENV-UNREADABLE`) and exit non-zero with a
message that names the file and the expected mode.

This closes the Docker-silent-crash-loop failure mode. Today compose sees
the file-not-readable error, systemd's `Restart=always` retries, the
journal fills with identical failures, but the user-visible signal is only
"cloudflared sidecar never healthy." An `ENV-UNREADABLE` marker:

- Can be grepped by watchdog.py as a fast-fail signal (see §c below).
- Surfaces in `journalctl -u tinyassets-daemon` immediately, cutting
  first-manual-diagnosis time from ~minutes of reading crash dumps to
  one-line.
- Makes ship-logs.sh alerts interpretable without SSH.

---

## (c) Alarm gap — surviving host-asleep for 24h

### What failed

- Uptime canary fired every 5 min for 18h. Issue opened at threshold-cross
  (10 min in). **No paging layer.** GitHub emails the host's inbox, but
  the host was asleep for ~8h of the window and the notification was
  indistinguishable from normal repo noise for the other ~10h.
- P0 auto-triage fired and *restarted compose* — which, against an
  unreadable env, crash-looped again. Triage `if: steps.reprobe.outputs.color
  == 'red'` added `needs-human` label. That label does not page.
- Watchdog on the box runs `systemctl restart tinyassets-daemon` on 3
  consecutive reds. Same underlying cause (env file unreadable) → same
  re-crash. Watchdog is blind to config-bricked states by design.

Three independent self-heal layers all failed for the same reason:
**they all assume "restart will fix it."** It doesn't when the thing
that's wrong is on the filesystem, not in memory.

### What to add (prioritized, 24h-survivability-scoped)

**P0 — A paging path.** GitHub-issue emails are not a pager. The cheapest
structural change is a third-party pager hooked to the `p0-outage` label.
Options in descending minimalism:

- **Pushover** (~$5 one-time): single API call from alarm-sink step when
  the issue is opened. Ringing alert to host's phone. Fewest moving parts.
- **ntfy.sh** (free, self-hosted or public): same shape, HTTP POST to a
  topic, phone subscribes. No account needed.
- **Twilio SMS** (~$0.01/msg): more robust delivery, adds a vendor.
- **Existing GoDaddy-hosted SMTP** → a phone carrier's SMS gateway
  (`number@txt.att.net` etc.): uses infra we already have, but gateways
  are deprecating.

Recommendation: **Pushover**. One-time $5, zero ongoing cost, works with
a single `curl` line from the existing `alarm-sink` step. Secret
(`PUSHOVER_TOKEN`, `PUSHOVER_USER`) into GH Actions secrets. Same label
that opens the issue triggers the push.

**P1 — Smarter consecutive-red escalation.** Current alarm fires at 2
consecutive reds (10 min). That is correct for *opening* an issue.
What's missing: **escalation after N=12 reds (1h) with no human ack.**
`alarm-sink` already runs every tick. Add: if `openIssue` exists AND
its `created_at` was >1h ago AND no human comment (non-bot actor
comment) has landed, re-page. At N=48 reds (4h), re-page with
"CRITICAL — 4h outage." This converts the alarm from a single-shot
email into an escalating signal without any new infrastructure beyond
the pager.

**P2 — Self-repair attempt for known-class failures.** Given the
`ENV-UNREADABLE` marker from §b.3, extend `p0-outage-triage.yml` with a
**"before restart, try the known-class fixes"** step:

- If `journalctl` contains `ENV-UNREADABLE` → run the known good
  `chown root:workflow /etc/tinyassets/env && chmod 640 /etc/tinyassets/env`.
- Then restart. Then reprobe.

This turns the specific class of failure (`/etc/tinyassets/env` perms) from
*needs-human* into *auto-healed*, closing the exact 04-21 P0 path end-to-end.
Other classes stay `needs-human` — we don't generalize; we encode what
we've seen.

### What I am *not* recommending

- **On-box pager.** Host-box-dependent. Defeats the goal.
- **Third-party uptime monitor (Pingdom/etc).** Adds a vendor for a
  signal we already generate. Uptime-canary on GHA is the right vantage;
  the gap is the notification delivery, not the probe.
- **SMS/paging from the droplet itself.** Same host-fate-sharing failure
  mode as the old Windows Task Scheduler canary.

---

## PLAN.md entry point

Alarm-path architecture is not explicitly in PLAN.md today. The closest
section is the uptime / complete-system-24/7 forever rule (AGENTS.md
top-of-file) and the `observability + uptime` env var table
(`TINYASSETS_MCP_CANARY_URL`, `TINYASSETS_DEPRECATIONS`, `TAB_WATCHDOG_*`).

Proposed new PLAN.md module heading (for host approval):

> **§ Alarm path — out-of-band notification to humans.** The only layer
> that must survive host-asleep-for-24h. Runs on GitHub infrastructure,
> not on any host machine. Two signals: (1) new `p0-outage` issue →
> pager + escalation timer, (2) escalation re-page at 1h / 4h / 24h
> unacked. Not replaced by on-box watchdog (which handles in-memory
> faults). Distinct from canary (which is the signal source). Testable
> assumption: "If the host's phone is off for 24h, a second pager path
> (email, desktop, secondary device) still fires at the 4h escalation."

Requires host approval before navigator adds. Batch with the open host-Q
queue rather than sending one-off.

---

## Summary for the lead

- **Audit:** 3 confirmed matches of the pattern, all in `deploy-prod.yml`.
  Task #1 covers the one with the `test -r` assertion; two sibling sites
  (WIKI_PATH scrub, rollback) are chmod-patched but missing the assertion.
  Worth folding into Task #1 scope.
- **Structural fix:** `deploy/edit-env.sh` + pre-commit invariant + daemon
  entrypoint `ENV-UNREADABLE` marker. Three cheap layers, each closing a
  different future failure mode. ~half-day of dev work total.
- **Alarm gap:** *paging* is the gap, not probe smartness. Pushover
  ($5 one-time) via alarm-sink step; escalation timer at 1h/4h unacked;
  known-class self-repair in auto-triage using the `ENV-UNREADABLE`
  marker. PLAN.md deserves a new §Alarm-path module — draft above
  for host approval.
