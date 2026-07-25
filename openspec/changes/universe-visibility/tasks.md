# Tasks — universe visibility

Builder lane (claude/osx-universe-visibility): model + additive enforcement +
tests landed. Concrete model pinned in `design.md`. Enforcement is additive —
it only tightens the existing `public_read` gate when a more restrictive level
is declared, so no live universe changes visibility (backfill declares intent).
Full-strict rollout (`TINYASSETS_VISIBILITY_STRICT_UNDECLARED=on` + `create`
default `private`) is host-gated; see design 1.3.

## 1. Define the model

- [x] 1.1 Enumerate visibility levels and the capabilities each grants to an unauthenticated reader
      (existence / metadata / content as separate grants)
      → `design.md` §1.1; `VisibilityLevel` triple + presets in `tinyassets/api/visibility.py`
      (`public` / `metadata_only` / `unlisted` / `private`).
- [x] 1.2 Decide per-universe vs per-page granularity and how they compose
      → `design.md` §1.2; composition `effective = universe AND page` — a page narrows,
      never widens (`page_content_permitted`); universe gate runs first.
- [x] 1.3 Decide the default for new universes
      → `design.md` §1.3. Security-load-bearing part (undeclared never defaults visible)
      is DONE via the `TINYASSETS_VISIBILITY_STRICT_UNDECLARED` flag + backfill. The
      *value* `create` records is a **host-decision** knob (conservative `private` default
      vs public-commons `public`); mechanism built, value is a one-line change — this lane
      does not silently flip the live product default.
- [x] 1.4 Decide disposition of the legacy universes (concordance, workflow-voice,
      echoes-of-the-cosmos, default-universe) — explicit level or recorded grandfather reason
      → `design.md` §1.4 (all four → explicit `public`; `default-universe`'s internal
      engineering pages get per-page `visibility: private`). `backfill_universe_visibility()`
      declares each from its current `public_read` bit (no visibility flip). NOTE: the actual
      per-page frontmatter edit on `default-universe`'s engineering pages is a runtime/deploy
      data step (those pages are not in the repo); the enforcement mechanism is built + tested.

## 2. Enforce it

- [x] 2.1 Gate universe enumeration on the declared level
      → `_action_list_universes` gates on `visibility_permits(uid, "discover_existence")`
      and reports the declared level per row (`tinyassets/api/universe.py`).
- [x] 2.2 Gate wiki/commons reads on the declared level
      → wiki dispatcher gates reads on `read_content`; per-page narrowing in `_wiki_read`
      (`tinyassets/api/wiki.py`). Metadata gate refined at `get_status` (`read_metadata`).
- [x] 2.3 Fail closed on an undeclared level — never default to visible
      → unrecognized declared level, corrupt rules read, and blank universe id all resolve
      to `CLOSED`; a genuinely-missing row fails closed under
      `TINYASSETS_VISIBILITY_STRICT_UNDECLARED`, and `backfill_universe_visibility()`
      removes undeclared states so the flag only ever bites broken state.
- [x] 2.4 Raw-DML forge probe per gate, proven RED without the gate
      → `TestForgeProbes` writes a withholding level directly into `universe_rules`
      (bypassing the API) and proves each gate withholds it, while asserting the ungated
      primitive (listable dir / resolved level / existing content) would serve it.

## 3. Prove it

- [x] 3.1 Regression test: anonymous reader against each level sees exactly the declared surface
      → `tests/test_universe_visibility.py` (enumeration / metadata / content gates per level +
      grant-exemption + per-page narrowing). 36 tests pass; ruff clean; 70 pre-existing
      isolation/observability/multi-tenant tests still pass.
- [ ] 3.2 Re-run the first-contact ui-test and confirm what an anonymous caller can enumerate matches
      the declared intent
      → **BLOCKED on live acceptance**: requires a deployed build + browser connector
      (`ui-test` through `https://tinyassets.io/mcp`). This is a verifier/host acceptance step
      after cross-family review + deploy — not runnable in this builder lane. Left unchecked
      deliberately.
