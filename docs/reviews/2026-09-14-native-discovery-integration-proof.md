# Native discovery integration — September14 2026

Feature codex/select-agent-models, working tree based onc6e786ee. Continues the
approved Fable shape review; final approved release review is still unused.
No live deployment, real account inference/discovery or private workflow edit.

## Implemented

Fresh native account metadata now feeds the advisory picker for an accepted
discovered model scope. Refresh can add arbitrary new model IDs without a
platform release. Explicit accepted IDs retain owner-declared semantics and
cannot acquire extra scope from discovery. Default selection still omits the
model flag; failed/unknown enumeration preserves that usable default while
displaying the metadata gap. Enumerated rows and default rows have distinct
truthful UI labels.

Both sync and async chat selection refresh owned metadata outside assignment
locks/SQLite transactions and recheck ownership/member facts before launch.
Native selection is separate from HTTP selection and answering-model telemetry.
Missing, stale, unknown or revoked enumeration refuses before inference.
Cancellation releases the real temporary owned credential copy.

Foreground and background workflow selection prepare the same metadata outside
their fences, then validate it against the current exact member/custody inside
admission. Version2 native selection evidence records enumeration basis, default,
requested ID, source digest and observation interval; version1 owner-declared
evidence remains exact and strict. One-use invocation and current work lifecycle
checks are unchanged. No journal becomes authority, and no user branch is edited.

## Evidence

Seventeen new integration/record cases pass. These exercise real SQLite member,
credential custody, temporary snapshot, router, foreground compiler/session,
background queue/activation and settlement paths. Only the provider's metadata
and inference responses are synthetic. A second thread acquires both assignment
and SQL write fences during metadata IO, proving they are not held across it.
Picker refresh sees a newly added model; a negative case preserves provider
default on discovery failure. Both workflow cases settle exactly one reservation
with enumerated evidence. Strict version/schema checks reject malformed records.

Final18-file Windows Python3.14 group: **442 passed,3 skipped,62.21s**.
Same group actual Linux Python3.11.16/git2.47.3/bwrap0.12.0:
**444 passed,1 skipped,59.69s**. Results verified September14 at06:54UTC. The Windows
extra skips are actual POSIX shared-reader/sandbox checks, executed on Linux.
The shared skip requires a configured real Codex test universe/snapshot; it is
not counted as live proof.

Command:
`python -m pytest -q tests/test_native_discovery_integration.py tests/test_native_model_discovery.py tests/test_native_model_execution.py tests/test_native_model_authority.py tests/test_run_provider_session.py tests/test_providers.py tests/test_provider_served_router.py tests/test_served_model_preferences.py tests/test_model_options_api.py tests/test_interactive_http_agent.py tests/test_work_model_selection.py tests/test_provider_invocation_selection.py tests/test_model_options.py tests/test_app_model_picker.py tests/test_app_model_choice.py tests/test_agent_workflow_fences.py tests/test_background_budget_finalization_e2e.py tests/test_background_served_provider.py --tb=short --show-capture=no --disable-warnings -rs`

Linux uses `python3 scripts/linux_oracle.py --` with the same arguments and
GIT_DIR/GIT_WORK_TREE pinned to this feature checkout from WSL Ubuntu.
Ruff, strict OpenSpec and diff checks pass. Plugin mirror/import passes439files.
Canonical brand generator updates only the app checksum; brand parity passes.
Synthetic DOM exercises label rendering, not a live signed-in browser session.
The first two picker integration tests needed their fixture's current home
created through set_founder_home; no production authorization was weakened.

## CI ratchet correction, verified September14 at07:09UTC

Remote c6e786ee required-tests run34814329571/job103881747426 identified exactly
two new failures, both channel-agnostic ratchet checks. The correction moves the
bounded metadata transport to native_jsonrpc_discovery.py and describes method,
field, handshake and pagination differences with a trusted executor registration.
It reuses command resolution and configured labels without changing actual-model
telemetry. No gate exemption or upward baseline change: total references682→681.
A real subprocess test uses different methods/fields and an arbitrary future
model ID through the same transport; this is synthetic metadata, not an account.

The previous command plus tests/test_channel_agnostic_ratchet.py now passes
**458 Windows/460 Linux**, **3/1 skips**, **61.53s/54.85s** respectively. Linux
uses the same pinned working-tree oracle described above. Ruff and diff checks
pass; plugin mirror/import passes439files. The Windows group was repeated because
its earlier closed tool session's terminal output could not be recovered; no
success was inferred from that missing output. Skip meanings are unchanged.

## Remaining

Actual connected-account CLI proof, Claude's direct enumeration seam, Windows
shim metadata support, and broader unknown-executor registration remain unproven.
Legacy/explicit grants are not silently widened to discovered scope. Workflow
HTTP tools/round allowance, final exact-head review, CI for this new diff,
deployment and ordinary rendered app acceptance are still pending. The old
four chat/workflow authority refusals remain pinned and unchanged.
