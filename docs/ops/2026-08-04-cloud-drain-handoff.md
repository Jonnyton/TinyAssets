# Cloud drain handoff — 2026-08-04

## Current truth

- Local tray/drain is stopped. Do not start it; the intended cutover is cloud-only.
- Production is healthy after deploy run `30954336142` for image/main `c291a875`.
- GitHub/WorkOS connection is complete:
  - destination: `Jonnyton/TinyAssets`
  - grant: `pipes_grant_26eb1ab80dd8ecf0202a3b4f69a17081`
- User-owned provider binding is active after rebind:
  - binding: `pwb_fbddd0e8b76b837a266488a23403f0b3`
  - generation: `4`
  - provider: `claude-code`
  - budget: `max_invocations=64`, `max_cost_microunits=64`
- Published drain branch: `745e637dd8fb@99cb5a8f`.
- No cloud automation has been created or resumed yet.

## Changes landed

- PR #2277: documented `operation=rebind` alias.
- PR #2283: provider rebind CAS recovery for revoked bindings.
- PR #2284: include revoked bindings when selecting a rebind target.
- PR #2286: normalize GitHub destination comparison (`owner/repo` vs `github.com/owner/repo`). **Open; required checks were still running when this handoff was written.**

## Why creation is paused

The create path successively exposed three real issues: a stale revoked provider binding, an enrollment invocation cap mismatch, and a destination normalization mismatch. The first two are deployed and verified. PR #2286 contains the final destination fix; do not keep retrying create against the old image.

## Resume procedure

1. Wait for PR #2286 to merge. Verify all required checks pass.
2. Build and deploy main (workflow IDs: build `263326511`, deploy `263326512`).
3. Rebind once from the phone/Claude connector using:
   `write_graph target=automation operation=rebind payload_json={"provider":"claude-code"}`
4. Create exactly one **stopped** automation using:
   - repository `jonnyton/tinyassets` (canonical normalized form)
   - accepted spec ref `openspec/changes/activate-main-universe-spec-drain`
   - branch version `745e637dd8fb@99cb5a8f`
   - cadence `300`
   - `max_cost_microunits=64`
   - operator `TinyAssets Cloud Drain`
5. Verify `automation_id` and `desired_state=stopped`; then resume it once with `write_graph target=automation operation=resume`.
6. Verify `read_graph target=automations` shows one active automation, then inspect `get_status`/health for at least one bounded slice and PR attempt. Keep local drain stopped.

## Evidence and cautions

- Focused local verification: provider authority `62 passed`; cloud/user-owned automation focused suite `87 passed`.
- Public production deploy/canary succeeded for the deployed image.
- The browser connector is the authenticated control surface; no OAuth reauthorization is currently required.
- Do not claim 24/7 cloud operation until an active automation and a post-resume cloud slice are observable with the computer off.
