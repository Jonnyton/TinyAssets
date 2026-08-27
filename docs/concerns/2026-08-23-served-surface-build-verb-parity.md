# P1 - Served-agent BUILD verb parity is partial

**Filed:** 2026-08-23 | **Verified:** 2026-08-24 | **Severity:** P1

> Migrated verbatim from `STATUS.md` on 2026-08-25 when the board was retired.
> Source dates preserved. Premise re-verified against `origin/main` @ `8cbf9769`.

## Source (verbatim)

Surface parity (served agent BUILD verbs) - PARTIAL. CLOSED: `connect_compute` (#2491/#2492),
`run_graph` RUN (sanitized invoke_branch #2498), and `write_graph target=branch` **CREATE-only**
(sanitized handler #2509, live-verified `30820c2e` running_healthy). STILL missing on the served
surface: `write_graph` PATCH/edit, `connect_http` (secret deposit), consent
(`grant_effector_consent`), serving-control (`set_engine`/`bind_serving_provider`), remix.
Remaining "all surfaces do the same things" gap - authority/RCE-sensitive -> OpenSpec+Codex before
exposure. Pre-second-user harden gate for the shipped create: force-unapproved build mode +
branch<->universe binding. Also: no read surface for provider definitions yet.

## Why it is not just a feature gap

Every missing verb is authority-sensitive. Adding them to the served surface widens an RCE-adjacent
boundary, which is why the row carries its own gate: OpenSpec change plus Codex review **before**
exposure, not after.

## Pre-second-user gate for what already shipped

`write_graph target=branch` CREATE is live. Before a second real user: force-unapproved build mode,
and an explicit branch<->universe binding.

## Owner

`openspec/changes/served-agent-build-run/design-hardening.md`
