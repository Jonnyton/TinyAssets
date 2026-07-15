# Auto-birth the founder's home universe on first connect (2026-07-15)

**Status:** approved (host directive, 2026-07-15) — supersedes the 2026-07-02
opt-in-birth decision.

## Decision

A connected authenticated founder **always** has a home universe. The first
authenticated `get_status` (the connector's opening call) with no home
**auto-creates + binds** a blank seed home universe and returns a compact
`first_contact: universe_created` welcome. A founder must **not** have to know to
ask for their first universe. Additional universes stay explicit
(`write_graph target=universe` / `universe action=create_universe`).

## Why this reverses 2026-07-02 (opt-in birth)

The 2026-07-02 decision made a status read pure — it returned an
"awaiting-creation" card and created the universe only when the founder
explicitly asked to meet it ("the request is the consent"). Rationale then:
"reads must be reads" and avoid a side-effect-disclosure paragraph on every
first reply.

Live dogfooding (2026-07-15) showed the failure mode the host rejected: a
founder who did not know the magic words never got a universe — they signed in,
had no home, and kept hitting the ownerless legacy `default-universe` (read-only
to everyone). Onboarding that depends on the user guessing an incantation is
broken. The welcome disclosure the 2026-07-02 decision treated as a cost is, in
fact, the desired onboarding beat.

## What is preserved (not a blanket "reads create")

- **`read_graph target=status` stays a pure read** (`readOnlyHint=True`). Only
  the dedicated `get_status` handle provisions on first contact; the canonical
  read handle never mutates state. `get_status`'s own annotation is corrected to
  `readOnlyHint=False` (idempotent + non-destructive: repeated calls converge to
  the same home).
- **Scope gate before reservation.** A founder lacking the create scope still
  gets the awaiting card (`get_status` is not a create-scope bypass), and no
  `founder_home` binding is left for a founder who could not create.
- **Single-birth under concurrency.** `daemon_server.claim_founder_home` reserves
  the home id atomically (`INSERT … ON CONFLICT(founder_sub) DO NOTHING`);
  materialization is serialized by a process lock so racing first-contact workers
  never double-create (no duplicate `create_universe` ledger rows). Schema
  init/migrations are also serialized (auto-birth made concurrent first DB access
  reachable on a fresh install).
- **Anonymous callers never birth**; `.active_universe` is never written on a
  founder birth; the create routes through the ledgered, scope-gated dispatch
  (founder `admin` grant + ledger entry).

## Where it lives

- Spec: `openspec/changes/universe-creation/specs/universe-creation/spec.md`
  ("First MCP contact" requirement + scenarios).
- Code: `tinyassets/api/status.py` (`get_status` `allow_first_contact_birth` +
  `ensure_founder_home`), `tinyassets/daemon_server.py`
  (`claim_founder_home` + serialized `initialize_author_server`),
  `tinyassets/universe_server.py` (`read_graph` opt-out + `get_status`
  annotation), `tinyassets/api/prompts.py` (control_station + meet_universe).
- Tests: `tests/test_first_contact.py`, `tests/test_get_status_primitive.py`.
- Review: opposite-provider (Codex) — auth/onboarding + host-decision reversal.
