# Tasks: target-architecture (umbrella)

This change tracks slices; each checkbox is one slice. A slice is opened as its
own delivery change (≤12 tasks, one owner, one PR) from the brief in
`design.md` §Slice plan, and its box here is ticked only when that change is
**landed, deployed (`deployed_sha.py --assert-contains`), live-verified and
archived**. Spend marks name the founder approval the slice needs before any
paid resource is created. Dependencies are in `design.md`.

## Start now (parallel)

- [ ] S0 DigitalOcean nested-KVM validation on a short-lived staging droplet;
      decision rule in design §S0. **Founder spend:** staging droplet ~$0.14
      (or approve a quiet-window production benchmark instead). Verify: numbers
      plus commands recorded; D1 and PLAN updated with the decision.
- [ ] S1 Durability foundations and warm standby: SQLite ≥3.51.3, Litestream
      off-region, off-region backups, weekly DR drill from the off-region copy,
      fenced standby promotion. **Founder spend:** bucket ~$0–5/mo, standby
      droplet $12–24/mo, Cloudflare LB ~$5/mo. Verify: drill green from
      off-region; promotion drill ≤5 min after detection.
- [ ] S2 Platform state out of the universe directory (`PlatformStatePaths`,
      §4.16, concern #4258). Verify: the three #4258 reproductions fail in the
      Linux oracle; no jail mounts the platform root.
- [ ] S8 Always-on control plane under a leadership lease, coalescing and
      cadence decay, blue-green deploys. Verify: scripted deploy loop shows 0 s
      origin-down and no duplicate effects.

## Boxes

- [ ] S3 One accessor for command-center content (local `BoxProvider` driver
      over `universe_files.py`) and the change-generation hot-path cache.
      Depends on S2. Verify: ratchet at 0 direct opens; no turn-latency
      regression.
- [ ] S4 `BoxProvider` + `boxhostd` + `boxd` + gVisor driver; tool runner and
      provider launch re-pointed. Depends on S3. Verify: driver contract suite
      green in CI; tool loop end to end through a box on staging.
- [ ] S5 Firecracker driver, grow-only disk allocator, snapshot/suspend,
      Debian 13 box host, restic box backups. Depends on S0, S4. **Founder
      spend** if S0 picks bare metal (OVH RISE-S $77/mo). Verify: contract
      suite green on both drivers; restore p95 meets S0's rule.
- [ ] S6 Egress proxy as credential injector; per-process secret scope;
      owner-scoped Claude subscription gate (default off). Depends on S4.
      Verify: no real credential in any box or loop process (asserted).
- [ ] S7 Thin agent loop in the control plane (HTTP protocols, box handle bound
      at turn start, CLI-in-box only where a credential needs it). Depends on
      S4, S6. Verify: live rendered conversation (`ui-test`); waiting-turn
      memory measured.
- [ ] S9 Usage limits on the box lifecycle: metering, seat + host-capacity
      admission replacing the 4-run pool and tool slots, spare-capacity lane.
      Depends on S4 (S5 for Firecracker metering). **Founder decision:** the
      compute-hour numbers before any limit ships. Verify: one account's
      fan-out never delays another's admission.

## Shared stores and cutover

- [ ] S10 Postgres for catalog/ledger/inbox/market (`TransactionalStore`),
      outbox, identity map, `home_cell` + signed cell claim + ownership
      generation + ingress dedup (one cell). **Founder spend** only if managed
      Postgres ($15.15–30.30/mo; self-hosted $0). Verify: simulated move
      between two local cells passes generation and dedup tests.
- [ ] S11 Cutover from shared `/data/<universe>` to sealed boxes, in the
      `command-center-cutover` window if open: derived inventory, locked
      verified run, flip, rollback rehearsal, export and deletion through the
      box, retire bwrap jails and host-path drivers. Depends on S2, S3, S5,
      S6, S7. Verify: every command center serves from its box; public canary
      `--assert-handles` and a rendered conversation green; DR drill restores
      boxes; then sync specs and archive this change.
