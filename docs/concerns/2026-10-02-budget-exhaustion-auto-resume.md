---
severity: P2
title: Automatically resume saved work after pooled budget reset
filed: '2026-10-02'
summary: Budget exhaustion gives reset guidance but cannot yet arm a supported activity continuation. Wire the one-shot WakeTarget after Activities PR 4221 lands.
---

**Filed:** 2026-10-02
**Severity:** P2

## Source (verbatim)

> dots-research confirmed the supported resume primitive, starting an activity via tinyassets.api.activities.write(..., operation="start"), is in #4221, which is not on main. Do NOT target the Activities branch with an automation either: #4221 refuses runs no activity names.

Evidence supplied by the founder for this follow-up slice. The existing
`register_automation` path requires an existing owner-authored Branch; it does
not directly resume an interactive conversation. No reset automation is armed.
The current fallback tells the owner the earliest capped-source reset in UTC,
with a relative time, and that connecting another source can continue now.

## Follow-up

Once #4221 lands, coordinate with **dots-research** (activity start contract) and
**cp-scheduler** (control-plane WakeTarget). Arm a one-shot WakeTarget at the
**earliest reset among the capped sources**, calling:

```python
activities.write(
    operation="start",
    payload={
        "title": "Resume after the budget reset",
        "brief": "continue the work saved in notes/<project>-progress.md",
    },
)
```

Bind the wake to the owning command center and the actual saved project note.
Do not schedule a run against the Activities branch: #4221 refuses runs with
no activity names. Confirm the supported start primitive after it lands.

Progress-note creation remains a model instruction before the text-only final
request; the journal independently preserves completed rounds. Scripted tests
prove dispatch and guidance, not real-model compliance with saving a note. With
only one request at turn start, no tool call remains available to save a note.
