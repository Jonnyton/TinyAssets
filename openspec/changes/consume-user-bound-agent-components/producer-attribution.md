# Reply producer integration (2026-09-19, dark)

Source map before change:

- `providers/call.py::_call_router_with_retry` already emits request-local
  ProviderResponse to response_observer before reducing it to text. Mock/error
  paths never emit an earned answer. `WriterExecutionReceipt` accepts only
  safe success labels and uses reported_model, never configured `model`.
- `graph_compiler.py::_build_prompt_template_node` discarded that observation;
  plain calls recorded provider unknown, policy events used configured metadata.
  The compiler timeout executor needs explicit callback plumbing, not an ambient
  context variable or global last-provider. Per-invocation collectors remain
  isolated through real parallel compiled graph calls.
- `ProviderRouter._call_meta` had configured model only; it now additionally
  projects the SAME existing strict receipt without changing that configured
  field's meaning. Foreground work-agent completion now forwards only its final
  completed response to the caller observer; no journal inference round is
  mistaken for the final answer. Observer failure does not replay a call.
- Compiler `ran` details carry `execution` using that unchanged existing receipt
  document. This uses existing run_events.detail_json, not a new table, carrier,
  public action or multi-model receipt. Existing legacy fields stay compatible.

Terminal correlation uses the already-pinned published version and content hash,
identifies a unique direct single-output prompt writer, reads at most two `ran`
events for that run/node, and requires its raw completed response to equal the
declared final reply. The strict normalized receipt is frozen in the EXISTING
terminal execution field and copied to existing conversation execution_json in
the same deduplicated pair transaction. Founder text never inherits it.

Unknown is intentional when there is a non-template transform, reducer, multiple
writers/output fields, repeated/aliased writer, missing/corrupt observation,
changed output or unprovable source. A synthesis prompt writing its own final
text can identify that producing response; it does not claim sole authorship of
all preceding evidence. A code-combined response cannot infer one producer from
the first/last graph response. Codex without reported_model remains unknown;
configured selection is never fabricated as telemetry.

Red-first evidence: two plain/policy parallel observer tests failed for absent
execution before plumbing; two router reported/unknown tests failed before
metadata projection; ten direct-writer/ambiguity tests failed before the helper;
two real compiler -> run-event -> canonical terminal -> conversation tests failed
because the pair path dropped the earned receipt, then passed after preserving it.
Remote transports are deterministic fixtures; compiler, provider bridge, event
store, exact snapshot validation and history projection are real code paths.
These tests are not production or provider-authenticated acceptance.

Windows 12-file cohort passed 194 tests, zero skips before upgrading the parallel
test from real concurrent node adapters to full LangGraph fan-out; that stricter
five-test file then passed too. Existing real work-agent 16-test suite passed.
Related authority/session suite had one introduced optional-observer signature
regression, fixed by omitting an absent callback; exact regression now passes.
Its Windows symlink privilege failure is unchanged on untouched baseline493bd98c;
no quarantine or permission behavior was changed. Matching Linux 12-file cohort
passed 194 tests in 108.33s, zero skips, including full compiled fan-out.
