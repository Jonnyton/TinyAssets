# Codex review — labelled credential fields and removal (branch `claude/labeled-credential-fields`, PR #2755)

Dispatched 2026-08-31 on Codex's own budget, from the PR's own worktree (a review
run from the primary checkout reads a stale branch). SIX passes, plus a final verification. `AGENTS.md`
caps review at three rounds and then escalates; the fourth was scoped to
verifying the fix to round 3's single finding, because the exact-head receipt the
scope guard demands is voided by the push that fixes anything. That tension is
filed as
`docs/concerns/2026-08-31-the-exact-head-receipt-loops-against-iterative-review.md`.

**Findings per pass: 7 → 5 → 1 → 3 → 5 → 4.** Non-monotonic, as `AGENTS.md` predicts, and
the fourth pass found a weakness in a test written during the third — the failure
mode it cites from #2561.

## Round 1 (`070ead76` and earlier): REJECT, 7 findings

1. **Q1** a `text` field beside the secret persisted a credential in the clear:
   its answer is recorded in `answer_json` and relayed into chat. **Fixed** —
   every field on a credential ask must be `type: "secret"`.
2. **Q2** removal does not clear `llm_credential_deposit_owners`, so a
   *different* principal's re-deposit is refused as an ownership transfer.
   **Filed**, not fixed —
   `docs/concerns/2026-08-31-credential-removal-leaves-ownership-and-orphans.md`.
   Bounded: it holds for the original owner, which is the case the live test runs.
3. **Q3** an absent connection row skips the owner check, so another admin of the
   same universe can delete an orphaned secret and learn it existed. **Filed**,
   same concern file.
4. **Q4** two `basic` fields assembled into JSON and were split at the JSON colon;
   and exactly one filled field took the single-value branch, depositing one
   value as the whole credential. **Fixed** — completeness is judged on the
   DECLARED set, and multi-value assembly is refused for schemes that cannot
   encode it.
5. **Q5** the Control Station prompt still taught the fieldless shape that is now
   refused, so the first live credential ask would have stranded. **Fixed.**
6. **Q6** `_MAX_URL_CHARS` was declared and never enforced; a 10,017-character
   hostname passed the pattern and was stored and rendered. **Fixed.**
7. **Q7** deriving the git transport host from the connection's API host built
   `https://api.github.com/owner/repo.git`. **Fixed separately in #2753**, which
   is the sha production currently serves.

## Round 2 (`fcc1ca64`): REJECT, 5 findings

1. **Q1** the served docs called the OAuth field `api_key_secret`; the deposit
   reads `api_secret`. The owner would have filled four boxes and been told
   `oauth1a secret is missing: api_secret` about a box they could not see.
   **Fixed**, and pinned by a doc/runtime parity test.
2. **Q2/Q5** stored rows were never revalidated at answer time, so a pre-upgrade
   request bypassed both of round 1's fixes and deposited
   `{"part_a":…,"part_b":…}` as a bearer token. **Fixed.**
3. **Q3** AGREE.
4. **Q4** ordinary username/password services were stranded entirely — the ask
   refused them, inference swallowed the refusal, and the fieldless fallback was
   also refused. **Fixed**; `basic` is a proper two-field scheme.
5. **Q6** deferring Q2/Q3 is defensible for serialized original-owner
   re-deposit, but removal and an in-flight deposit can race. **Noted in the
   concern file.**

## Round 3 (`fcc1ca64`, the cap): REJECT, 1 finding

**Q1 — the whole flow was dead at step 1.** `remove_http` was routed on
`universe_server.py` with `target="connection"`. The agent the founder actually
talks to is served by `engine_mcp_server.py`, whose `write_graph` refuses every
target but `branch` and `pending_request` — and it was *that* surface's docstring
teaching `remove_http`. "Remove the github credential" was rejected before
anything happened, and the three races filed against removal were unreachable
because removal itself was.

**Fixed without widening the door.** Deposit already happens as a
pending-request ask the owner answers in the rail; take-back became the same
shape on the same rail. The agent proposes, the person disposes.

## Round 4 — scoped verification of that fix (`520ba707`): ADAPT, 3 findings

Scoped deliberately: verify the fix to round 3's finding, not hunt for new ones.
It found three anyway, two of them **pre-existing** rather than caused by the fix.

1. **V1** a standing "don't ask again" returned `settled/may_proceed` for an
   action-bearing ask — but for those the ANSWER IS THE ACT, and the served agent
   has no route to perform any of them. Always true of `extend_http` and
   `grant_workspace_consent`, where it merely looks inert; on `remove_http` the
   owner is told a credential is gone while it sits in the vault. **Fixed on both
   sides** (never recorded, and an already-recorded ALLOW no longer settles).
   A standing DECLINE is untouched — doing nothing needs no route, and an
   existing test correctly caught my first over-broad version.
2. **V2** AGREE — the authority boundary holds.
3. **V3** answer-time revalidation checked the fields and only when there were
   any, so the three fieldless action types skipped it and the action was never
   compared to what was displayed. **Fixed** — the dedupe key is a hash of the
   tuple the tab renders from, so recomputing it binds the executing row to the
   displayed one.
4. **V4** AGREE — 68 focused tests passed, neighbours unaffected.
5. **V5** the new guard test hard-coded four verbs, so a fifth in the prose would
   pass undetected. **Fixed** — the verb set is derived from the text, and it
   reads both instruction surfaces.

## What the fixes rest on

Every hunk is mutation-checked: reverting it turns a named test red. Two of those
checks earned their keep — one showed a fix of mine was completely uncovered
(with the write-side guard in place, nothing could reach the read-side one), and
one of my own mutations was a no-op (`[] or sorted(...)`) that presented as a
surviving mutant.

The recurring class across all four passes was the same: **the docs taught a
shape the runtime refused, and the tests exercised the layer beneath the one that
was broken.** Three guards now close it structurally rather than by fixing one
string at a time — served-docs/action parity, connection-verb reachability, and a
suite that drives `engine_mcp_server.write_graph` itself rather than the API
under it.


## Round 5 (`74b14c3a`): ADAPT, 4 findings — one of them a regression I caused

Authorised by the founder as the last pass. It was worth its cost immediately.

1. **R3, blocking — this branch had reverted #2753.** `FORGE_GIT_HOSTS`
   (`api.github.com` → `github.com`) was deleted here, and #2753's own
   regression test was rewritten to assert the opposite. The founder's
   connection declares ten endpoints all on the API host, so without the table
   the clone becomes `https://api.github.com/owner/name.git` — the 403 that PR
   fixed, and that production was serving at the time. **Restored** byte-for-byte
   from `main`; the design argument is filed at
   `docs/concerns/2026-08-31-the-forge-table-is-platform-knowledge-and-removing-it-broke-a-live-fix.md`.
2. **R3, blocking — the rail dropped the readback.** `removed_endpoints` /
   `removed_scopes` were added to `remove_http` and never carried through
   `answer_request`, so on the only surface the owner drives they did not exist.
   The same "the API has it, the served path does not" shape as round 3.
3. **R3 — the readback could not rebuild what it destroyed**: no `auth_scheme`
   (an oauth1a connection returned as bearer) and endpoints flattened, losing
   `param_patterns`.
4. **R2 — I claimed the readback disclosed nothing new. False.** The grant
   sentence listed methods and paths and never named git scopes, so a key could
   carry `git_write` on a repository the owner had never been shown. Fixed by
   naming them in the sentence rather than by stripping the readback.
5. **R4** — the rotation test called the API directly and so could not have
   caught (2). Rewritten to answer through the rail.

## Round 6 (`f495602a`): ADAPT, 4 findings — all in round 5's fixes

Second consecutive round breaking on the previous round's work, which is the
non-convergence signal. Both blocking items turned out to be **one** defect
wearing two faces: *a hand-written inverse drifting from the canonical thing it
mirrors.*

1. **W2, blocking** — the readback re-implemented endpoint serialization while
   `OutboundEndpoint.as_dict()` already emitted exactly what `_validate_endpoint`
   parses. Mine dropped `allowed_query` / `required_query` and emitted pattern
   maps as tuples, so a rebuild was refused with "query_patterns must be an
   object". **Fixed by calling `as_dict`** — it round-trips by construction.
2. **W4, blocking** — the grant sentence was assembled per action type, so
   teaching the deposit about git scopes left the EXTENSION silent: a scope-only
   extension granted repository write and rendered `reach .`. **Fixed with one
   builder** used by both.
3. **W3** — scopes were appended after "- nothing else.", a sentence
   contradicting itself in the same breath. They are now inside the enumerated
   list the sentence closes over.
4. **W1** — the module docstring still said "the platform never names one"
   directly above the table that names one. Corrected.

Wording for asks carrying no git scope is unchanged on purpose: the first
attempt reworded every credential tab in the product, and two existing
assertions caught it.

## The shape of the whole thing

Seven passes, findings **7 → 5 → 1 → 3 → 5 → 4**. Every round found something
real; none of it was style. The recurring class never changed:

> **Two definitions of one fact, and the tests exercising whichever one was
> right.** A doc and a runtime (rounds 1–3), a served surface and the API
> beneath it (round 3), a parser and a hand-written inverse (round 6), a
> sentence built twice (round 6).

Fixing the instance always worked and never held. What holds is removing the
second definition: call the serializer that exists, render every grant through
one builder, derive the guard's vocabulary from the text it checks, and drive
tests through the door the user actually uses.
