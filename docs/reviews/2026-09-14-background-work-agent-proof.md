# Background work-owned agent integration

September 14, 2026, feature tree based on f4cd7ea5. Implements the background
portion of reviewed R3/R5/R6, not the user's background-self project. No private
workflow, prompt, approval, provider grant or saved model preference was edited.
The final approved Fable review remains unused; this is not a deployed claim.

## Behavior

The immutable existing `universe_self` opt-in now prepares the shared persona
and enters the same work-owned coordinator as foreground runs. Each inference
uses the background session's original task admission, receipt, claim and finite
attempt/queue/member budget. Invocation indices advance when armed, including
failed attempts. Background token/cost shares remain bounded by the old ceiling.

Fresh tool checks validate sealed invocation provenance, immutable snapshot hash,
current home/admin, running task/consumer/lease, activation epoch/executor/subject,
canonical background attempt/queue owner, receipt/claim/reservation and current
provider/member/custody. Caller context cannot substitute a chat request, another
carrier, model plan/selection or same-name universe in another root. The adapter
also refuses a later receipt or claim different from its initial work lineage.

Background admission formerly held the provider-assignment lock across the
provider call. It now releases that lock after atomic arming and before yielding
to the coordinator; dispatch and every subsequent step recheck current authority.
The actual HTTP discovery fixture acquires the exclusive assignment and SQL
write fences in another thread, including on the second model round.

Completed tool results are recorded before another inference. Cancellation,
activation/worker/lease changes, member revocation or lost admin stop before a
new tool or inference. Unknown model/tool outcomes and later capacity failure
leave the task failed without automatic whole-node replay. Ongoing tools stop at
the original two-invocation test allowance, preserving both completed results.
Missing engine routes reserve nothing; engine discovery failures release the
unused reservation at zero usage.

Native completion and capacity use work journal evidence too. No-effects proof
controls retry, not metering: a native capacity error may follow token spending.
With no observed usage totals, native work capacity failures retain an
indeterminate reservation and maximum charge, whether effects are known absent
or unknown. A known-unsent unavailable provider retains the existing zero path.

## Verification

Real claimed queue, compiler, admission, SQLite journal, router and engine-client
wiring are exercised. Remote model/MCP transports and persona preparation are
synthetic; this is not actual connected-account or rendered app proof.

- Initial combined twelve-file Windows group: 323 passed, zero skips, 102.32s.
  Linux ran that group plus `test_shared_background_self.py`: 335 passed, zero
  skips, 83.95s. After adding explicit activation executor/subject checks and six
  caller-substitution cases, targeted Linux background/shared-self/neutrality
  group: 55 passed, zero skips, 27.21s.
- Final native-accounting five-file Windows group: 211 passed, zero skips,
  51.65s. Same exact correction on Linux: 211 passed, zero skips, 40.37s.
- Supplementary Windows background/journal/diagnostics/neutrality group: 92
  passed, zero skips, 34.48s, before the final native-accounting correction.
- Ruff on edited runtime/new tests, strict OpenSpec validation, diff whitespace
  and 441-file plugin mirror/import checks pass.

Final accounting group command:

```
python -m pytest -q tests/test_background_work_agent.py tests/test_workflow_http_agent.py tests/test_mixed_agent_execution.py tests/test_provider_work_authority.py tests/test_work_agent_allowance.py --tb=short --show-capture=no --disable-warnings -rs
```

Linux uses `python3 scripts/linux_oracle.py --` with the same arguments, invoked
from WSL Ubuntu with explicit linked-worktree GIT_DIR/GIT_WORK_TREE. Environment:
Python 3.11.16, git 2.47.3, bubblewrap 0.12.0. Windows uses Python 3.14.

Initial combined command:
`python -m pytest -q tests/test_background_work_agent.py tests/test_background_budget_finalization_e2e.py tests/test_workflow_http_agent.py tests/test_work_model_selection.py tests/test_run_provider_session.py tests/test_provider_work_authority.py tests/test_agent_turn_coordinator.py tests/test_interactive_http_agent.py tests/test_mixed_agent_execution.py tests/test_work_agent_allowance.py tests/test_work_agent_authority.py tests/test_agent_workflow_fences.py --tb=short --show-capture=no --disable-warnings -rs`.
Linux adds `tests/test_shared_background_self.py`. The later 55-case Linux group
uses `tests/test_background_work_agent.py tests/test_shared_background_self.py
tests/test_channel_agnostic_ratchet.py` with the same pytest flags.

The earlier shared-persona unit test still expected direct provider dispatch
after admission. It now tests the actual persona-to-agent entry seam; the new
end-to-end files prove the real authorization and execution behind that seam.
Exact base f4cd7ea5 was exported with `git archive` into a separate temporary
directory outside the repository and the same `test_shared_background_self.py`
command was run: base 10 passed/2 failed; current 11 passed/1 failed. The removed
failure is that obsolete seam. The remaining Windows symlink privilege failure
is identical at base; Linux executes and passes that case. No skip/quarantine
was added. Base snapshot is under
`C:/Users/Jonathan/AppData/Local/Temp/tinyassets-background-baseline-6c754a3e4f6b4208b72f7c736d908436/tree`.

Initial background tests exposed a fixture without admin ACL; the fixture now
grants its synthetic owner admin rather than weakening runtime checks. Initial
native accounting tests caught the inheritance relation (rate-limited/overloaded
errors subclass unavailable), so the final predicate positively identifies those
capacity classes rather than excluding their superclass.

The older background authority unit fixture mocked role extraction but not its
newly shared snapshot lookup. It now supplies an ordinary synthetic snapshot;
the actual rollback test covers both role and snapshot refusal. Runtime early
snapshot failures retain the existing typed authority hold and hold projection.
That group plus native discovery integration/metadata and picker/choice tests
passes119Windows, zero skips,12.17s. No production authorization was weakened.

Final combined twenty-file verification completed September14 around19:32UTC:
497Windows passes with the one base-reproduced symlink-privilege failure above,
zero skips,110.44s;498Linux passes, zero skips,88.31s. It includes both background
unit and real-queue seams, assigned consumer, native discovery, picker/choice,
shared conversation and provider-neutrality checks. All final runtime corrections
and the updated rollback/persona unit seams are included.

Final combined command:
`python -m pytest -q tests/test_background_work_agent.py tests/test_background_budget_finalization_e2e.py tests/test_workflow_http_agent.py tests/test_work_model_selection.py tests/test_run_provider_session.py tests/test_provider_work_authority.py tests/test_agent_turn_coordinator.py tests/test_interactive_http_agent.py tests/test_mixed_agent_execution.py tests/test_work_agent_allowance.py tests/test_work_agent_authority.py tests/test_agent_workflow_fences.py tests/test_shared_background_self.py tests/test_background_served_provider.py tests/test_assigned_queue_consumer.py tests/test_native_discovery_integration.py tests/test_native_model_discovery.py tests/test_app_model_picker.py tests/test_app_model_choice.py tests/test_channel_agnostic_ratchet.py --tb=short --show-capture=no --disable-warnings -rs`.

## CI and remaining work

Prior f4cd7ea5 full CI34884340435 reports exactly one new failure: the obsolete
shared-persona seam above, already corrected here. It otherwise reports17826
passes,9 baseline failures,2 baseline collection errors,54 skips,10 deselected.
The same head's Windows installer104113067226 passed58s at19:07:59UTC; recurring
installer timeouts remain unexplained. New-head CI must be verified after push.

Next: integrated model-selector and real connected-account native metadata proof,
the reserved final Fable release review, fresh CI, protected deployed-SHA/canary,
then the exact rendered app request `Retest your workflow checklist`. Keep the
usable selector MVP ahead of additional within-turn fallback enhancements. No
background project takeover and no live completion claim.
