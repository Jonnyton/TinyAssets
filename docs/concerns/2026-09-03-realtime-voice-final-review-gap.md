# Realtime voice has no post-fix exact-head approval

**Filed:** 2026-09-03
**Verified:** 2026-09-03
**Severity:** P2
**Surface:** draft PR #2797, provider-neutral first-class voice

## Source (verbatim)

> Verdict unchanged. Findings 1–14 as given above; finding 1 is the sole blocker,
> findings 7–12 are non-blocking and should go to the founder with this receipt
> rather than trigger a fourth round, per `AGENTS.md` "Three rounds, then
> escalate."
>
> REVIEWED_HEAD: 20cc50e0020154d981ef83ebd1cff21123f2de0c
> VERDICT: ADAPT

The saved final response contained no preceding findings 1–14 beyond its prose
description of finding 1.

## Re-verification

Claude Opus review round three examined commit
`20cc50e0020154d981ef83ebd1cff21123f2de0c` and returned `ADAPT`. Its sole stated
blocking defect was a stale connection attempt closing a replacement transport.
That defect is fixed and regression-tested in the subsequent branch head.

The third-round receipt also referred to numbered non-blocking findings 7–12 but
omitted their content from the saved response. The three-round cap forbids a
fourth review, while the high-risk landing rule requires an `APPROVE` receipt for
the unchanged head. Therefore PR #2797 must remain draft and unmerged unless the
founder explicitly resolves this gate. All voice flags remain off; no platform
credential, shared billing authority, or user-owned bridge has been supplied.

Resolution requires a founder decision on whether the repaired, green branch may
land dark despite the capped review ending `ADAPT`. Production enablement remains
separately blocked on an already-bound user-owned `tinyassets.voice.v1` resource,
an authenticated public canary, rendered live-connector proof, and a physical
device microphone pass.
