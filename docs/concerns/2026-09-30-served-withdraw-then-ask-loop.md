---
severity: P2
title: A served turn withdrew and re-raised the same ask three times
filed: 2026-09-30
summary: On the free account, turn 02:07Z ran write_graph pending_request withdraw then ask on the same request three times in a row, and each call used up one of about fifty daily requests. The cause is not diagnosed yet.
---

# A served turn withdrew and re-raised the same ask three times

**Found:** founder's live evidence, 2026-09-30. Free account
`u-01ky3zh1arr8qth8jee7zx63pq`, OpenRouter `:free` models, `agent_turn_tools`
in `/data/.tinyassets.db`, turn 2026-09-30T02:07Z.
**Area:** `tinyassets/engine_mcp_server.py` (`write_graph target=pending_request`),
`tinyassets/api/pending_requests.py` (`request_from_user`, `withdraw_request`).

## What happened

In one turn the model called `withdraw` and then `ask` on the same pending
request, three times in a row. On an OpenRouter free account every round spends
one of the roughly fifty requests the whole account gets per day.

## Why it was not fixed with the tool-contract PR

The obvious fix is to make withdraw followed by an identical ask idempotent, or
to return guidance saying "you withdrew this identical ask N seconds ago". That
guesses at the cause. The evidence the founder summarized does not show what
each call returned, so it is still unclear which signal sent the model back:

- an `ask` that deduplicated onto the still-live row. The row comes back
  without `created`, and the model may read that as a new tab
- a `withdraw` whose `still_on_rail: true` read as "the withdraw failed"
- a refusal that was flagged `isError: false`. The tool-contract PR now flags
  refusals as errors, which may remove the loop on its own

## What would settle it

Pull the six `agent_turn_tools` rows for that turn (request and `result_json`).
If the loop does not recur after the `isError` change deploys, delete this file.
If it recurs, fix the specific signal in whichever result misled the model.
