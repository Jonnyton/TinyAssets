# Tasks — universe visibility

> **Reconciled against `origin/main` 2026-07-22.** No task here is complete, so
> nothing is checked off. What changed is the *evidence*: `main` already has a
> partial visibility substrate that this change must reconcile with rather than
> build beside. Two findings matter most:
>
> 1. There are **two uncoordinated visibility mechanisms** already — a
>    per-universe public/private bit (`tinyassets/api/permissions.py:59`) and a
>    separate per-branch `visibility` field (`tinyassets/api/branches.py:380`).
> 2. Current code **defaults undeclared universes to public**
>    (`permissions.py:78-80`), which is the exact inverse of task 2.3.

## 1. Define the model

- [ ] 1.1 Enumerate visibility levels and the capabilities each grants to an unauthenticated reader
      (existence / metadata / content as separate grants)
  - Current state on main: only a **binary** public/private bit exists
    (`universe_public_read_allowed`, `permissions.py:59`). The
    existence/metadata/content split this task asks for does not exist — today a
    reader who can read at all can read everything.
- [ ] 1.2 Decide per-universe vs per-page granularity and how they compose
  - Current state on main: **both already exist and do not compose.**
    Per-universe = the rules-row bit (`permissions.py:59`); per-branch =
    `visibility: public|private` on branch records (`branches.py:380-381`,
    enforced at `branches.py:445-446` against `author`). This task is now partly
    a *reconciliation* of two shipped mechanisms, not a greenfield decision.
- [ ] 1.3 Decide the default for new universes
  - Current de-facto default on main is **public**: a missing rules row is
    treated as "no decision recorded → publicly readable"
    (`permissions.py:62-63,78-80`). Any decision here is a change of behavior,
    not a fresh choice.
- [ ] 1.4 Decide disposition of the legacy universes (concordance, workflow-voice,
      echoes-of-the-cosmos, default-universe) — explicit level or recorded grandfather reason
  - Still open, and now load-bearing: these were revived as dormant and
    **live-listed** on 2026-07-15, so they are currently enumerable by anonymous
    readers via the public default in 1.3.

## 2. Enforce it

- [ ] 2.1 Gate universe enumeration on the declared level
  - Partial on main: enumeration **is** gated — `_action_list_universes` skips
    entries failing `permissions.universe_access_allows(child.name)`
    (`tinyassets/api/universe.py:1195,1217`). But it gates on the binary bit,
    not on a declared level, and it cannot express "existence visible, content
    hidden". Not complete; do not re-add the gate, extend it.
- [ ] 2.2 Gate wiki/commons reads on the declared level
  - Partial on main: universe-scoped wiki actions are gated
    (`tinyassets/api/wiki.py:2491-2504`), but the commons is **deliberately
    ungated** — see the comment at `wiki.py:2490` ("is a shared surface and is
    not gated here"). The commons half of this task is untouched.
- [ ] 2.3 Fail closed on an undeclared level — never default to visible
  - **Contradicted by current code, not merely unimplemented.**
    `universe_public_read_allowed` returns `True` on a missing rules row
    (`permissions.py:78-80`) — undeclared resolves to *visible*. Note the
    function does fail *closed* on a genuine rules-read error
    (`permissions.py:81-89`), so the gap is specifically the missing-row case,
    which is currently by design. This task is a behavior reversal and needs a
    migration story for universes that have no rules row today.
- [ ] 2.4 Raw-DML forge probe per gate, proven RED without the gate

## 3. Prove it

- [ ] 3.1 Regression test: anonymous reader against each level sees exactly the declared surface
- [ ] 3.2 Re-run the first-contact ui-test and confirm what an anonymous caller can enumerate matches
      the declared intent
