---
severity: P2
title: Daily budget exhaustion cannot schedule an interactive conversation continuation
filed: '2026-10-02'
---

The pooled-budget slice inspected resume primitives before implementation, as requested.
`tinyassets/automations.py:1344` exposes `register_automation` with `not_before` and an
idempotent `event_key` (lookup at line 1371), but requires a `branch_def_id`.
Lines 1405-1416 resolve that existing Branch and require its author to be the owner.
`tinyassets/shared_self.py:1` describes the same owner-authored Branch requirement;
`prepare_shared_self_turn` at line 103 prepares a turn, not a scheduled conversation.

An interactive served conversation has no such Branch. No applicable primitive was
found for arming a later conversation turn from its journal or prompt. The slice
therefore does not invent a scheduler, create a Branch, or promise an automatic wake.
The final inference is told the earliest source reset and the alternative of connecting
more compute. A later user turn can continue from the conversation and saved notes.

Progress-note creation remains an instruction to the model before the text-only final
request; the platform's journal preserves every completed round independently. The
scripted request-count tests prove control flow, not that a real model obeys the save
instruction. With only one request at turn start, no model tool call remains available.
