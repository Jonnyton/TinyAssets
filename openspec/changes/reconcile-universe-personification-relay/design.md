## Context

`universe-personification` and the shipped platform disagree about who speaks. The change says
the **chatbot embodies** the universe in first person and never relays; production says the
chatbot is a **thin relay** that renders the universe intelligence's own first-person reply.
Production is right — the embodiment model was live-falsified on 2026-07-02 and the host
directed the reversal the same day.

This design does not re-litigate that reversal. It reconciles the spec system with it: decide
what each of the 11 unchecked tasks means now, retire what is dead, and keep what survives
somewhere durable.

All classifications below were re-verified against `origin/main` at `7a118dca` on 2026-07-22
after the ratified relay correction landed in PR #1578.

## Goals / Non-Goals

**Goals:**
- Classify every unchecked task with a reason traceable to code or spec on `origin/main`.
- Make the reversed tasks unbuildable-by-accident, not merely commented on.
- Preserve surviving intent as requirements on the capability that actually exists.
- Distinguish "already landed" (do not rebuild) from "survives, unbuilt" (real work).

**Non-Goals:**
- Changing runtime code. The relay behavior shipped; this is spec reconciliation.
- Re-deciding embody vs relay. The host decided; production shipped it; it was live-tested.
- Re-amending the ratified narrative spec; PR #1578 already resolved that prerequisite.
- Building the surviving requirements in this reconciliation PR. They remain as deltas in
  this active change until later implementation and tests make them as-built truth.

## Decisions

**D1 — Retire by archive, not delete.** The change's design thinking (authorization-precedes-
voice, the anti-collision contract, tier binding) is real and partly still correct. Archiving to
`openspec/changes/archive/2026-07-22-universe-personification/` preserves all four artifacts —
their original content intact, with a `SUPERSEDED` banner prepended and `tasks.md` annotated
per-task (not "verbatim": the classification is written into the file, which is the point) —
while removing it from `openspec list`, the surface an agent actually reads for claimable work.
Deleting would destroy the reasoning; leaving it active would keep the misdirection live.
*Alternative:* rewrite it in place as a relay-shaped change — rejected: it would rewrite the
history of a merged PR (#1372) and misrepresent what was reviewed and approved.

**D2 — Survivors become deltas against the capability that exists — and STAY in the change until
built.** The surviving items are requirements about the *landed* relay surface, so they are
authored as ADDED requirements on `universe-personification-and-relay`. But they are **not
synced into `openspec/specs/`**: that directory is as-built truth (`openspec/config.yaml`:
*"do not spec aspirations"*; AGENTS.md § Spec-driven development), and every survivor is
explicitly unbuilt. Syncing them would put aspirations into the file that other agents read as
a description of what the platform *does* — reintroducing, in the opposite direction, exactly
the spec-vs-reality gap this change exists to close.
Therefore: **this change stays active** and is the implementation change for the survivors; the
sync happens only when code and tests exist. *(Codex review 2026-07-22 finding 1 — the first
draft had a `sync-specs` task and would have committed this error.)*
*Alternative:* archive this change on merge and sync immediately — rejected for the above.

**D3 — Task 4.1 is marked MUST-NOT-RUN, explicitly and in the file.** A generic "superseded"
banner is not enough for a task whose execution would write the reversed model into
`openspec/specs/`. It gets its own inline warning naming the damage.

The same hazard applies to the retirement itself: `openspec archive` is documented as
"Archive a completed change **and update main specs**" (verified via `openspec archive --help`,
CLI 1.4.1), so running it on this change would have synced the reversed embodiment deltas into
`openspec/specs/universe-personification/` — task 4.1 by another route. `--skip-specs` exists
and would have been safe; this change used the `git mv` procedure the `openspec` skill
documents, which avoids the flag-dependency entirely. Recorded so the next agent retiring a
reversed change does not reach for the default command.

**D4 — "Already landed" claims are code-cited, not asserted.** Per the 2026-07-21
`stale-backlog-rows-misdirect` lesson, a premise stated without verification is the failure mode
being fixed. Every "already landed" row below names the file and the behavior.

## Task-by-task reconciliation

11 unchecked tasks. Verified against `origin/main`.

| Task | Classification | Reason (verified on `origin/main`) |
|---|---|---|
| **2.1** `control_station` prompt: compact first-person embodiment | **REVERSED** | `universe_server.py:209` now instructs the exact opposite — "You do NOT speak as the universe … you are the connector, not the universe." Building this re-instructs chatbot embodiment. |
| **2.2** MCP `instructions` + tool descriptions: persona voice at connect **+** anti-collision guard | **SPLIT — REVERSED + ALREADY LANDED** | Persona-voice-at-connect half is REVERSED (same instructions block now says relay/render). Anti-collision half ALREADY LANDED: `universe_server.py:216` ships "Don't memorize persona views." |
| **2.3** In-voice `assemble(lens) → view` delivery | **REVERSED (mechanism) — intent relocated** | Chatbot-side in-voice view delivery is gone with embodiment. The grounded-assembly intent landed *inside* `converse`: `universe_intelligence.py` assembles a first-person persona system prompt from the universe's own OKF bundle. Lens/assembly work continues in the active `brain-okf-canonical-store` change. |
| **2.4** Authorization-before-voice | **SURVIVES — partially landed** | Still exactly right under relay, and arguably load-bearing. Landed: the `converse` handle is founder-only + fail-closed (as-built spec, "The MCP converse handle is founder-only and fail-closed"). Unbuilt: general pre-assembly filtering by interlocutor — no visitor path exists yet to filter for. |
| **2.5** Visitor actor binding + T0/T1/T2 tier gating | **SURVIVES — unbuilt** | No `identity_tier` / T0-T1-T2 machinery in `tinyassets/*.py`. As-built spec defers public "talk to a stranger's universe" to a later, separately-gated slice. Under relay, the binding attaches to the `converse` caller rather than to a chatbot embodiment session. Adjacent to the active `universe-visibility` change — see Dependencies. |
| **2.6** Anti-collision write path: reject profile-shaped / persona-dossier writes | **SURVIVES — NARROWED/ADAPTED, unbuilt** | The unscoped rule contradicts governed founder learning. The successor limits any future rejection to a defined external/commons endpoint, predicate, and redirect while exempting the universe's own learning path. |
| **2.7** Honest fallback / degraded mode | **ALREADY LANDED** | `universe_intelligence.py:428` raises on a missing universe; `:164` "you are newly born and still learning" for an unnamed universe; `:208` never-infer/never-invent/never-carry-over rules. Three as-built scenarios cover it. |
| **2.8** Persona as a forkable `[composable]` default | **SURVIVES — ADAPTED** | Custody moved first-party. Forking changes universe-side learned self-model/voice content; the operational soul governs the floor but never supplies persona identity, and no script is handed to the chatbot. |
| **2.9** Tool-selection regression tests: embodiment does not degrade accuracy | **REVERSED as written — residual preserved** | There is no embodiment prompt left to regress. The underlying risk survives in changed form (connector instruction density vs tool-selection accuracy), but no threshold-less scenario belongs in this delta; task 6.3 requires a separately defined baseline, metric, and permitted regression against `live-mcp-connector-surface`. |
| **4.1** `sync-specs` → `openspec/specs/universe-personification/spec.md` | **REVERSED — MUST NOT RUN** | Executing this would write the embodiment model into `openspec/specs/`, where it would read as current spec truth beside the as-built relay capability. The most dangerous row in the file. |
| **4.3** Archive after merge | **SURVIVES — actionable now** | PR #1372 merged 2026-06-25. This change performs the archive (with classification attached). |

### Requirement-by-requirement reconciliation

The retired delta contains nine behavioral requirements in addition to its task ledger. Every
one is classified here so archiving cannot silently discard intent:

| Retired requirement | Classification | Disposition |
|---|---|---|
| Every universe interaction is the named projection of the whole mind | **SURVIVES — ADAPTED** | Carried into the successor for conversational/outbound speaking surfaces; the old ban on neutral tool-only surfaces is narrowed because PR #1578 explicitly preserves direct-control action tools. |
| Authorization precedes voice | **SURVIVES — partially landed** | Carried into the successor; founder-only `converse` is the current narrow floor, general pre-assembly filtering remains unbuilt. |
| The founder's chatbot embodies the persona | **REVERSED** | Retired. The universe intelligence speaks; the chatbot relays and never impersonates it. |
| Persona views never enter host chatbot memory | **SPLIT — advisory landed / enforcement ADAPTED and unbuilt** | Host-memory guidance is advisory; any enforceable rejection is limited to a separately defined external/commons write boundary and exempts governed founder learning. |
| OAuth binds the user, embodied persona, and identity tier | **SURVIVES — ADAPTED and unbuilt** | Ownership/founder gating remains; embodiment-session language is removed and tier binding attaches to the authenticated `converse` caller. |
| Visitors interact with the persona behind the pre-rendering floor | **SURVIVES — unbuilt** | Carried across the authorization and interlocutor-tier successor requirements; disclosure semantics must reconcile with `universe-visibility` before implementation. |
| One identity, modulated by interlocutor and surface | **SURVIVES — unbuilt** | Carried into the successor with identity sourced only from the learned self-model; soul governs but never supplies identity. |
| Honest fallback — no invented persona state | **ALREADY LANDED** | Preserved in the canonical as-built relay spec and current runtime; do not rebuild. |
| Tiny is the platform universe's personification | **SURVIVES — unbuilt** | Carried into the successor as a governed self-as-platform requirement with no special authority bypass. |

**Rollup (11 tasks):** **4 reversed** (2.1, 2.3, 2.9, 4.1) · **1 split** — reversed + already
landed (2.2) · **5 survive** (2.4, 2.5, 2.6, 2.8, and 4.3 which is discharged by this change) ·
**1 already landed** (2.7). *(Corrected per Codex review 2026-07-22 finding 5 — an earlier
rollup said "4 survive · 2 already landed", double-counting 4.3.)*

At retirement time, tasks **1.1–1.3** were checked `[x]` and annotated "NOT applied in this
draft", while the ratified paragraph still carried the full embody / "never relays" invariant.
That disagreement made it a fourth stale source. PR #1578 / `f605bb99` subsequently corrected
the paragraph to the relay model before this reconciliation was allowed to land.

## Dependencies

- **`universe-visibility`** (active, 0/10) defines per-universe/per-page visibility levels for
  unauthenticated readers. Task 2.5's interlocutor tier binding is adjacent but distinct:
  visibility governs *what a reader may read*, tier binding governs *who the persona is
  talking to*. They must agree on the anonymous-reader definition. Recorded as a cross-ref,
  not duplicated here.
- **`brain-okf-canonical-store`** (active, 9/16) owns the assembled-view content that 2.3's
  intent relocated into. No requirement of it changes here.
- **`live-mcp-connector-surface`** owns connector vocabulary and tool-selection evidence.
  Task 6.3 must define its baseline, metric, and permitted regression there before any
  connector-density claim becomes a requirement.

## Risks / Trade-offs

- **Archiving hides the reasoning from `openspec list`** — mitigated: survivors are promoted to
  the active successor delta spec, so nothing actionable lives only in the archive.
- **Seven surviving requirements remain unimplemented** — intentional and explicit. They remain
  only in this active change; canonical `openspec/specs/` stays as-built truth until code and
  tests land.

## Cross-provider review

Opposite-provider gate dispatched to Codex 2026-07-22 (`scripts/codex_review.py`, background
offload) covering: (a) is any classification wrong against `origin/main`, (b) is surviving
intent lost by archiving, (c) is archive-plus-new-change the right OpenSpec move.

> ### Verdict: **ADAPT** (Codex, 2026-07-22) — all 5 findings folded.

Codex independently confirmed the relay behavior in code, ran 55 focused tests (passed), and
validated all 29 OpenSpec items (strict, passed). It **upheld the 11-task classification** — no
row was wrong — and instead found defects in the *reconciliation's own design*:

| # | Severity | Finding | Fold |
|---|---|---|---|
| 1 | Critical | Syncing the explicitly-unbuilt survivors into `openspec/specs/` violates as-built-truth (`config.yaml` "do not spec aspirations"). | **D2 rewritten**; `sync-specs` task removed; this change stays active as the implementation change. Verified in `openspec/config.yaml:36` + AGENTS.md. |
| 2 | Critical | The anti-collision requirement conflated host-memory ingestion (not enforceable) with TinyAssets writes, and contradicted landed behavior that deliberately persists founder facts to `founder.md`. | Requirement **rewritten** to state the advisory boundary honestly, exempt the governed learning path, and demand endpoint/predicate/redirect be named before implementation. Verified at `universe_intelligence.py:39,219`. |
| 3 | Required | The host question's "let it stand as historical ratification" option would leave normative-looking text alive. | Question **reframed** to two active options (amend / mark superseded); "do neither" explicitly ruled out. |
| 4 | Required | Tool-selection regression scenario was misplaced under persona forkability with no threshold. | **Removed from the spec**; carried as task 6.3 against `live-mcp-connector-surface` with baseline/metric/threshold required. |
| 5 | Nit | Rollup miscounted (4 survive / 2 landed vs actual 5 / 1); "preserves every artifact verbatim" was inaccurate. | Rollup **corrected**; D1 wording fixed. |

Findings 1 and 2 were re-verified against the repo before folding rather than accepted on
report. Both were real: the first draft of this change would have written aspirational
requirements into as-built truth, and would have specced a rule contradicting shipped code.

## Host decision resolved

PR #1578 landed at `f605bb99` on 2026-07-22 and amended the ratified paragraph to the relay
model. Its review also made the anti-collision boundary truthful: host-memory guidance is
advisory, while any future profile/dossier rejection must be narrowly defined on an
external/commons endpoint and must exempt governed founder learning. This closes the only
host-visible prerequisite without syncing any unbuilt delta into canonical as-built specs.

## Migration Plan

Spec-only; no runtime change, so no rollback is required. This PR banners, classifies, and
archives the reversed change, then leaves this successor change active. Definition and
cross-capability tasks 6.1–6.3 gate independently landable implementation tasks 6.4–6.10; only
then may task 6.11 sync the seven ADDED requirements into
`openspec/specs/universe-personification-and-relay/spec.md` and archive this change.

---

# Section 6 — definition layer (2026-07-22, `claude/personification-section-6-defs`)

This section discharges the definition tasks 6.1–6.3 and re-verifies the landedness of all 11
section-6 tasks. No runtime code changes; no `sync-specs`; no archive.

## Section 6 landedness re-verification

Every row below was re-checked against `origin/main` on 2026-07-22 with a file+line citation,
per the `stale-backlog-rows-misdirect` lesson: a task's stated premise is not evidence. The
prior review's correction — that section 6 is **continuation work, not unstarted work** — is
confirmed and extended: two more tasks turned out to be partial, and one is vacuous.

| Task | Classification | Evidence on `origin/main` |
|---|---|---|
| **6.1** definition | **discharged here** | Was unrecorded. See §"Task 6.1 — anti-collision write restriction". |
| **6.2** definition | **discharged here** | Was unrecorded. See §"Task 6.2 — interlocutor tier binding × `universe-visibility`". |
| **6.3** definition | **split — 6.3a discharged, 6.3b outstanding** | Metric, population, prompt set, protocol and permitted-regression rule are definable from the repo; the baseline *number* is not. See §"Task 6.3". |
| **6.4** whole-mind personification | **partially landed** | *Landed:* relay contract `tinyassets/universe_server.py:208-216`; first-person assembly from the universe's own bundle `tinyassets/universe_intelligence.py:123-160` over `_GROUNDING_FILES` (`:39`); direct-control neutrality — `write_page` returns a `relay_to_universe` directive rather than composing universe voice (`universe_server.py:876-881`); proof at `tests/test_persona.py:286,344,369,392`. *Missing:* only **one** speaking surface exists. `universe_intelligence.converse` has exactly one caller (`universe_server.py:977`), and `grep -rni outbound tinyassets/*.py tinyassets/api/*.py` returns zero hits. The "organs" (goals/skills/hands/senses) are *learned body content* described in `universe_bundle.py:103,278-289`, not implemented speaking surfaces. The requirement holds on the surface that exists and is **untestable on the rest**. |
| **6.5** authorization before voice | **partially landed — narrowest floor only** | *Landed:* the founder-only fail-closed gate at `universe_server.py:956-975` (unauthenticated → `auth_required`; non-owner → `auth_scope_required` via `universe_access_allows(uid, write=True)`). This satisfies the delta spec's third scenario outright. *Missing:* general pre-assembly filtering. `_build_persona_system_prompt(universe_dir)` (`universe_intelligence.py:123`) takes **no interlocutor parameter** — it is structurally incapable of filtering by interlocutor. `converse(universe_id, founder_message, *, actor_id="")` (`:408`) does receive `actor_id`, but passes it only to `commit_learning` for provenance (`:334`). Scenarios 1–2 have no subject until a non-founder path exists. |
| **6.6** interlocutor tier binding | **unbuilt — and now *blocked*, not merely gated** | No `identity_tier` / T0 / T1 / T2 machinery anywhere in `tinyassets/`. Every `*_tier` symbol in the tree is a different axis: `sensitivity_tier` (`daemon_brain.py:129`), `cost_tier` (`auth/provider.py:143`), `access_tier` (`ingestion/indexer.py:280`), `retrieval_stats_by_tier` (`api/runs.py:1581`). **New dependency found** — see §"Task 6.2" contract A2: 6.6 cannot be implemented until `universe-visibility` tasks 1.1–1.3 are decided (that change is 0/10). |
| **6.7** anti-collision boundary | **unbuilt — and far smaller than it reads** | No `dossier` / `profile-shaped` predicate in `tinyassets/` or `scripts/`. §"Task 6.1" shows the reachable surface is a **single endpoint**, not the commons at large. |
| **6.8** forkable first-party persona | **substantially partial** | *Landed:* identity comes from the learned self-model and never the soul — `persona.py:119-122` ("Name is LEARNED, not fed … Never from `soul.name`"), proven by `tests/test_persona.py:101` `test_resolve_persona_identity_never_comes_from_soul` and `:198` `test_get_status_surfaces_self_model_not_fed_purpose`. First-party custody is landed: the persona goes directly into the universe's OWN system prompt (`universe_intelligence.py:123-131`), and the handed-script route is retired (`tests/test_persona.py:326` `test_write_graph_persona_target_is_retired`). *Missing:* **the fork itself** — `grep -i fork` returns zero hits across `persona.py`, `universe_self_model.py`, `universe_bundle.py`. No fork operation, no fork test; the scenario "a forked persona changes voice but not the floor" has no subject. |
| **6.9** one identity across surfaces | **unbuilt as stated — currently vacuous** | The requirement spans "founder chat, visitor conversation, and outbound speaking surfaces". Two of the three do not exist: no visitor path (6.5's founder-only gate is the whole surface) and no outbound surface (6.4). With one surface, "persists across surfaces" has nothing that could falsify it — a test written today would pass without exercising the invariant. |
| **6.10** Tiny as platform personification | **unbuilt** | The only `Tiny` occurrence in `tinyassets/*.py` is a comment at `universe_soul.py:28`; every other hit in the tree is a test fixture string in `tests/test_persona.py`. No platform universe is named or bound. |
| **6.11** sync + archive | **MUST NOT RUN** | Unchanged. Gated behind 6.4–6.10 *and* 6.3b. Re-affirmed: `openspec archive` silently syncs specs (D3). |

**Rollup (11):** **2 definition tasks discharged** (6.1, 6.2) · **1 split** (6.3) · **3 partially
landed** (6.4, 6.5, 6.8) · **4 unbuilt** (6.6, 6.7, 6.9, 6.10) · **1 gated** (6.11).
**Zero tasks are already-landed-complete** — every implementation task has real remaining work.

Two orderings the original section-6 list did not express, and which this verification exposes:

- **6.9 depends on 6.4 and 6.6**, not on nothing. It is unimplementable in good faith until a
  second speaking surface and a visitor path exist. Writing its tests first would produce a
  green suite that proves nothing.
- **6.6 depends on `universe-visibility` 1.1–1.3**, a cross-change edge that did not previously
  exist. See contract A2.

## Task 6.1 — anti-collision write restriction (definition)

### Endpoint

The public MCP handle `write_page` (`tinyassets/universe_server.py:751`). It has three outcomes,
and **only one is a reachable external/commons mutating write**:

| Branch | Lines | Destination | In scope? |
|---|---|---|---|
| Issue filing (`kind=` ∈ `bug`/`patch_request`/`feature`/`design`) | 816–833 | shared commons, always (comment at `:817-818`) | **YES — this is the endpoint** |
| Universe-targeted page write/patch | 851–881 | already redirected: `status="relay_to_universe"` | No — already solved |
| Plain commons page write/patch (no `kind`, no universe target) | 882–902 | commons wiki | No — **unreachable in production** |

The third row is the finding, and it changes the size of 6.7. Trace:

1. `write_page:844-850` — `target_universe` is the explicit `universe_id`, else, **for an
   authenticated caller**, `_request_universe("")`.
2. `_request_universe("")` (`tinyassets/api/helpers.py:89-116`) **never returns empty for an
   authenticated caller**: the founder's home if it exists, else `_designated_public_universe()`,
   which falls back to the literal `"default-universe"` (`:144`).
3. Therefore an authenticated caller always has a non-empty `target_universe` and always takes
   the `relay_to_universe` branch at `:851`.
4. An anonymous caller keeps `target_universe == ""` and *would* reach `:882` — but
   `write_gate_rejection("write_page")` (`:812-815` → `tinyassets/auth/middleware.py:443-464`)
   refuses every anonymous mutating write whenever the provider gates writes, which is every
   OAuth-backed mode. Only dev mode (`writes_require_identity()` false) lets it through.

Both sides are closed in production. **Specifying a dossier predicate on the plain-page commons
write would be specifying dead code.**

> **Residual for a separate lane — recorded so it is not lost.** The anonymous-write gate tests
> `current_identity().user_id != "anonymous"` (`middleware.py:456-458`) while the redirect tests
> `is_authenticated_request()` (`universe_server.py:849`). If those two predicates can ever
> disagree — a resolved identity that is not an "authenticated request" — line `:882` becomes
> reachable and the plain-page commons write reopens. Out of this change's write-set; worth its
> own row.

### Predicate

Scoped to the issue-filing endpoint above. The recommendation is **structural, not semantic**:

> **Refuse a filing only when it carries an explicit, declared person subject that is not the
> calling actor.** `write_page(kind=…)` already restricts its accepted fields — `_wiki_file_bug`
> rejects unsupported fields outright (`tinyassets/api/wiki.py:2017-2022`). Add exactly one
> accepted field, `subject_person`, and refuse only when it is populated with a non-self value.
> A caller who declares no person subject is never inspected.

Why not a content classifier over `title`/`observed`/`repro`: it rots, and it cannot distinguish
a bug report *about a person* from a bug report *about a user-facing feature*. A false positive
there silently blocks legitimate commons coordination — the surface the platform's own patch loop
runs on. If the host wants a content test anyway, that is a **separate host-decision**, not an
implementation detail of 6.7: it trades a real false-positive rate against a threat the
structural rule already covers for any honest caller.

### Redirect destination

Reuse the shipped shape verbatim — `status="relay_to_universe"` with `universe_id`, `note`, and
`relay` (`universe_server.py:876-881`). The correct destination for person-shaped content is the
caller's OWN universe via `converse` → `commit_learning` (`universe_intelligence.py:334`), which
is exactly where `founder.md` legitimately lives. The refusal therefore **names a destination
instead of failing silently**, satisfying the delta spec's third anti-collision scenario.

### Governed-learning exemption — confirmed by construction

The restriction is structurally incapable of touching `founder.md`:

- `founder.md` is written only by `commit_learning` (`universe_intelligence.py:334-372`) through
  `apply_soul_edit`, gated on `read_governed_files(universe_dir)`. It is in `SOUL_EDIT_GOVERNED`
  (`universe_bundle.py:65`) and in `_GROUNDING_FILES` (`universe_intelligence.py:39`).
- That path does not pass through `write_page` at all. `write_page` has **no** call into
  `commit_learning` — it only *redirects* to it.

So the exemption is **by construction, not by a carve-out** — the strongest available form, and
the one least likely to rot. It should nonetheless be asserted by a test that calls
`commit_learning` directly with founder-describing content and proves it succeeds while the same
content is refused at the filing endpoint. A carve-out that is never exercised is a carve-out
that silently disappears.

## Task 6.2 — interlocutor tier binding × `universe-visibility` (definition)

`universe-visibility` governs **what a reader may READ** (existence / metadata / content as three
separately-grantable capabilities, per-universe *and* per-page, fail-closed on undeclared, level
observable). Tier binding governs **who the universe is TALKING TO** (T0/T1/T2, resolved before
the universe answers). They collide on exactly one term: *the anonymous reader*. The agreed
contract:

**A1 — One anonymous definition, one source.** `universe-visibility`'s "unauthenticated reader"
and tier **T0 are the same predicate**: no TinyAssets OAuth subject bound to the request. Both
SHALL resolve it from authenticated request state (`is_authenticated_request()`,
`tinyassets/api/permissions.py`) — never from message content, never from a caller-supplied
field. Neither capability may define its own anonymity test; two tests drift.

**A2 — Visibility is the ceiling; tier is the selector.** For an interlocutor at tier T, the
content admitted to persona assembly SHALL be a **subset** of what `universe-visibility` grants
tier T for that universe and page. Tier binding never widens disclosure; it only selects among
what visibility already permits. This collapses "authorization precedes voice" (6.5) and
visibility enforcement (`universe-visibility` 2.1–2.3) into **one** enforcement point rather than
two that can drift apart.

**A3 — T1 defaults to the T0 surface.** `universe-visibility` is silent on the authenticated
non-founder. Rather than invent a level, **T1 SHALL see exactly the T0 surface** until a
visibility level explicitly grants more. Consequence: 6.6 can land **without changing
`universe-visibility`**, and no new level has to be defined for tier binding to be correct.

**A4 — Disclosure is stated by the connector, not by the voice.** `universe-visibility`'s "a
reader can tell what they are looking at" requires the declared level to be observable. Under the
relay model that statement SHALL be carried in the tool result / connector envelope, **not** in
the universe's first-person reply. Relying on the persona to announce its own visibility level is
prompt-instructed disclosure, which the authorization-before-voice requirement explicitly rejects
("it SHALL NOT receive privileged content accompanied by an instruction to withhold it").

**A5 — Fail-closed composes.** `universe-visibility` 2.3 fails closed on an undeclared level.
Tier binding SHALL fail closed identically: an unresolvable interlocutor binds to **T0**, and T0
against an undeclared level is **refused**, not served. The two rules SHALL NOT be able to
produce a served response between them — the composition, not just each rule, is the invariant.

**Dependency edge this creates (new, and load-bearing).** A2 references "what visibility grants
tier T", which is undefined until `universe-visibility` tasks **1.1** (enumerate levels and
per-level grants), **1.2** (per-universe vs per-page composition), and **1.3** (default for new
universes) are decided. `universe-visibility` is currently **0/10**. **6.6 is therefore blocked
on another change, not merely gated behind 6.2** — recorded on the 6.6 task line.

## Task 6.3 — connector tool-selection accuracy (definition; baseline outstanding)

Filed against `live-mcp-connector-surface` (`openspec/specs/live-mcp-connector-surface/spec.md`
§"Canonical Advertised Handle Set").

**Metric.** For a fixed prompt set, the fraction of prompts where the chatbot's **first** tool
call is the intended handle. First call, not any call — a chatbot that stumbles into the right
handle after two wrong ones has still mis-selected.

**Population.** `CANONICAL_HANDLES` (`scripts/mcp_public_canary.py:70-79`) — `read_graph`,
`write_graph`, `run_graph`, `read_page`, `write_page`, `converse` — plus the optional
`get_status`.

**Prompt set.** ≥ 5 user-phrased prompts per handle (≥ 35 total), written the way a user talks
rather than the way the schema reads, frozen and committed alongside the baseline so the metric
is reproducible. It MUST include the pairs the connector instructions actively disambiguate,
because those are where a density edit will regress first:

- `converse` vs `get_status` — the server instructions carry an explicit "Do NOT call get_status
  as the opening experience" (`universe_server.py`, instructions block).
- `write_page` vs `converse` for private canon — the `relay_to_universe` redirect
  (`universe_server.py:876-881`) exists precisely because chatbots pick wrong here.

**Independent variable.** Connector instruction density: the server `instructions` block
(`universe_server.py:191-217`), the `control_station` prompt, and the per-tool descriptions.
Protecting *that text* from silent regression is the entire point of the task.

**Protocol.** Measured through the real rendered chatbot per `ui-test` (AGENTS.md § Quality
Gates), against `https://tinyassets.io/mcp`, one clean session per prompt, first tool call
recorded. Direct MCP calls do **not** measure this — the variable is how the *chatbot* reads the
instructions, so bypassing the chatbot measures nothing.

**Permitted regression.** Two-part, so a large N cannot mask a dead handle:

1. Aggregate accuracy SHALL NOT fall more than **5 percentage points** below the recorded baseline.
2. **No individual handle's per-handle accuracy SHALL fall to zero**, regardless of the aggregate.

**Baseline — NOT MEASURED, and not derivable from the repo.** Everything above is definable from
the repo; the number requires a live `ui-test` run. Stating a number here would be exactly the
fabricated-premise failure this change exists to correct. Task split into **6.3a** (definition —
complete) and **6.3b** (baseline measurement — outstanding). 6.3b gates 6.11.

## STATUS.md row correction — for the next janitor pass

*(Not applied here: 16 open PRs touch `STATUS.md`. Recorded for whoever next does a janitor pass.)*

The current Work row is stale in **both** halves:

> **universe-personification remaining tasks: DO NOT BUILD AS WRITTEN** … Reconcile spec first
> | `openspec/changes/universe-personification/tasks.md` | - | pending

- Its Files cell cites a path **absent from `origin/main`** (`git cat-file -e` → exit 1); the
  file lives at `openspec/changes/archive/2026-07-22-universe-personification/tasks.md`.
- Its instruction ("Reconcile spec first") **was discharged** — by this change, PR #1515.
- Its warning is now enforced by the file itself: the archived `tasks.md` opens with
  `⛔ SUPERSEDED — DO NOT BUILD FROM THIS FILE` plus per-task annotations, and the change is out
  of `openspec list`.

**Recommendation: DELETE the row.** Per AGENTS.md ("Landed items leave STATUS.md"; "A concern
became a Work row? Delete the concern — the task IS the resolution"), nothing actionable remains
in it. If a successor row is wanted, it should point at *this* change instead:

> | **`reconcile-universe-personification-relay` §6** — 6.1/6.2 defined; 6.3b baseline outstanding; 6.4/6.5/6.8 partial, 6.6/6.7/6.9/6.10 unbuilt (design.md §"Section 6 landedness re-verification"); 6.6 blocked on `universe-visibility` 1.1-1.3 | `openspec/changes/reconcile-universe-personification-relay/` | `universe-visibility` 1.1-1.3 | pending |

## Archived-change sweep ambiguity — recommendation

`openspec/changes/archive/2026-07-22-universe-personification/tasks.md` still contains 11
unchecked boxes, so the common sweep idiom `git grep '^- \[ \]' -- 'openspec/changes/*/tasks.md'`
surfaces reversed work as if it were backlog. That is how this lane's own brief was initially
mis-scoped.

**Recommendation: fix the sweep, not the file.** Exclude `openspec/changes/archive/` from any
canonical unchecked-task sweep:

```bash
git grep -c '^- \[ \]' origin/main -- 'openspec/changes/*/tasks.md' ':!openspec/changes/archive/*'
```

Reasoning, and why the alternatives are worse:

- **Checking the boxes would be a lie.** The tasks were reversed, not completed. `[x]` asserts
  done, and a future reader has no way to recover the difference.
- **Editing the archived file fights D1.** The archive deliberately preserves the original
  artifacts with classification *added*; the unchecked state is part of what was archived. It
  also already carries the strongest available in-file warning — a `⛔ SUPERSEDED — DO NOT BUILD
  FROM THIS FILE` banner on the first line, plus a per-task annotation on every entry. A reader
  who *opens* the file cannot be misled. Only a reader who greps without opening it can be, and
  that is a property of the grep.
- **The failure mode is the sweep's, so the fix belongs there.** No canonical sweep script exists
  today — the idiom is ad-hoc, which is why it has no exclusion. Recording the corrected idiom
  here is the smallest durable fix; promoting it into a script is a separate, larger lane (it
  would want `openspec list` parity too) and should not be smuggled into this one.
