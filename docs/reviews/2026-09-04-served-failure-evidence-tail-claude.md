# Provider failure evidence review — Claude, 2026-09-04

Base: `bb100f9cc79d9d7a91eb1abac4f86a55b20e2103`.
Review scope: three canonical runtime files, their plugin mirrors, and the
focused failure-notice tests. Checklist logs and concern records are supporting
evidence, not runtime changes. No runtime edits followed round-two approval.

## Round 1: ADAPT

Source transcript: `718529e5-2ba1-4ebc-b0ac-bfd26519533d`.
The reviewer found seven earlier prefix cuts in the provider router. A
server-recorder-only repair would see a detail already truncated to 200 and
would not repair the observed loss. Requested one shared scrub-before-cut
helper, a real-router regression, and a secret crossing the cut boundary.
All three requests were implemented. The real-router regression was run red
against the old router, then green with the repair.

## Round 2: APPROVE

Source transcript: `03312e41-bd2d-4884-bb14-98166c2de5e4`.
The wrapper output retains closing-hook text; the review body was recovered
from this completed transcript.

AGREE: all seven failed-attempt constructors use the shared helper; complete
details are scrubbed before clipping; existing bounds hold; the quick-exit
provider's terminal cause survives through the router to the recorder; all
three plugin mirrors match. Scrubbing earlier also protects diagnostic details
that propagate through chain state. Auth, routing and private state are untouched.

Independent Windows 11 / Python 3.14.3 verification:
`python -m pytest -q -p no:cacheprovider tests/test_a_failed_turn_says_what_actually_happened.py --basetemp=C:/Users/Jonathan/AppData/Local/Temp/ta-pt-r2`
reported 42 passed in 5.46 seconds.

Non-blocking residuals: other provider-level empty-stdout paths still prefix-cut
stderr before the router; helper budgets below five would be invalid, but all
three fixed call sites use 160, 200 or 300. Neither affects the observed quick
exit path. No sub-agents, peer dispatches, edits or broad suites were used.

VERDICT: APPROVE
