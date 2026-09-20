# Dark storage/reset checkpoint — 2026-09-19

This checkpoint implements only canonical request/run correlation, source-pin
validation, terminal projection and the necessary deletion/reset privacy fences.
No production schema initializer, public route, selected-handler dispatcher,
model preference bridge, app control or private user workflow is activated.
It is **not** end-to-end consumer completion or permission to deploy/enable it.

## Implemented boundary

- `storage/conversation_run_admissions.py`: one atomic scoped intent-key/run
  reservation; history/default changes cannot alter retry identity; immutable
  terminal freeze; conversation-side durable pair dedupe; repair the separate
  runs projection flag after a crash without replaying effects.
- Current home/admin/tombstone checks under existing author writer. Existing
  shared reset barrier precedes that writer and rejects dirty recovery. Runs
  and conversation writers are never open simultaneously during projection.
- Source metadata/current visibility precedes private snapshot deserialization;
  active version/hash rechecked inside runs transaction; nested executable
  references refused for the self-contained adapter. Public foreign prompt
  definitions are not blanket-banned; existing compiler provenance remains.
- Trimmed terminal pairs expire private intent/context/terminal/selection data,
  retaining only scoped key/digest/run correlation. Owner account deletion erases
  the new table even after a home rebind; delayed projection cannot recreate home.
- `storage/conversation_reset.py` plus bounded `scoped_reset.py` integration:
  content-free exact admission identities join the reviewed reset plan/digest;
  existing committed witness authorizes idempotent payload expiry before cleanup.
  Recovery repeats expiry; pre-witness rollback retains original payloads.
  Existing home operational-DB refusal and active-run refusal remain unchanged.
- Legacy reset plans without the new action retain their digest/recovery meaning;
  no new fence/generation or raw owner identity is written in the journal.

The shared file/cloud dispatch primitive is not copied into this checkpoint.
Its prepared callback will supply existing `author_conn`/`runs_conn`; the consumer
must not re-enter `authorized_scope` under those writers. Its common guarded start
CAS alone decides execution. A free guard on a queued run is not orphan evidence.
No model receipt is invented: the dark terminal currently records attribution
unknown until the verified producer/preference integration is implemented.

## Evidence and truthful limitations

Windows final cohort: **265 passed**, no skips, 91.77 seconds (session 79750).
Linux final cohort: **265 passed**, no skips, 116.85 seconds (session 51791).
Both run the eight files below. Windows command is `python -m pytest -q` followed
by this list. No provider stubs grant real authority; tests use isolated temp data.

```text
tests/test_conversation_run_admissions.py
tests/test_account_deletion.py
tests/test_vault_account_deletion_guard.py
tests/test_conversation_store.py
tests/test_conversation_execution_history.py
tests/test_conversation_failure_history.py
tests/test_scoped_identity_reset.py
tests/test_scoped_reset_mutation_proof.py
```

Linux command prefix (append the same eight paths):

```powershell
wsl -d Ubuntu -- docker run --rm --network none --memory 2g --pids-limit 1024 --security-opt seccomp=unconfined -e PYTHONDONTWRITEBYTECODE=1 -e TMPDIR=/tmp -e TINYASSETS_DATA_DIR=/tmp/tinyassets-test-data -v /mnt/c/Users/Jonathan/.codex/worktrees/governed-experience-consumer-shape/TinyAssets:/src:ro -w /src --entrypoint python sha256:1b69d8536490285c7c7a13f1efe53ebe847696a99ae567dbbd2b9761ee0c530a -m pytest -q -p no:cacheprovider
```

This is the established isolated read-only WSL container route, with no network,
host/private data mounts or dependency installation. Canonical `linux_oracle.py`
cannot reach the local Docker Desktop engine; this equivalent working-tree route
uses the already installed immutable Linux/POSIX/bubblewrap image. CI remains
authoritative, and no hosted tests/deployment/live user acceptance occurred here.

Red-first evidence: missing module failed the initial 11 tests; source checks
failed with missing `authorize_source` after correcting the fixture's required
display name; former-home deletion exposed a real FK failure before its owner
mapping repair; expiry retained selection data before the new privacy assertion;
five reset cases failed on unclassified canonical history before integration.

The first expanded Linux cohort was 261 passed / 3 failed. All three failures
reproduced on untouched base `493bd98c` in detached `consumer-storage-baseline`
(session 55748), same immutable image:

- `test_operator_cli_loads_private_roster_and_emits_redacted_plan`
- `test_roster_rejects_credentials_and_unexpected_fields`
- `test_apply_resets_exact_founder_home_and_subject_grants_only`

The first two fixtures wrote a default world-readable roster while production
correctly required private mode. Valid POSIX fixtures now use 0600; a new negative
test still requires refusal of unsafe permissions. The third took a raw database
byte snapshot before its fixture WAL settled. It now explicitly closes/checkpoints
the fixture before the **unchanged byte-equality assertion**. No runtime permission,
preservation assertion, quarantine or production behavior was weakened. Focused
Linux rerun of those exact three passed (4.37 seconds).

`ruff check` on all six authored Python files, `git diff --check`, and
`openspec validate consume-user-bound-agent-components --strict` pass. Plugin
build staged 469 runtime files and returned `Import probe: probe-ok`; existing
mirror-parity test is included in the cohort. Earlier stale-mirror test failure
was resolved by the canonical build, not by weakening its assertion.

Independent exact-head code review is still required. Shape review and root
contract approval are not runtime approval. Full arbitrary UI/harness/setup,
model parity, shared execution integration and two-owner live adoption remain open.
