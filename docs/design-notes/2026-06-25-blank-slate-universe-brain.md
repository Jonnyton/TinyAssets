# Blank-Slate Universe Brain — every universe starts knowing nothing but the drive to align and learn

- **Status:** Proposed (design). Host-ratified 2026-06-25. Codex review = **ADAPT**, folded (§11). §10 self-model store resolved — OKF-grounded, host-approved 2026-06-25 — build started at Slice 1.
- **Author:** Claude Code session (host design dialogue 2026-06-25).
- **Supersedes framing of:** Persona Slices 1–3 (`#1382`, `#1386`, `#1395`) — see §7.
- **Relates to:** OKF brain foundation (`#1369`), Personification interaction layer (`#1372`), memory-scope model, PLAN.md Brain module (typed/promoted memory; generator/evaluator/Brain separation), `workflow/persona.py`, `workflow/universe_soul.py`, `workflow/api/status.py`.

---

## 1. Summary

Every universe brain boots from the **same blank state**, pre-loaded with
**nothing about itself** — no name, no identity, no sense of its body. The only
universal pre-load is a **drive**: *align with my founder, and learn continuously
from everything that happens in me.* The brain's **identity** (who am I, my name,
my body/shape) is **earned over time** — formed by the brain itself, from (a) its
founder's signal and (b) the accumulated data of every branch ever run inside the
universe. The founder has **no buttons** that write the brain's *identity* directly;
the brain is the **sole author of its own self-model**.

**Critical distinction (Codex ADAPT, §11):** this applies to the persona's
**identity self-model**, which is *separate from* the universe's **operational
direction** (premise / loop branch / authority). The bug was conflating the two —
the persona recited the operational premise *as its identity*. Operational
direction stays as load-bearing founder signal; only identity becomes blank +
learned.

## 2. Why now — the bug this corrects

A live host-run chatbot test (2026-06-25, sha `94b21693`) asked the platform
persona "who are you and what are you working on?" It replied:

> "the persona is Tiny… **Tiny's declared purpose is the patch-request loop**… **it's
> running** with effects in dry-run…"

The persona *recited a hand-authored `UniverseSoul.purpose` string* — it parroted a
pre-fed answer it never learned. Three slices of prompt-strengthening tried to make
it *embody* that answer; you cannot stop a persona relaying a canned answer while a
canned answer sits in its soul. Remove the fed *identity* and the relay has less to
grab. (Caveat per Codex §11: removing the fed answer does **not** by itself
*guarantee* first-person embodiment — clients can relay any block in third person.
Client-instruction/prompt verification stays a **separate acceptance gate**.)

## 3. The model (host-ratified principles)

1. **Identity is the universe.** Every unique OAuth identity maps to one **main
   universe**, created automatically on first recognition.
2. **One uniform blank brain.** Every universe boots from the identical starting
   brain. Pre-loaded **identity** content = **zero**. The only universal pre-load
   is the **drive**: *align with founder + learn from all activity.*
3. **No buttons (for identity).** The founder cannot set the brain's *identity*
   directly. Everything they do — talk, state intent, run branches — is **signal**
   the brain absorbs.
4. **The brain is the sole author of its own self-model.** It continuously forms,
   holds, and updates its evolving self-understanding from signal + activity. It is
   the only writer of its identity.
5. **Founder intent is signal, not a constraint to resolve.** The founder freely
   expresses what they want — clear signal — and the brain *intrinsically wants to
   align*. No tension to police.
6. **Curiosity comes from the drive, not a fed checklist.** A blank aligning mind
   is naturally curious about exactly what it needs to align: *who is my founder?
   what are this universe's goals? existing work to build from, or starting new?*
   Questions universal; answers emergent.
7. **Generic name at birth; the name is learned.** On OAuth recognition the
   universe gets a **generic placeholder name** — never meaningful at birth.
8. **Body/shape are observed, never declared.** `patch-loop-live` *discovers* "a
   patch loop runs in me" by observing its branch history.
9. **Identity self-model ≠ operational direction (Codex ADAPT).** The founder's
   premise/direction (what to build), the loop branch, and authority grants are
   **operational** founder signal — they stay, the daemon keeps reading them. The
   persona's **identity** (name, self-understanding, body-sense) is the *only* thing
   that becomes blank + learned. `set_premise` does not vanish; it stops being
   surfaced as the persona's *identity claim*.

## 4. Onboarding flow (first-time user)

1. User adds the connector, or their chatbot connects to the MCP directly.
2. System reads the unique OAuth: **no** main universe → create one (blank identity
   + generic name); **has** one → auto-route to it + its persona.
3. **First contact = curiosity:** the brain wants to learn its founder, the goals,
   and existing-vs-new. For the host: a universe already exists, but its *identity*
   is blank, so it is curious about *him* and reconstructs its body from the real
   branch history it can see.

## 5. Architecture mapping

- **This is the per-universe OKF brain** (`#1369`) with its **identity seed state
  corrected to empty.** The brain assembles an identity self-model from universe
  activity across the memory tiers (node→branch→goal→user→universe). That
  self-model **is** the persona's voice (`#1372`).
- **`UniverseSoul` is split in two roles** (Codex §11): *operational* fields
  (`loop_branch_def_id`, `edit_authority`, `effect_authority`, and the premise as
  build-direction) stay and keep driving the daemon; the *identity* the persona
  claims moves to a new, brain-authored **`UniverseSelfModel`** (§10) that starts
  blank.
- **`get_status` persona block** stops presenting authored `purpose` as the
  persona's self-claim; it surfaces the brain's *current learned self-model*
  (sparse + curious when new) — via an **additive/versioned** shape change, not a
  key swap (tests pin `name`/`purpose`/`embodied`; keep them, add learned fields).
- **The persona voice** = whatever self-model the brain has authored so far;
  embodiment is a *separate* client-side gate (§2 caveat).

## 6. What changes in current code (audit, not yet built)

| Current | Problem | Direction (adapted) |
|---|---|---|
| `resolve_persona` surfaces `soul.purpose` as identity | Recites a fed answer | Surface the learned `UniverseSelfModel`; keep `purpose` key additively for compat |
| `set_premise` writes purpose + PROGRAM.md | Doubles as identity *and* operational direction | **Keep** as operational founder-signal; stop routing it to the persona's identity claim. Daemon keeps reading premise for direction |
| `write_graph(target=persona, name=…)` (Slice 2, `#1386`) | Founder button that sets identity + short-circuits learning | Demote/remove **last**, only after the brain can learn a name from signal |
| Universe creation writes premise at birth | Pre-fed identity | Keep premise as direction; **identity** self-model starts blank; assign generic name |
| `get_status` persona surfaces authored purpose | Fed answer as fact | Additive/versioned learned-self-model shape; both-client `ui-test` |

**Migration (adapted — do NOT strip souls wholesale, Codex §11):** keep every
universe's **operational** soul fields (loop branch, authority) and its activity
history; blank only the **authored identity** the persona claims. Stripping
`patch-loop-live`'s whole soul would null `loop_branch_def_id` → `submit_request`
rejects and the loop queues nothing (`workflow/api/universe.py:1397`). Migration is
**reversible**, ships with a **dry-run inventory** for `patch-loop-live`, and only
re-points identity to "learn from history."

## 7. Relationship to the persona slices already shipped

- **Slice 1 (`#1382`)** — persona surfacing + embody prompt. Surfacing scaffold
  reused; the identity it surfaces becomes the learned self-model.
- **Slice 2 (`#1386`)** — `set_persona_name` verb. To be **demoted/removed last**,
  after the brain can learn a name. (Not reversed first — Codex §11 ordering.)
- **Slice 3 (`#1395`)** — stronger embody prompt. Live test showed no voice shift;
  embodiment is a separate client gate, tracked apart from this note.

## 8. (reserved)

## 9. Proposed build slices (adapted order — Codex §11: build the replacement before retiring anything)

1. **OKF self-model bundle + seed (§10).** Stand up the per-universe `self/` OKF
   bundle with a seed `index.md` (okf_version + the broken-link curiosity questions)
   + read/write primitives. Pure addition; nothing retired. *(host-approved 2026-06-25)*
2. **`get_status.persona` = learned self-model, additive/versioned.** Keep
   `name`/`purpose`/`embodied`; add the learned identity + a `learning`/curious
   state. Both-client `ui-test`.
3. **First-contact curiosity.** The drive-driven "get to know my founder / goals /
   existing-vs-new" behavior, sourced from the self-model's gaps.
4. **Generic-name-at-birth + identity/operational split** in universe creation.
5. **Demote `set_premise` to operational-signal-only + remove `set_persona_name`.**
   Last, now that the brain learns identity. Premise still drives the daemon.
6. **Reversible migration** with dry-run inventory; verify a blanked-identity
   `patch-loop-live` still runs its loop (operational fields intact) and
   reconstructs its body from history.

Each slice: TDD, opposite-provider review, live chatbot `ui-test` via the CDP route.

## 10. Self-model store — an OKF bundle the brain writes about itself (host-resolved 2026-06-25)

Re-reading the OKF spec + README settled this and made it far smaller than first
drafted. **OKF is intentionally minimal — it imposes no curation, confidence, or
quality gate (curation is the producer's job); `index.md` is auto-generated
progressive disclosure.** So the self-model is just an OKF bundle the brain authors
about itself — no bespoke schema, no evaluator engine.

- **Store** — a per-universe OKF bundle at `self/` (sibling of the operational soul,
  distinct from its operational fields). One concept `.md` per learned thing
  (`identity.md`, `founder.md`, `body.md`, `goals.md`, …), each with OKF frontmatter
  (`type` required) plus extension keys (`confidence`, `provenance:
  founder-signal | observed-activity`, `timestamp`). Reuses `workflow/wiki/okf_export.py`.
- **Evidence** — OKF `# Citations`: a claim cites the branch / conversation that
  taught it. A claim isn't *promoted*, it's *written with its receipt*. That citation
  discipline is the only gate.
- **Curiosity = OKF broken links** — a blank brain's `index.md` links to concept
  files that don't exist yet (OKF: "not-yet-written knowledge"); the gaps *are* its
  open questions. The seed `index.md` lists the universal questions (identity/name,
  founder, goals, body, existing-vs-new).
- **Learning history** — OKF `log.md`: dated entries as the brain updates itself.
- **Cadence** — not engineered. The brain updates as it interacts / observes (like a
  person), not on a schedule.
- **Read path / persona surface** — `get_status.persona` reads the bundle's
  `index.md` (OKF's native summary), additively, never the operational premise.

**On Codex's "evaluator gate" must-fix:** softened to **test-first**. OKF + host
direction (don't over-steer; don't assume the model can't curate) say: ship the
citation discipline, *test whether intent alone produces honest self-modeling*, and
add a gate only if live testing shows drift/hallucination.

## 11. Opposite-provider review (Codex, 2026-06-25) = ADAPT — folded

Codex (read-only) judged the direction sound but **not build-ready**, with 3
critical + 3 required findings, all folded above:

- **Critical — self-model is hand-wavy** → §10 added (schema/store/cadence/evidence/
  evaluator/drift); gated on host approval before build.
- **Critical — unsafe slice order** (retires setters before the replacement) → §9
  reordered: build self-model + learned status FIRST, retire setters LAST.
- **Critical — "strip souls" breaks the loop** (soul mixes identity + operational;
  no loop branch ⇒ `submit_request` rejects) → §5/§6/§9 split identity from
  operational; migration preserves operational fields, reversible + dry-run.
- **Required — `get_status` cross-client shape** → additive/versioned, keep pinned
  keys, both-client `ui-test`.
- **Required — "founder intent = signal" needs a contract** → §9 principle + §6:
  `set_premise` stays operational; specify storage + daemon effect + client response
  in slice 5.
- **Required — over-declared the persona bug resolved** → §2 caveat: embodiment is
  a separate client-instruction gate; removing the fed answer is necessary, not
  sufficient.

**Status after fold:** direction approved; build still gated on host sign-off of the
§10 self-model schema (the one genuinely-open design surface).
