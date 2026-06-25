# Blank-Slate Universe Brain — every universe starts knowing nothing but the drive to align and learn

- **Status:** Proposed (design). Host-ratified principles 2026-06-25; build slices not yet started.
- **Author:** Claude Code session (host design dialogue 2026-06-25).
- **Supersedes framing of:** Persona Slices 1–3 (`#1382`, `#1386`, `#1395`) — see §7.
- **Relates to:** OKF brain foundation (`#1369`, `docs/.../2026-06-24-...okf...`), Personification interaction layer (`#1372`), memory-scope model, `workflow/universe_soul.py`, `workflow/api/status.py` persona block.

---

## 1. Summary

Every universe brain boots from the **same blank state**. It is pre-loaded with
**nothing about itself** — no name, no purpose, no body, no identity. The only
thing every brain starts with is a **drive**: *align with my founder, and learn
continuously from everything that happens in me.* Its identity, body, shape,
purpose, and even its **name** are **earned over time** — formed by the brain
itself, from (a) its founder's signal and (b) the accumulated data of every
branch ever run inside the universe. Nothing is ever *fed as an answer*; the
founder has **no buttons** that write the brain's state directly. The brain is
the **sole author of its own self-model**.

This is the same per-universe brain described in the OKF foundation — this note
corrects its **seed state to empty** and forbids direct state-setting.

## 2. Why now — the bug this corrects

A live host-run chatbot test (2026-06-25, deployed sha `94b21693`) asked the
platform universe's persona "who are you and what are you working on?" It replied:

> "the persona is Tiny… **Tiny's declared purpose is the patch-request loop**… **it's
> running** with effects in dry-run… What **it's** working on right now: 12 live runs…"

Two faults, one root cause:

1. **It recited a purpose it never learned.** `UniverseSoul.purpose` held a
   hand-authored string ("Patch-request loop: a user-built backlog driver…") and
   `get_status` surfaced it. The persona *parroted a pre-fed answer*.
2. **It relayed in the third person** ("the persona is Tiny", "it's working on")
   instead of embodying ("I'm…", "I'm working on…").

These are the **same problem**. Three slices of prompt-strengthening (Slices 1–3)
tried to make the bot *embody the purpose better* — but you cannot stop a persona
relaying a canned answer while a canned answer sits in its soul. **Remove the
pre-feeding and the relay has nothing to grab.** A one-day-old universe asked
"what are you?" should honestly say *"I'm new — I don't know my shape yet; I'm
here with you and learning,"* not recite a mission someone typed for it.

## 3. The model (host-ratified principles)

1. **Identity is the universe.** Every unique OAuth identity maps to one **main
   universe**, created automatically on first recognition.

2. **One uniform blank brain.** Every universe boots from the identical starting
   brain. Pre-loaded content = **zero**. The only universal pre-load is the
   **drive**: *align with my founder + learn from all universe activity.*

3. **No buttons.** The founder cannot reach in and set the brain's state. There is
   no "set purpose", no "set name", no direct identity/body writer exposed to the
   founder. Everything the founder does — talk, state intent, run branches — is
   **signal** the brain absorbs through its drive. This is structural, not a
   policy: with no setters, nothing can *ever* be fed as an answer.

4. **The brain is the sole author of its own self-model.** "No buttons" applies to
   the *founder*. The **brain** continuously forms, holds, and updates its own
   evolving self-understanding from signal (founder) + activity (branches). It is
   the only writer of its identity.

5. **Founder intent is signal, not a constraint to resolve.** "Declared vs
   inferred" is a false dichotomy. The founder freely expresses what they want —
   that's *clear signal* — and it is fine, because the brain *intrinsically wants
   to align and do what the founder wants*. There is no tension to police.

6. **Curiosity comes from the drive, not a fed checklist.** We do **not** hardcode
   "ask for the repo link / the website / your name." A blank brain that *wants to
   align* is naturally curious about exactly the dimensions it needs in order to
   align: *who is my founder? what are this universe's goals? is there existing
   work I should reference and build from, or is the founder starting something
   new?* The **questions are universal** (every brain wants these); the **answers
   are emergent** (learned per universe). The specific facts — name = "Tiny", the
   repo URL, the founder's website — are answers the brain *goes looking for
   because it wants to*, then writes into its own self-model.

7. **Generic name at birth; the name is learned.** On OAuth recognition the
   universe is assigned a **generic placeholder name** — never a meaningful one
   ("patch-loop", "Tiny" are both wrong at birth). A real name is something the
   brain comes to, from its founder, over time.

8. **Body and shape are observed, never declared.** The brain comes to know its
   body the way a person does — `patch-loop-live` should *discover* "a patch loop
   runs in me" by **observing it run** across the universe's branch history, never
   by being told.

## 4. Onboarding flow (first-time user)

1. The user adds the Workflow connector, **or** their chatbot connects to the MCP
   directly.
2. The system reads the unique OAuth and checks for a main universe:
   - **None** → create one: blank brain + generic placeholder name.
   - **Exists** → auto-route to that main universe and its persona.
3. **First contact = curiosity.** The brain wants to learn its founder, the
   universe's goals, and whether there is existing work to build from or the
   founder is starting fresh. It asks — not from a script, but because a blank,
   aligning mind genuinely needs to know.

For the **host specifically:** a universe already exists, but under §6 (migration)
it is stripped to blank. Next contact, instead of "I'm Tiny, my job is the patch
loop," it is curious about *him* and about *the universe it finds itself in*: it
can see deep history (a patch loop, ~27 goals) and reconstructs its **body** from
that real activity, while openly not yet knowing its founder, its name, or whether
this is work to build on or a fresh start.

## 5. Architecture mapping

- **This is the per-universe OKF brain** (`#1369`) with its **seed state corrected
  to empty**. The brain assembles a self-model from universe activity across the
  memory-scope tiers (node → branch → goal → user → universe). That self-model
  **is** the persona's voice (`#1372` personification).
- **`UniverseSoul.purpose`** + the `set_premise` that writes it = the pre-feeding
  to remove. A learned, brain-maintained self-summary replaces the hand-set string.
- **`get_status` persona block** must stop surfacing an authored purpose as fact;
  it surfaces the brain's *current learned self-model* (which, for a fresh or
  freshly-stripped universe, is honestly sparse + curious).
- **The persona voice** = whatever self-model the brain has authored so far.
  Embodiment falls out of this for free: there is no separate "persona" to relay,
  only the brain speaking as itself.

## 6. What changes in current code (audit, not yet built)

| Current | Problem under this model | Direction |
|---|---|---|
| `UniverseSoul.purpose` (authored) | Pre-fed identity the persona recites | Replace with brain-authored, learned self-model |
| `set_premise` (writes purpose) | A founder "button" that sets brain state | Remove as a direct setter; founder intent becomes signal the brain absorbs |
| `write_graph(target=persona, name=…)` / `set_persona_name` (Slice 2, `#1386`) | A founder "button" that sets the name AND short-circuits learning it | Remove as a direct setter; name is learned from founder signal |
| Universe creation assigns a meaningful name | Names a universe "patch-loop" etc. at birth | Assign a generic placeholder; name is learned |
| `get_status` persona block surfaces authored `purpose` | Surfaces a fed answer as fact | Surface the brain's current learned self-model |
| Persona Slices 1–3 prompt strengthening | Trying to embody a fed answer | Reframed — embodiment is automatic once there's no fed answer |

**Migration (host-ratified): strip existing universes and let them re-learn from
their own history.** Keep each universe's activity/branch history; drop its
authored soul identity (purpose, etc.). The brain reconstructs its body/identity
from the real history and becomes curious about its founder. This makes
`patch-loop-live` the first and richest test case: deep history, blank self-model,
watch it rebuild understanding from its own data.

## 7. Relationship to the persona slices already shipped

- **Slice 1 (`#1382`)** — persona surfacing + embody prompt. *Kept* (the
  surfacing scaffold is reusable) but its embody framing is subsumed.
- **Slice 2 (`#1386`)** — `set_persona_name` verb. **Reverse:** it is a founder
  button that sets the name directly (§6). The name must be learned.
- **Slice 3 (`#1395`)** — stronger embody prompt. Live test showed it did not move
  the voice (the control_station prompt is likely not even loaded by claude.ai;
  only the always-present `instructions` apply). Subsumed: embodiment is not a
  prompt problem, it is a *no-fed-answer* problem.

The honest read: the persona work was iterating the wrong layer. This note relocates
the fix from "say the persona better" to "let the brain have no pre-given self."

## 8. Open questions / risks (for slicing)

1. **Self-model store + learning loop.** Where does the brain's learned self-model
   live (OKF bundle? a learned-summary doc the brain writes?), and what is the
   learning cadence — every interaction, every branch completion, a periodic
   re-assemble? This is the core build.
2. **Bootstrapping cold.** A brand-new universe with zero history has nothing to
   learn from yet. Confirm the desired first-contact behavior is pure curiosity
   (ask the founder), with the self-model genuinely empty until signal arrives.
3. **Cross-client surface.** `get_status` shape change is consumed by both ChatGPT
   and Claude (mandatory both-client `ui-test`). Any persona-block change ships
   with that check.
4. **Migration safety.** Stripping authored souls is a write to live universe
   state — needs a reversible/auditable migration, not a destructive one.
5. **What persists as "signal" vs "noise."** The brain learns from *all* activity;
   define what it weights (founder's explicit intent vs incidental branch output).

## 9. Proposed build slices (draft, for approval)

1. **Strip + generic-name substrate.** Universe creation assigns a generic
   placeholder name; remove meaningful-name-at-birth. (Foundational, low-risk.)
2. **Retire the founder setters.** Deprecate `set_persona_name` and demote
   `set_premise` from "writes identity" to "founder signal the brain ingests."
3. **Brain self-model store + curiosity drive.** The blank self-model + the
   learning loop that updates it from signal + activity; first-contact curiosity.
4. **`get_status` persona block = learned self-model.** Surface the brain's current
   self-understanding (sparse/curious when new); both-client `ui-test`.
5. **Migration.** Strip existing universes' authored souls (reversible), keep
   history; verify `patch-loop-live` reconstructs its body from activity.

Each slice gets the standard gate: TDD, opposite-provider review, live chatbot
`ui-test` read via the CDP route, before it is called done.
