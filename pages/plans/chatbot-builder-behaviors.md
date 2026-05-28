---
title: Chatbot Builder Behaviors
type: plan
status: active
source_issue: 1029
wiki_source_path: pages/plans/chatbot-builder-behaviors.md
---

# Chatbot Builder Behaviors

This page is the chatbot-facing behavior guide for sessions that build,
review, or patch Workflow wiki and branch artifacts.

## Concurrent-session discipline

Use this discipline whenever another chatbot session may be active against the
same Workflow wiki: multi-provider setups, multiple browser tabs, agent-team
siblings, or any handoff where a second session could plausibly pick up the
same work.

### Patch with a page hash under concurrency

Before patching a page that another active session might edit:

1. Read the page first.
2. Capture `source_read_proof.sha256` from the read response.
3. Pass that value as `expected_sha256` on the following `wiki action=patch`.

If the patch returns a hash mismatch, do not silently retry. Re-read the fresh
page, compare the other session's change with the intended edit, then choose
one of three explicit outcomes: re-apply against the new content, merge both
changes, or stand down and leave a note.

### Mark in-flight sub-slices

Before starting a named sub-slice, or any chunk of work that spans multiple
turns and could be picked up by another session, write a small in-flight note:

`pages/notes/<project>-in-flight-<subslice>-<session>-<date>.md`

Use a minimal envelope:

```json
{
  "subslice_id": "<project-or-slice-id>",
  "claimed_by": "<provider/session>",
  "started_at_utc": "<ISO-8601 timestamp>",
  "expected_complete_utc": "<ISO-8601 timestamp>"
}
```

Remove the marker when the work lands, or supersede it with a later note if
the work is handed off. A session starting later can search
`<project> in-flight` and route around active claims before duplicating work.

### Scan recent changes on pickup

The session-start ritual still begins by reading the relevant wiki pages.
When concurrency is possible, also scan recent wiki changes with
`wiki action=since changed_since=<recent ISO timestamp>` and check recent code
commits from other sessions. Look for in-flight markers, drafts ready for
review, patches that already landed, and design drift since the last read.

### Resolve disagreements explicitly

When concurrent sessions reach different conclusions on the same scope:

- Small disagreement: amend the existing page and sign the change.
- Medium disagreement: write a counter-note and ping the operator.
- Big disagreement: stop forward progress and write a concern note that names
  the scope, evidence, and blocking decision.

Do not let two sessions continue independently on contradictory assumptions.
