## Why

The engine's run cap (`_RUN_GRAPH_RATE_MAX = 20` per rolling hour per
universe; Codex gate #5, so a prompt-injected engine cannot spam an
already-approved effect branch) counted every engine-triggered run the same.
A normal GitHub job spends one run per API call — read the ref, create the
branch, read the file, write it, open the PR — so with one honest retry the
budget is gone. Live 2026-08-29 22:43Z, production, in the founder's presence:
`run_graph rate limit reached (max 20 per 60m); try again shortly.` on the
third attempt at a one-line README change; the universe stopped mid-job and
asked to be "sent back in after the run window clears". The founder's
standing rule is that a turn runs until finished unless the user interrupts;
here the platform interrupted it. Finding:
`docs/concerns/2026-08-29-run-rate-cap-stalls-a-normal-github-job.md`.
Founder 2026-08-30: "all the my call still open things are things you can
handle" — option 1 chosen (count only runs that carry an external write).

## What Changes

The count rule moves into one module, `tinyassets.engine_admissions`, and
becomes:

- Every engine-triggered run and every engine write (`write_graph`, remix,
  brain) is admitted as kind **`write`** and charged against the 20/h write
  budget **at admission, atomically** — nothing about a run is trusted before
  it runs, because the packet an effect fires is model-authored at run time
  (a branch cannot be classified as read-only up front).
- Admission returns a ticket (the ledger row id); `run_graph` and the
  scheduled-automation runner bind it to the run they start the moment its
  id exists (identity by row id, so concurrent admissions cannot cross-bind).
- When the run's effects have fired, the dispatcher settles the admission:
  if every effect that ran was a `GET`/`HEAD` authenticated call (or nothing
  ran, or the packet was refused before the wire and declared `GET`/`HEAD`),
  the row is **reclassified as `read`** and stops counting against writes.
  Any other sink, a non-`GET`/`HEAD` verb, or a verb the result and the
  packet do not name stays `write` — fail closed.
- `read` rows still count toward a new **total bound of 60/h** for runs of
  any kind, so a loop of read-only runs is bounded too (`run_graph` returns
  as soon as the run is queued, so this is what bounds compute on the
  owner's subscription; the concern's job is 5 runs + up to 5 retunes = 10
  admissions, 20 with a full retry, and 60 leaves 3x that). The refusal
  names the cap that refused.
- A run that fails or is cancelled fired nothing (effects fire only after
  success): `update_run_status` settles it as a read. An unknown sink stays
  a write. A settlement that arrives before the bind (a fast run) is kept in
  a `settlements` table and applied at bind time.
- Ledger storage shape: `admissions` gains `kind TEXT NOT NULL DEFAULT
  'write'` and `run_id TEXT NOT NULL DEFAULT ''` (additive `ALTER TABLE`;
  an old ledger's rows count as writes; migration happens inside the
  `BEGIN IMMEDIATE` transaction so two first touches cannot both pass). A
  symlinked or out-of-tree ledger is refused by every entry point; a missing
  parent directory is created, never read as "no cap".

Not changed: the approved-source-hash gate still pins WHAT runs; the
per-grant `unprompted_action_cap_json` still bounds the requests themselves;
browser-triggered runs have no admission row and are untouched (scheduled automations already paid this budget; they now bind and settle like foreground runs).

## Impact

- `tinyassets/engine_admissions.py` (new), `tinyassets/engine_mcp_server.py`
  (`_engine_run_admit` delegates; `run_graph` binds the run),
  `tinyassets/effectors/__init__.py` (settles after dispatch),
  `tinyassets/effectors/authenticated_external_call.py` (`packet_verb`).
- Storage: `<data_dir>/.engine_run_admissions.db` — two additive columns.
- Behaviour visible to a universe: a job made of reads and a few writes no
  longer hits the cap; the refusal text for the total bound names runs, not
  writes.
