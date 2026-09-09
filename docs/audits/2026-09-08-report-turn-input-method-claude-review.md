# Turn input method — Claude review

Date: 2026-09-08  
Writer: Codex  
Reviewer family: Claude (opposite-provider)

## Round 1 verdict

**ADAPT.** The reviewer agreed with replacing the ambiguous Voice-session flag
with per-turn provenance and found three gaps in the first implementation:

1. Request-rail replies and generated action lines did not report their actual
   origins.
2. Rejection of the removed `voice_active` field was tested only at the Python
   signature rather than at the public FastMCP boundary.
3. Spoken-turn coverage depended partly on source assertions rather than the
   browser harness executing the voice send path.

The reviewer also noted that an already-open app tab using the removed field
will fail after deployment until the app's build checker reloads it. This is the
intentional result of the founder's no-compatibility decision, not a fallback to
preserve.

## Adaptations

- Typed request-rail replies now report `typed`; founder-selected controls that
  generate a conversation line report `app_action`.
- The closed public enum is `typed`, `spoken`, `app_action`, or `unknown`.
- A FastMCP tool-call test proves `voice_active` is rejected as an unexpected
  argument.
- The browser harness now executes the shared voice send path and proves it
  reports `spoken`, while a composer submission made during an active Voice
  session still reports `typed`.
- Queue, retry, and restored-record tests prove provenance is preserved, with
  `unknown` used only when an older record contains no provenance to report.

Round 2 reviews the resulting commit. Its exact-head verdict is recorded in the
pull request so adding the verdict cannot itself invalidate the reviewed SHA.
