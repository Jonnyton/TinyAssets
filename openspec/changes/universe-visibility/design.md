# Design — universe visibility model

This document pins the concrete model that `proposal.md` and the delta spec
(`specs/universe-visibility/spec.md`) require. It answers the "Define the model"
tasks (section 1 of `tasks.md`) so that enforcement (section 2) and proof
(section 3) have a stable target.

Truth split: `tinyassets/api/permissions.py` already owns **ownership** (the
`universe_acl` grant set) and the legacy binary **`public_read`** bit. This
change adds a thin, additive layer — `tinyassets/api/visibility.py` — that
decomposes the *anonymous read surface* into three separately-grantable
capabilities, fails closed on an undeclared/unrecognized level, and composes a
per-universe level with a per-page override. It never loosens the existing
gate; it only tightens it when a more restrictive level is declared.

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

A page declares its own restriction via a `visibility:` (or `content:`)
frontmatter key. A page marked restrictive is withheld from an anonymous reader
even inside an openly-readable universe (spec Req 3). A page cannot make itself
*more* visible than its universe — the universe gate runs first.

Rationale: the observed leak (`default-universe` commons) mixed internal
engineering notes with an unrelated public note in one scope. A universe-level
flag alone cannot express that; per-page narrowing can.

## 1.3 Default for a newly created universe

The security-load-bearing requirement is **"no universe may sit in an
undeclared state, and undeclared never defaults to visible"** (spec Req 1).
That is satisfied by *declaring a level at create time*, not by the value
chosen. Two knobs:

- **Undeclared resolution** (`universe_visibility()` when a rules row is
  genuinely absent): governed by env flag
  `TINYASSETS_VISIBILITY_STRICT_UNDECLARED`.
  - Default **off** → missing row resolves to `public` (preserves today's live
    behavior and the existing test suite until the backfill has run).
  - **On** → missing row resolves to `private` (full spec compliance; the
    fail-closed default). Intended to be switched on *after* the backfill has
    declared every existing universe, so it only ever bites genuinely broken
    state.
- **`create` default level**: create records an **explicit** level so a new
  universe is never undeclared. The autonomous-safe default is the conservative
  `private` (Hard Rule #4). **Host-decision knob:** the public-commons /
  discovery-remix vision may prefer `public` as the create default. The
  *mechanism* is built and the value is a one-line change; recorded in
  `tasks.md` as the host choice. This lane does not silently flip the live
  product default.

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
enforcement mechanism (`_wiki_read` page gate) is built and tested here.

This is a backfill of *declaration*, not a visibility flip. The genuinely
strict posture (`TINYASSETS_VISIBILITY_STRICT_UNDECLARED=on` +
`create` default `private`) is a host-gated rollout, recorded in `tasks.md`,
because it is a wide-blast-radius read-path change that must pass cross-family
review before any live flip.

## Enforcement surfaces (section 2 map)

| Capability          | Surface                                              | File                        |
|---------------------|-----------------------------------------------------|-----------------------------|
| `discover_existence`| `universe action=list` (`_action_list_universes`)   | `tinyassets/api/universe.py`|
| `read_metadata`     | `get_status` per-universe gate                      | `tinyassets/api/status.py`  |
| `read_content`      | `wiki` read dispatcher + per-page `_wiki_read`      | `tinyassets/api/wiki.py`    |
| observability (Req 4)| declared level reported in `list` / `inspect`      | `tinyassets/api/universe.py`|

## Proof (section 3 map)

- Per-level regression: an anonymous reader against each of the four levels sees
  exactly the declared triple (list / status / wiki).
- Raw-DML forge probe (task 2.4): write a withholding level directly into
  `universe_rules` (bypassing the public API), then prove each gate withholds —
  and prove the same probe is RED with the gate removed.
- Unrecognized-level and corrupt-rules → fail closed.
- `TINYASSETS_VISIBILITY_STRICT_UNDECLARED` on/off both covered.
- Live first-contact `ui-test` re-run (task 3.2) requires a deployed build +
  browser connector — a verifier/host acceptance step, not runnable in this
  builder lane.
