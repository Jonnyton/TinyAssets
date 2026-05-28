---
name: premise
description: Read or replace the current universe premise through the Workflow Server.
disable-model-invocation: true
---

# Premise

Read or update the universe purpose/premise that seeds the daemon's creative direction.

## Usage

- `/workflow-universe-server:premise` with no arguments: call `universe`
  with `action="read_premise"` and display the current premise.
- `/workflow-universe-server:premise <text>`: call `universe` with
  `action="set_premise"` and the provided text. Warn the user this
  overwrites the existing premise. Offer to show the current premise first.

## Notes

The daemon reads the premise once at startup. Changing it mid-run will take effect on the next daemon restart or universe switch.
