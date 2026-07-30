# Design — universe visibility model

This document pins the concrete model that `proposal.md` and the delta spec
(`specs/universe-visibility/spec.md`) require. It answers the "Define the model"
tasks (section 1 of `tasks.md`) so that enforcement (section 2) and proof
(section 3) have a stable target.

Truth split: `tinyassets/api/permissions.py` already owns **ownership** (the
`universe_acl` grant set) and the legacy binary **`public_read`** bit. This
change adds `tinyassets/api/visibility.py`, which decomposes the *anonymous read
surface* into three separately-grantable capabilities and composes a per-universe
level with a per-page override.

Two structural invariants (required by the cross-family review that rejected the
first cut):

- **Tighten-only by construction.** The effective read decision is
  `legacy_gate AND new_layer`: `visibility_permits` returns `False` whenever the
  legacy `universe_access_allows` read gate denies, so the new layer can never
  *grant* a read the legacy gate withholds. An inconsistent row (`public_read=False`
  plus a permissive explicit level) is therefore refused, not opened.
- **Fail closed by default.** `universe_visibility` returns the *declared* level
  or `CLOSED`; it never derives an open default from `public_read`. Undeclared,
  blank, null, unrecognized, wrong-type, corrupt, and non-dict states all resolve
  to `private`. Existing universes are declared by `backfill_universe_visibility`
  (the migration path) — not by a fail-open fallback or an env opt-in to
  strictness (which the review flagged as a config-text guard, not a runtime gate).

## 1.1 Visibility levels and the capabilities each grants an unauthenticated reader

An unauthenticated reader's access is three **separate** capabilities, exactly
as the spec requires (existence / metadata / content are separately granted):

| Capability          | What it grants an anonymous reader                                  |
|---------------------|---------------------------------------------------------------------|
| `discover_existence`| The universe appears in enumeration (`universe action=list`).       |
| `read_metadata`     | Name, word count, activity dates, phase, liveness (`get_status`).   |
| `read_content`      | Wiki/commons page bodies and other universe content.                |

Named levels are canonical presets over the three booleans. A level is a
**triple**, not an ordered scale — that is what lets "content but not
discovery" and "discovery but not content" both exist:

| Level           | existence | metadata | content | Meaning                                                   |
|-----------------|:---------:|:--------:|:-------:|-----------------------------------------------------------|
| `public`        |     ✅    |    ✅    |   ✅    | Fully open. The historical default.                       |
| `metadata_only` |     ✅    |    ✅    |   ❌    | Discoverable + describable, body withheld.                |
| `unlisted`      |     ❌    |    ❌    |   ✅    | Readable only by direct id; never enumerated (spec Req 2).|
| `private`       |     ❌    |    ❌    |   ❌    | Nothing to an anonymous reader (grant required).          |

`private` is the **fail-closed** level: any undeclared, unrecognized, or
unreadable state resolves to it.

A reader **with an ACL grant** (read/write/admin) on the universe is not an
"unauthenticated reader" and is exempt from these limits — they always get full
access to their own universes. The level governs only the non-granted surface.

## 1.2 Per-universe vs per-page granularity and composition

Visibility is evaluated **per universe and per page**. The universe level is the
ceiling; a page may only *narrow* it, never widen it:

```
effective_content(page) = universe.read_content AND page.read_content
```

A page declares its own restriction via a `visibility:` (or `content_visibility:`)
frontmatter key. A page marked restrictive is withheld from any reader that is
not a *granted* reader of the page's universe, even inside an openly-readable
universe (spec Req 3). **Authentication alone is not page authority** — a valid
user with ordinary wiki scope but no universe ACL grant is treated exactly like
an anonymous reader (a first-cut bug the review caught). A page cannot make
itself *more* visible than its universe — the universe gate runs first.

The narrowing applies to **every read path that surfaces a page**, not just
`read`: `search`, `since`, and `list` all filter restricted pages out (their
body excerpt, title, and path are each disclosure).

Rationale: the observed leak (`default-universe` commons) mixed internal
engineering notes with an unrelated public note in one scope. A universe-level
flag alone cannot express that; per-page narrowing can.

## 1.3 Default for a newly created universe

The security-load-bearing requirement is **"no universe may sit in an
undeclared state, and undeclared never defaults to visible"** (spec Req 1).

- **Undeclared resolution is fail-closed, unconditionally.**
  `universe_visibility()` returns `CLOSED` for any universe without an explicit,
  recognized `visibility_level` — no env opt-in, no `public_read` fall-through.
  The review rejected the env-flag approach (a config-text guard, not a runtime
  gate), so strictness is the default and only behavior.
- **`backfill_universe_visibility()` is the migration, and the startup gate makes
  it enforceable.** The backfill declares every pre-existing universe from its
  current `public_read` bit (`True → public`, `False → private`) so no live
  universe changes visibility — it only becomes *declared*.
  `run_visibility_startup_gate()` runs the backfill at server boot (HTTP
  `lifespan` + `main()` for sse/stdio) and then **refuses readiness**
  (`VisibilityStartupGateError`) if any universe remains undeclared, with the
  exact remediation. This is a runtime gate, not a prose deploy instruction — an
  un-migrated deploy fails fast instead of silently serving legacy universes as
  `CLOSED`.
- **Creation writes an explicit level.** `_action_create_universe` (the single
  path both explicit `create_universe` and the converse/first-contact auto-birth
  route through) declares `visibility` at birth on the create's critical path, so
  undeclared rows stop being produced going forward. The value is
  `DEFAULT_CREATE_VISIBILITY` (a **host-decision knob**, default `public`, matching
  Hard Rule #12 "public-draft by default" and today's `public_read=1` default);
  the creator may pass an explicit level, and an invalid value fails the create
  loudly. The delta spec mandates only that an *explicit* level be written, not a
  specific value.

**Test-harness note:** the pre-visibility test suite (hundreds of tests) creates
bare universes and was written against the post-backfill world. `tests/conftest.py`
carries an autouse fixture that *emulates the deployed backfill* for those legacy
modules (undeclared → `public_read`-derived) so they keep asserting their own
concern. Production code ships fully strict; the true pre-backfill fail-closed
behavior is exercised un-emulated by `tests/test_universe_visibility.py`.

## 1.4 Disposition of the legacy universes

`concordance`, `workflow-voice`, `echoes-of-the-cosmos`, `default-universe` are
old and publicly-intended (proposal.md). Disposition:

| Universe             | Level      | Reason                                                              |
|----------------------|------------|--------------------------------------------------------------------|
| `concordance`        | `public`   | Publicly-intended knowledge universe; grandfather to explicit public.|
| `workflow-voice`     | `public`   | Publicly-intended; dormant (3 stale queue rows — unrelated).        |
| `echoes-of-the-cosmos`| `public`  | Publicly-intended.                                                  |
| `default-universe`   | `public` universe, **per-page restriction** on its engineering pages | The commons body is public-intended, but its patch-request / bug-report / identity-defect pages are internal and get `visibility: private` frontmatter. |

The universe-level backfill (`backfill_universe_visibility`) derives each
existing universe's explicit level from its current effective `public_read`
bit, so **no live universe changes visibility** — it only becomes *declared*.
The per-page restriction of `default-universe`'s internal pages is a runtime
data step (adding frontmatter to those wiki pages) executed at deploy; the
enforcement mechanism (page gate across `read`/`search`/`since`/`list`) is built
and tested here.

## Enforcement surfaces (section 2 map)

| Capability          | Surface                                                          | File                        |
|---------------------|-----------------------------------------------------------------|-----------------------------|
| `discover_existence`| `universe action=list` (`_action_list_universes`); note-leak safe| `tinyassets/api/universe.py`|
| `read_metadata`     | `get_status` gate (existing universes) + `inspect` gate; blank-id leak safe | `tinyassets/api/status.py`, `tinyassets/api/universe.py` |
| `read_content`      | `wiki` read dispatcher + per-page narrowing across `read`/`search`/`since`/`list` | `tinyassets/api/wiki.py`    |
| observability (Req 4)| declared level reported in `list` / `inspect`                  | `tinyassets/api/universe.py`|

Composition is `legacy_gate AND new_layer` at every surface, so the new layer
can only narrow. Page-level narrowing is grant-based (authentication alone is not
authority). `get_status`/`inspect` gate only *existing* universes — a nonexistent
universe has no metadata to protect, so the not-found diagnostic stays ungated.

## Proof (section 3 map)

- `tests/test_universe_visibility.py` (52 tests): the fail-closed truth table row
  by row (blank/null/unrecognized/wrong-type/malformed-json/non-object-metadata/
  corrupt/undeclared → `CLOSED`); tighten-only composition (inconsistent
  `public_read=False` + permissive level denied at all three gates); grant
  exemption; enumeration/metadata/content gates per level; per-page narrowing incl.
  authenticated-without-grant withheld; sibling-read leaks (search/since/list);
  note-leak + blank-id-leak; raw-DML forge probes RED without the gate; backfill.
- Mutation-verified non-vacuous: forcing `visibility_permits`/`universe_visibility`
  open turns 30 gate tests RED; forcing `page_content_permitted` open turns the
  page/sibling tests RED.
- Live first-contact `ui-test` re-run (task 3.2) requires a deployed build +
  browser connector — a verifier/host acceptance step, not runnable in this
  builder lane.
