# Tasks: rename-universe-to-command-center

C0 is copy and is already approved by the founder. Design approval gates C1 and
later.

## C0. Copy

- [ ] 0.1 (Partly shipped in #4182: Switch command center, Welcome, commander.,
      header, sign-in and connections copy.) App: rename every user-visible "universe" in `app.html` and
      `app_ui.js`. "Switch UI" becomes "Switch command center", and the empty
      thread becomes "Welcome, commander.". Keys and ids stay.
- [ ] 0.2 Agent voice: served guidance, `api/prompts.py` server instructions and
      `control_station`, persona/seed text, and the `universe_tools.py`
      self-description. Rewrite sentences rather than swap words, so the
      engine block stays within the 30,000 ratchet (D5).
- [ ] 0.3 Website pages, `llms.txt`, plugin display name/description,
      store-listing copy in the repo, and native strings (Android channel text
      with an always-update `ensureChannel`, iOS mic string, mobile/desktop
      loading pages, D9). Rebuild the plugin mirror.

## C1. MCP surface

- [ ] 1.1 Generate the exhaustive alias inventory (parameters, targets, enum
      values, error codes, response keys) from the live schemas. Record it in
      `command_center_aliases.py`, the single table (D3).
- [ ] 1.2 First-party readers prefer the new key and fall back to the old one:
      the app, the bridge, the website read contract, and
      `mcp_tool_canary.py` (D4).
- [ ] 1.3 Server: new names primary. Aliases at the MCP middleware (with
      strict validation pinned off) and at the owner door / app routes before
      validation. Migrate direct Python callers, with a test against retired
      keywords. Dual response keys, a `deprecated_fields` note, the
      `conflicting_alias` refusal, alias-hit logging, and `present_actor`
      (D3/D4/D7).
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

- [ ] 3.1 Once production shows 14 consecutive days with zero alias hits,
      remove the input aliases and the old response keys and bump
      `schema_version`. Bridge aliases are kept.
- [ ] 3.2 Founder decided D6/D7 on 2026-10-01: rename both. Run C3, the codemod,
      in a freeze window the lead opens. Open the `migrate-storage-to-command-center`
      change for C4 (D7): guard, inventory, dry run, backup, migration, rollback.
