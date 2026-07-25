# Tasks — universe visibility

Builder lane (claude/osx-universe-visibility): model + enforcement + tests
landed, then hardened per a cross-family REJECT (verdict:
`docs/audits/…verdict-universe-visibility`). Concrete model pinned in `design.md`.
Enforcement composes as `legacy_gate AND new_layer` (tighten-only by
construction) and fails closed by default on any undeclared/forged/corrupt state
— no env opt-in. `backfill_universe_visibility()` is the deploy migration that
declares existing universes from their `public_read` bit; the deploy must run it.
The `create` default *value* (public vs private) remains a host knob (design 1.3).

## 1. Define the model

- [x] 1.1 Enumerate visibility levels and the capabilities each grants to an unauthenticated reader
      (existence / metadata / content as separate grants)
      → `design.md` §1.1; `VisibilityLevel` triple + presets in `tinyassets/api/visibility.py`
      (`public` / `metadata_only` / `unlisted` / `private`).
- [x] 1.2 Decide per-universe vs per-page granularity and how they compose
      → `design.md` §1.2; composition `effective = universe AND page` — a page narrows,
      never widens (`page_content_permitted`); universe gate runs first.
- [x] 1.3 Decide the default for new universes
      → `design.md` §1.3. Undeclared fails closed **unconditionally** (no env flag). Two
      runtime gates make it safe/enforceable (round-3 ADAPT): (a) `run_visibility_startup_gate()`
      runs the idempotent backfill at boot (HTTP lifespan + `main()`) and refuses readiness if
      any universe stays undeclared; (b) `_action_create_universe` writes an explicit level at
      birth (both explicit create + converse auto-birth). The *value* is the host-knob
      `DEFAULT_CREATE_VISIBILITY` (default `public` per Hard Rule #12; creator may override).
- [x] 1.4 Decide disposition of the legacy universes (concordance, workflow-voice,
      echoes-of-the-cosmos, default-universe) — explicit level or recorded grandfather reason
      → `design.md` §1.4 (all four → explicit `public`; `default-universe`'s internal
      engineering pages get per-page `visibility: private`). `backfill_universe_visibility()`
      declares each from its current `public_read` bit (no visibility flip). NOTE: the actual
      per-page frontmatter edit on `default-universe`'s engineering pages is a runtime/deploy
      data step (those pages are not in the repo); the enforcement mechanism is built + tested.

## 2. Enforce it

- [x] 2.1 Gate universe enumeration on the declared level
      → `_action_list_universes` gates on `visibility_permits(uid, "discover_existence")`,
      reports the declared level per row, and emits a neutral "no universes visible" note
      that does not leak the hidden count or base path (`tinyassets/api/universe.py`).
- [x] 2.2 Gate wiki/commons reads on the declared level
      → wiki dispatcher gates reads on `read_content`; per-page narrowing applied across
      `read`/`search`/`since`/`list` and is grant-based (authentication alone is not page
      authority). Metadata gate at `get_status` + `inspect` (`read_metadata`), scoped to
      existing universes; blank-id denials do not leak the resolved private name.
- [x] 2.3 Fail closed on an undeclared level — never default to visible
      → `universe_visibility` returns `CLOSED` for undeclared / blank / null / unrecognized
      / wrong-type / malformed-JSON / non-object-metadata / corrupt states — no env opt-in.
      Composition is `legacy_gate AND new_layer`, so an inconsistent `public_read=False` +
      permissive explicit level is refused (tighten-only by construction).
- [x] 2.4 Raw-DML forge probe per gate, proven RED without the gate
      → `TestForgeProbes` + `TestResolutionFailClosed` + `TestTightenOnlyComposition` write
      withholding/forged rows directly into `universe_rules` and prove each gate withholds,
      while asserting the ungated primitive would serve. Mutation-verified non-vacuous.

## 3. Prove it

- [x] 3.1 Regression test: anonymous reader against each level sees exactly the declared surface
      → `tests/test_universe_visibility.py` (52 tests): fail-closed truth table row-by-row,
      tighten-only composition, grant exemption, all three gates per level, per-page narrowing
      (incl. authenticated-without-grant withheld), sibling-read leaks (search/since/list),
      note-leak + blank-id-leak, forge probes, backfill. Mutation-verified non-vacuous; ruff
      clean. Legacy get_status/telemetry suites migrated (fixtures declare, or the
      `tests/conftest.py` backfill-emulation for pre-visibility modules) — zero net new
      failures vs origin/main on the universe/wiki/status sweep.
- [ ] 3.2 Re-run the first-contact ui-test and confirm what an anonymous caller can enumerate matches
      the declared intent
      → **BLOCKED on live acceptance**: requires a deployed build + browser connector
      (`ui-test` through `https://tinyassets.io/mcp`). This is a verifier/host acceptance step
      after cross-family review + deploy — not runnable in this builder lane. Left unchecked
      deliberately.
