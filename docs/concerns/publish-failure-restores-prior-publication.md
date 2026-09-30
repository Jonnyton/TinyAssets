# Failed publish should restore prior publication state

2026-09-30, PR #4107 cross-family verification review: AGREE, P2 correctness.
`tinyassets/api/publish_requests.py:execute_action` clears every confirmed version's
publication mark and `_unflip` makes every branch private when bundle storage fails.
If a branch or identical version was already public before this request, that
withdraws an earlier publication too. This reduces exposure and does not bypass
consent; it is separate from P1-a/P1-b. Follow-up: record prior visibility/published
flags and version marks and compensate only this request's changes, with a test
for an already-public branch/version and a failed bundle write.
