# Independent native-model recovery review

Scope: `codex/provider-native-model-defaults`, based on e1246a27. This is a new
incident repair after deployed c30daa8f exposed HTTP 400 rejection of the implicit
gpt-5.4 model. It is not another review of the completed CLI-upgrade patch.
Reviewers are Claude subscription subprocesses, read-only and independently
examining the implementation; no private workflow/binding/credential edits.

## Round 1: ADAPT, shape supported (2026-09-05 00:58 UTC)

Transcript: b2aa1be0-6b52-40d3-9cab-9ac7f0e008f8, Claude Fable 5.1.
The final-output wrapper retained a session-closeout message; the actual review
was read from the transcript's final review response, not inferred from that hook.

AGREE: omit an unspecified model argument, preserve the explicit operator
override and same provider/account, keep served config and sandbox restrictions,
do not retry a rejected choice with another model. Return provider-default when
the native CLI does not expose the resolved name.

Required followups, incorporated:
- Correct the runtime row's separate compiled model label.
- Document the operator-global knob; it is not user connection-local selection.
- Record that ProviderDefinition.model exists but is ignored by the CLI resolver;
  do not silently activate historical values, which may be placeholders.
- Cover unset/blank/explicit selections, labels and unchanged sandbox flags.
- Exercise omitted-model startup with the real CLI, not only mocked argv.

Baseline Windows Python 3.14: 153 passed, 3 skipped. New served-default tests on
the unchanged implementation: 3 failed on the unwanted -m argument, while 2
explicit override cases passed. This establishes that the regression assertions
can fail before the implementation fix.

## Round 2: ADAPT, implementation supported (2026-09-05 01:14 UTC)

Transcript: 515fb78c-4ac1-4af0-851c-c2717086d5bc, Claude Fable 5.1.
Reviewer traced and independently reproduced the three failed offline smoke
attempts. Two test assumptions, not absence of model capability, caused them:

- Responses-lite carries tool specs under input additional_tools items instead
  of top-level tools. Official CLI 0.153.4 source evidence:
  codex-rs/core/tests/suite/responses_lite.rs and core/src/client.rs.
- MCP tool specs may be deferred to discovery. Code-mode initial requests can
  omit the engine's tool names entirely; they remain in the isolate's ALL_TOOLS.
  Source: core/src/tools/spec_plan.rs and features/src/lib.rs. Requiring the
  initial request to contain read_graph is therefore not a valid startup gate.

Corrections incorporated: inspect both nonempty tool envelopes and recursively
walk their specs; retain forbidden shell-name checks; classic requests require
engine spec/discovery visibility; Responses-lite requires an advertised exec
wrapper and explicitly reports deferred engine visibility as unobserved.
Required MCP startup, fixture bearer, feature restrictions and fake 401 remain.

Reviewer accepted the hidden code-mode registry observation boundary as a
documented non-gating followup, not proof of exhaustive runtime tool isolation.
A stubbed discovery/execution turn could strengthen that offline coverage.
The actual rendered app retest remains mandatory. The credential-free custom
provider uses the bundled default, not the authenticated account catalogue.

Real CLI 0.153.4 smoke after correction: PASS, bundled gpt-6-astra selected,
engine_discovery=unobserved-code-mode-deferred. No real credentials/inference.
Expanded Windows suite: 193 passed, 3 skipped. Ruff and provider-routing spec
validation passed. Plugin mirror rebuilt, import probe passed. Linux oracle
could not start because Docker Desktop's Linux engine is unavailable; Linux CI
and image build remain mandatory before landing.

## Round 3: APPROVE (2026-09-05 01:22 UTC)

Transcript: 29e50284-96ff-47f2-9635-c206d7141d0f, Claude Fable 5.1.
The reviewer independently ran 123 focused tests, Ruff, strict provider-routing
spec validation and mirror comparisons: all passed. Both wire envelopes and
their absence checks, classic/lite discovery distinction, native/explicit
selection, and truthful labels/docs satisfy the previous review conditions.

Two non-blocking followups were incorporated without a fourth round: qualify
the startup output as no shell specs **in the initial request**, and remove the
diagnostic's reference to a possibly unassigned parsed-request variable. The
disabled shell feature check remains an independent supporting check; the hidden
registry observation limit is not claimed solved. These are wording/diagnostic
cleanup, not changes to model selection or authority.

VERDICT: APPROVE. Linux CI, verified deployment and the rendered app retest still
gate shipping/acceptance claims. The checklist goal remains unproven.
