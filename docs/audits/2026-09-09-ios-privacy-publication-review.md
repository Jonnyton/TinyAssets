# iOS privacy publication cross-family review — 2026-09-09

Scope: the public `/legal/#privacy` status and effective-date change for App
Store submission.

An independent Claude peer reviewed the uncommitted diff read-only under a
no-subagent, no-edit, bounded-review contract. Its verdict was
`DISAGREE_EVIDENCE` for two related copy issues:

1. the page header paired the new privacy version with the older terms effective
   date; and
2. the status could imply that the privacy notice had received counsel approval,
   while the page footer truthfully says counsel review is pending.

Both findings were folded in before landing. The header now labels the privacy
and terms dates separately. The status describes privacy publication as an
operational disclosure and explicitly says counsel review of the page remains
pending. The unsupported phrase claiming live operational verification was also
replaced with the narrower, evidenced statement that the notice was reviewed for
publication. The reviewer stated that these edits resolve the blocking finding
without requiring a second review round.

The peer additionally confirmed that the privacy section names iOS and covers the
four declared data categories, recipients, protection, retention, deletion,
analytics, minimum age, and contact; that the `#privacy` anchor is suitable for
App Store Connect; and that no hidden availability claim was introduced.

Author verification before review: site node tests passed (233 pass, four
platform-specific skips), the Next static build passed, the phone/desktop rendered
sweep reported zero errors, warnings, or overflow, and both `/legal/` captures were
visually inspected. The same build-and-sweep gate was rerun after the copy fix.
