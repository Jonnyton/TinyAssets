# Souled-universe self-maintenance: effect-authority resolved through the running universe's soul

**Status:** proposed (design note). Centers on one slice; names two adjacent gaps as future.
**Lineage:** PR-139 "Souled-universe consolidation program" (wiki `pages/patch-requests/pr-139-souled-universe-consolidation-program-*`; GitHub slices #1089–#1101). External-write spine: PR-122 / #914 (`docs/design-notes/2026-05-19-external-write-authority-and-rewards.md`).
**Author lens:** host directives 2026-05-28 (the "Tiny" framing), grounded against `origin/main` code.

---

## Thesis

A universe's **soul** is a continuity-of-intent engine: it preserves, grows, and keeps-aligned
its founder's will, even when the founder is not actively present. A universe acts on the world
through **branches with real-world gates** (its hands). For the platform's own universe ("Tiny",
whose product happens to be TinyAssets itself), one of those hands is the patch-request loop, and
its real-world gate is *opening PRs against the TinyAssets repo*.

Today that hand's **authority** comes from a global daemon env map, decoupled from the soul. This
note proposes the one structural change that makes "permission controlled by this specific
universe" true by **architecture** rather than by host env config: **resolve effect-authority
through the running universe's soul.**

This is project-generic. Tiny is not special — it is the first dogfood. A game universe's soul
authorizes *its* hands (its game's effect destinations); a fantasy universe with no separate
platform has no patch loop at all but still has a soul and other hands (social, publishing).
**If any code path ever says `if universe == "tiny"`, it has drifted.**

## The model (for grounding; not all of it ships here)

- **Soul = founder-will continuity**, not a development engine. The branches *enact* will
  (social, publishing, PRs); the soul is the distilled alignment layer that accretes from them
  and outlives any single burst of founder attention.
- **Every universe can have its own personified agent** (by its own name); **not every universe
  has a patch loop** — only ones maintaining a separate platform/product.
- **The loop is generic; the universe supplies the alignment.** Another platform runs the *same*
  loop branch, referencing *its* universe. Anything platform-specific lives in the universe, and
  the loop "knows to look there."
- **Embodiment (for Tiny):** repo = body/genome; branches-with-gates = hands/tools;
  website = face; posts = voice; the loop = self-improvement — itself just one hand.
- **Personality grows with capability; bones are present from universe-start.** The soul starts
  minimal and is meant to grow; using a will-bearing node can eventually ratchet into a versioned
  soul edit, bounded by founder-alignment.

## What is already wired on `origin/main` (do not rebuild)

- **`tinyassets/universe_soul.py`** — `soul.md` carries founder-will as typed fields: `purpose`,
  `why`, `hard_lines`, `soft_preferences`, `open_to_contributors`, plus **`edit_authority`**
  (default `"soul.edit"`) and **`loop_branch_def_id`**. Every write snapshots to
  `soul_versions/NNNN.md`, so soul edits are already versioned. `PinnedUniverseSoul.context()`
  carries an explicit identity boundary ("guides context only; does not change actor identity").
- **The loop-generalization is built.** `tinyassets/api/universe.py::_universe_loop_dispatch()`
  reads `soul.loop_branch_def_id` and dispatches *that* branch. The universe already runs the
  loop its soul names — generic loop, universe supplies which one.
- **Soul-as-lens (read direction) is wired.** `tinyassets/retrieval/agentic_search.py::assemble_soul_lens_context()`
  pulls the pinned soul into context assembly. The soul already *shapes* what every branch sees.
- **The hands + receipts exist.** `tinyassets/effectors/{github_pr,windows_desktop}.py` translate an
  `external_write_packet` into real side effects; `tinyassets/storage/external_write_receipts.py`
  records them. Per-destination **consent is already per-universe** via the `effector_consents`
  table (`github_pr.py::_check_consent(universe_dir, destination)`).
- **`tinyassets/resolution/`** is a *claim-conflict* resolver (which surface wins when evidence
  disagrees) — **not** the effect-permission gate. Do not conflate the two.

## The gap (this slice)

In `tinyassets/effectors/github_pr.py`, the **write capability** — the authority to effect a given
destination — is read from a **global daemon env map** `TINYASSETS_GITHUB_PR_CAPABILITIES`
(`_CAPABILITIES_ENV`, `_read_capability(destination)`), keyed by `owner/repo`. The per-universe
`effector_consents` row gates *consent*, but the *capability/authority itself* is global and has
no relationship to the running universe's soul.

Consequence: "Tiny is the sole PR-effector for TinyAssets" is currently enforced only by *which
env tokens the host sets on the daemon*, not by anything intrinsic to Tiny's universe. Any
universe whose run reaches the effector and clears consent could, in principle, use a globally
configured capability. The authority is in the wrong place.

## Proposed first slice: soul-scoped effect-authority

Make the running universe's **soul the source of effect-authority**, resolved at the effect
boundary:

1. **Soul declares its authorized hands.** Add an effect-authority scope to the soul (extend
   `edit_authority` semantics, or a sibling `effect_authority` list) naming the sinks/destinations
   this universe is permitted to effect — e.g. Tiny's soul declares
   `github_pr:Jonnyton/TinyAssets`. This is the universe's own typed declaration of its hands, in
   `soul.md`, versioned like everything else.
2. **The effector resolves authority from the soul of the running universe**, not from a global
   env map. `_read_capability(destination)` becomes "is this destination within the running
   universe's soul-declared effect-authority?" The env capability map is demoted to a *secrets*
   carrier (where the token/credential lives), never the *authority* decision — authority is the
   soul; the token is just how the authorized action is executed.
3. **Consent stays as the second factor** (`effector_consents`) — soul authorizes the *class* of
   hand; consent is the per-destination active grant. Both must hold. Kill-switch
   (`TINYASSETS_EXTERNAL_WRITE_ENABLED`) and dry-run defaults are unchanged.

Result: Tiny is the sole PR-effector for TinyAssets **because its soul is the only soul that
declares `github_pr:Jonnyton/TinyAssets` as an authorized hand** — architecture, not env config.
A game universe declares its own destinations. The mechanism is identical for all.

### Scope discipline (irreducibility / no over-build)

- **Reuse, don't invent.** This slice reuses `soul.md` + `effector_consents` + the existing
  effector entry point. The only new substrate is a soul-declared effect-authority field and a
  resolution check at the effector. If review finds this composes from existing fields without a
  new field, prefer that.
- **No `if universe == "tiny"` anywhere.** Generic by construction.
- **Out of scope (named, not built):** the self-change ratchet, and the `learned_failure` ceiling.

## The two adjacent gaps (future, not this slice)

- **Self-change ratchet.** `soul_versions/` exists, but nothing auto-ratchets intent from
  node-use back into a soul edit. Growth ("personality grows as capabilities grow") is the
  intended direction; it needs its own design once the alignment-bounding rules are settled.
- **Loop never clears `learned_failure`.** Goal `4ff5862cc26d` has 76 branches, 186 runs on the
  leader, quality 0, no canonical. The growth organ has never turned over once. Orthogonal to
  authority, but it blocks any universe's loop from producing a real outcome; worth its own
  investigation.

## Open questions for review

1. Extend `edit_authority` to cover effects, or add a distinct `effect_authority` field? (Edit
   vs. effect are different verbs — leaning distinct.)
2. Should soul-declared effect-authority itself require a higher bar to *add* (since it grants
   real-world reach)? Likely yes — adding an effect-authority entry is a soul edit, which is the
   highest-trust soul operation.
3. Does the env capability map stay as the secrets carrier, or move credentials to the vault
   (`scripts/load_secrets.sh`) and leave the effector reading only soul + vault?

## References

- Code: `tinyassets/universe_soul.py`, `tinyassets/api/universe.py` (`_universe_loop_dispatch`),
  `tinyassets/retrieval/agentic_search.py` (`assemble_soul_lens_context`),
  `tinyassets/effectors/github_pr.py`, `tinyassets/storage/{external_write_receipts,effector_consents}.py`,
  `tinyassets/resolution/`.
- Design lineage: PR-139 (wiki), `docs/design-notes/2026-05-19-external-write-authority-and-rewards.md`.
- Memory: `project_tiny_souled_platform_person`, `project_platform_is_just_a_goal_consumer`,
  `project_role_shift_to_community_participant`, `feedback_irreducibility_test_before_spec`.
