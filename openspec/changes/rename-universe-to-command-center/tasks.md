# Tasks: rename-universe-to-command-center

C0 is copy and is already approved by the founder. Design approval gates C1 and
later.

## C0. Copy

- [ ] 0.1 App: rename every user-visible "universe" in `app.html` and
      `app_ui.js`. "Switch UI" becomes "Switch command center", and the empty
      thread becomes "Welcome, commander.". Keys and ids stay.
- [ ] 0.2 Agent voice: served guidance, `api/prompts.py` server instructions and
      `control_station`, persona/seed text, and the `universe_tools.py`
      self-description. Rewrite sentences rather than swap words, so the
      engine block stays within the 30,000 ratchet (D5).
- [ ] 0.3 Website pages, `llms.txt`, plugin display name/description, and
      store-listing copy in the repo. Rebuild the plugin mirror.

## C1. MCP surface

- [ ] 1.1 Generate the exhaustive alias inventory (parameters, targets, enum
      values, error codes, response keys) from the live schemas. Record it in
      `command_center_aliases.py`, the single table (D3).
- [ ] 1.2 Website read contract accepts either key; land it, then verify it is
      live before 1.3 deploys (D4).
- [ ] 1.3 Server: new names primary, a pre-validation alias middleware on both
      servers, the `conflicting_alias` refusal, alias-hit logging, and renamed
      error codes and response keys. App routes normalize through the same table.
- [ ] 1.4 Rename `meet_universe` to `meet_command_center` and sync the
      `live-mcp-connector-surface` delta.
- [ ] 1.5 Bridge identity carries both the new and the old keys permanently,
      with a test that a stored bundle reading `universe_id` still works.
- [ ] 1.6 Post-deploy evidence: `mcp_public_canary.py --assert-handles` green,
      `deployed_sha.py --assert-contains`, and a rendered `ui-test` conversation
      that calls with an old name and with a new one.

## C2. Living docs

- [ ] 2.1 PLAN.md (glossary line, in place), README, skills, `docs/reference`,
      `openspec/specs`, and the two capability dir renames, updating every
      reference. Dated records are untouched.

## Later

- [ ] 3.1 Remove the aliases once production shows 14 consecutive days with
      zero alias hits (bridge aliases excepted).
- [ ] 3.2 Record the founder's D6/D7 decision. If either is overruled, open its
      own change.
