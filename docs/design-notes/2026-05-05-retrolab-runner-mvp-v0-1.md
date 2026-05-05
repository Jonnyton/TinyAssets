---
title: RetroLab Runner MVP v0.1
date: 2026-05-05
status: research
source: pages/plans/retrolab-runner-mvp-v0-1.md
source_issue: 351
---

# RetroLab Runner MVP v0.1

Community wiki source:
`pages/plans/retrolab-runner-mvp-v0-1.md`, retrieved from the live wiki on
2026-05-05. This repository note keeps the proposal visible to coding sessions
without promoting it to canonical `PLAN.md` truth.

## Classification

Request kind: docs/ops.

Smallest useful repo change: preserve the wiki proposal as a tracked design
reference and call out the implementation gates that future runner work must
resolve. No runtime code change is implied by this issue.

## Proposal Summary

The proposal asks Workflow to support chatbot requests like "install retro
game X, make a desktop shortcut, launch it, prove play" by adding a
Windows-side runner that can execute a small set of signed, typed local jobs.

The v0.1 scope is deliberately narrow:

- a signed Windows executable, `retrolab-runner.exe`;
- one-time pairing between the runner and the Workflow service;
- long-polling for signed jobs;
- a closed action allowlist for download, extraction, shortcut, launch,
  screenshot, keyboard-input, and kill operations;
- filesystem writes limited to `%USERPROFILE%\RetroLab\**` and desktop
  shortcuts;
- process launches limited to downloaded emulator executables under the
  RetroLab tree;
- append-only hash-chained local audit logs with periodic server attestation;
- keyboard-only proof, with mouse, gamepad, engine-state decoders,
  non-Windows runners, and paid-market integration left out of v0.1.

## Proposed Runner Surface

The wiki page names these connector and service surfaces as the minimum
runner control plane:

- `runner.list`
- `runner.issue_pair_code`
- `runner.dispatch_job`
- `runner.get_artifact`
- `runner.attest_audit_head`

Primitive collision check, 2026-05-05: namespaced action strings are outside
`scripts/check_primitive_exists.py`'s accepted verb format. Unqualified
`issue_pair_code`, `dispatch_job`, `get_artifact`, `attest_audit_head`, and
`update_filing` are clean on `origin/main`; unqualified `list` collides with
existing list handlers. A future implementation spec should keep runner
listing namespaced at the connector/tool boundary or choose a runner-specific
verb instead of adding another generic `list` action.

The runner itself would expose a closed local job enum:

- `fs_fetch`
- `fs_extract`
- `shell_create_shortcut`
- `shell_read_shortcut`
- `proc_launch`
- `ui_screenshot`
- `ui_send_keys`
- `proc_kill`

Each job is signed by the server, expires, embeds required URL and SHA-256
values, and is rejected by the runner if the signature, expiry, action, path,
or launch target fails validation.

## Acceptance Test Shape

The proposed single v0.1 proof target is Beneath a Steel Sky running through
ScummVM. The wiki page pins ScummVM and game-data downloads by SHA-256 and
defines a canned `bass_proof_v1` workflow branch with five acceptance tests:

- AT-1 bootstrap: fetch and extract ScummVM plus game data, then prove files
  and audit entries exist.
- AT-2 shortcut: create a desktop shortcut and read it back byte-for-byte.
- AT-3 launch: launch only from the shortcut values and prove the process,
  stdout markers, and window title are consistent with ScummVM loading BASS.
- AT-4 in-game objective: send keyboard input, capture screenshots, and prove
  ScummVM's in-game menu responds after the engine has loaded.
- AT-5 no-cheating proof: refuse pass if the launch payload differs from the
  shortcut readback or if any side-door process launch occurs.

Future implementation work should keep these tests as the user-visible proof
contract, but must re-verify all external download URLs, checksums, licenses,
and runner installation paths at build time.

## Relationship To Current Plan

This proposal aligns with `PLAN.md` in two ways:

- `API And MCP Interface` says chat clients are control stations, not the
  source of system truth. The runner would be a daemon-owned execution path
  behind typed connector tools, which matches that principle.
- `Full-Platform Architecture (Canonical)` includes opt-in daemon hosting and
  hostless uptime for authoring. A local runner is an opt-in execution
  capability, not a prerequisite for baseline authoring.

It also adds security-sensitive surface area that is not yet covered by a
canonical design: local executable install, runner identity, signed job
delivery, desktop shortcut manipulation, process launching, screenshot
capture, and keyboard injection.

## Implementation Gates

Before any code implementation is dispatchable, the runner needs a narrower
approved spec covering:

- pairing identity, key storage, revocation, and rotation;
- job schema, signature envelope, expiry, replay protection, and idempotency;
- allowlisted path resolution, reparse-point handling, archive extraction, and
  executable launch policy on Windows;
- artifact upload size, retention, redaction, and user-visible audit access;
- Authenticode, MSI or winget distribution, upgrade, and uninstall behavior;
- license and checksum revalidation for all bundled acceptance targets;
- a threat model for screenshot and keyboard-input abuse;
- final user-surface proof through a real connector conversation, not only
  direct MCP calls or local scripts.

## Missing Wiki Primitive

The source page also reports a wiki-maintenance gap: existing connector
primitives cannot update or supersede an already-filed nested patch request
cleanly. The proposed follow-up primitive is
`wiki.update_filing(filing_id, new_content, reason)`, preserving the filing id,
recording a revision log, and re-running lint.

That primitive is out of scope for this docs/ops preservation change. It
should become a separate bug or project-design lane before implementation.

## First Follow-Up Candidates

1. Write a security/threat-model design note for the Windows runner boundary.
2. Draft the runner job schema and signed envelope as a project-design lane.
3. Create a separate wiki primitive request for updating nested filings.
4. Re-check the BASS and ScummVM legal/download/checksum assumptions before
   any acceptance harness is treated as live proof.
