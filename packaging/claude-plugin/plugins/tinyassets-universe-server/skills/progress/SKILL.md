---
name: progress
description: Summarize recent universe output, current daemon activity, and writing progress.
disable-model-invocation: true
---

# Progress

Show a human-readable summary of what the daemon has written, including story outline, word counts, chapter status, and recent activity.

## Usage

When the user invokes `/tinyassets-universe-server:progress`, call
`universe` with `action="inspect"` and optionally `action="get_activity"`
for recent log entries.

## Response format

Present the progress as a brief narrative summary:
- What's been written (books, chapters, scenes)
- Current word count and trajectory
- What the daemon is working on now
- Any recent notable events from the activity log

Keep it conversational — this is a creative progress check, not a
technical report.
