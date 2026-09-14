Checked the hook's list. The running dispatch is this review's own output path; the two FINISHED items are the final release review I read in full at the start and the September 13 shape review, which I have now read and which agrees with my findings (owner-declared first, Claude enumeration returns None, no SDK writer); the vanished entries are prior harness reviews outside this brief, which forbids dispatch, edits and other lanes. Nothing further to advance. So the wrapper captures the findings rather than this note, the full review follows unchanged.

## Review: native model list and setup gap, head 4c65735b

Read-only, no dispatch, no edits. One test file run on Windows, 2026-09-14:

```
python -m pytest -q tests/test_native_model_discovery.py
34 passed in 0.91s
```

**Bottom line.** The whole authority chain for explicit native IDs and discovered scope already exists and is safe. The gap is two thin layers: the app never offers those scopes for subscription sources, and the server never tells the app whether a source can enumerate at all. The Claude enumeration proposal has one wrong premise: the existing JSON-RPC transport cannot carry the Claude control protocol, so a Claude adapter is a provider override, not a protocol registration.

### Item 1: declared IDs and discovered scope through the ordinary UI

- **AGREE, seam exists end to end.** The connector write parses `model_access` into the manifest type (`tinyassets/api/custom_agents.py:307-316`), which already accepts explicit IDs or discovered scope with validation (`tinyassets/provider_assignment_manifest.py:37-53`). The bind path re-resolves every member with its access (`tinyassets/provider_serving_binding.py:514-532`). At launch, explicit IDs are checked against scope (`tinyassets/providers/native_model_selection.py:104-116`) and re-checked against custody (`native_model_selection.py:60-73`). Nothing in the picker or preferences grants anything.
- **AGREE with the concern doc: the app is the only missing piece.** For subscription sources the proposal hardcodes the empty default ID (`tinyassets/onboarding/app.html:2208-2210`) and the button counts only the default row (`app.html:2213-2215`). The confirm text promises only "provider default" (`app.html:2229`).
- **Minimal patch, app only.** In the access panel, offer three consents per subscription source. Keep "provider default". Add "models this source lists", writing discovered scope, shown only when the server says enumeration is supported. Add "declare model IDs", a text input producing explicit scope with the empty default kept plus the typed IDs, with a confirm that says availability is unverified and a wrong ID fails the turn. All three go through the existing `bindingWrite` path (`app.html:2219-2223`), so the fallback order and the truthful basis labels (`app.html:2131-2138`) need no change.
- **DISAGREE_CONCERN, schema constraint to state in the UI.** Explicit and discovered are mutually exclusive on one member (`provider_assignment_manifest.py:52-53`). Owners cannot declare extra IDs on top of a discovered list. Present them as alternatives. Relaxing that is a storage-shape change and needs a proposal; do not do it in this lane.

### Item 2: catalogue discovery and the Claude probe

- **DISAGREE_EVIDENCE on reusing the JSON-RPC adapter for Claude.** The transport requires integer `id` and a `result` dict per reply (`tinyassets/providers/native_jsonrpc_discovery.py:109-114`) and speaks `method`/`params` (`native_jsonrpc_discovery.py:116-128`). The Claude control protocol uses typed envelopes with string request IDs and interleaved non-control messages. Registering a `NativeJsonRpcProtocol` on the Claude provider cannot work. The base class already anticipates this: an executor overrides `enumerate_models` (`tinyassets/providers/base.py:1268-1276`), and the discovery boundary is transport-agnostic (`tinyassets/providers/native_discovery.py:97-102`). That override is the seam. No new registry, no speculative protocol class until proven.
- **AGREE the bounded owner-custody probe is sound, with conditions.** Run it outside the daemon on the owner's machine against the owner's own login, never against production custody. Use an isolated config dir holding only credentials, mirroring how the launch env already isolates Claude (`base.py:647-664`). Reuse the existing launch conventions: strict MCP config with an empty server list and restricted setting sources (`tinyassets/providers/claude_provider.py:278-282, 346, 372`), plus no session persistence, in an empty cwd. Send only initialize and, if declared, the list request, then close stdin under a 30 s bound. Record redacted raw envelopes as the artifact.
- **Facts to prove before any adapter is registered:**
  1. Exact request and response shapes on CLI 2.1.261, and which field is the execution ID that `--model` accepts.
  2. Whether the list lives in the initialize response, a separate list request, or neither on this version.
  3. Unknown-request behaviour: error reply versus silence. Silence must hit the timeout and yield the fixed unavailable error, never a partial list.
  4. Unsupported must map to `None` (unknown), not an empty catalogue. An empty list renders as "no models", which would be a false claim.
  5. No assistant or result message appears (no inference), and what files the process leaves in the config dir and cwd.
  6. Clean exit on stdin close on Windows and Linux. Production is Linux, and whether the Claude binary is even in the image is unknown; if absent, `executor_unavailable` already fails closed (`tinyassets/providers/served_model_plan.py:182-185`).
- **DISAGREE_CONCERN, per-turn spawn on discovered scope.** Every served turn re-enumerates (`tinyassets/providers/model_selection.py:149-157`). Exposing the discovered toggle to all users on the current host means one bounded subprocess per chat turn. Ship the toggle to the founder first and measure, then cache within the existing five-minute window before general use.
- **Codex adapter status.** The registration is complete (`tinyassets/providers/codex_provider.py:697-704`). No owned-account run exists in evidence, so the list keys remain unproven live.

### Item 3: honest unavailable and unknown UX

- **DISAGREE_CONCERN, silent None on Claude discovered scope.** When enumeration returns unknown, the plan records no reason (`served_model_plan.py:305-317`, only the error branch appends one). The picker would show a bare default row, indistinguishable from an explicit default. Minimal patch: append a source-scoped `native_enumeration_unsupported` reason when the result is `None`. Reason strings are unvalidated (`tinyassets/providers/model_policy.py:158-163`) and the app renders any reason generically, so no UI change is needed for the label.
- **Minimal server patch for capability.** Add an `enumeration` field to each subscription source entry (`tinyassets/api/model_options.py:159-161`), derived from whether the installed executor has a metadata adapter. That is a fact about the installation, not the account, and it is what lets the app hide the discovered consent honestly instead of promising every future CLI can list.
- **AGREE, freshness and pricing are cosmetic today.** Declared rows carry fresh, unmetered pricing (`served_model_plan.py:166-169`) but the document already carries `availability_basis` per row (`tinyassets/providers/model_options.py:56`), and the app labels declared rows as unverified (`app.html:2132`). Do not change the freshness value; the app's usability check keys on it (`app.html:2214`). Document that native freshness attests custody, not availability.
- **Setup links exist already.** Both connect flows are in the app (`app.html:2864` for Codex, `app.html:3135` for Claude). The "connect first" note (`app.html:2154`) should link to them. Claude also stays under the host serving hold with its own reason (`provider_serving_binding.py:397-411`); render that as policy, not as "no models".

### Blockers versus hardening

**Before build:** none for the declared-ID and capability-field patches. They touch no authority path. The Claude adapter is blocked on the probe facts above.

**Post-live hardening:** cache the discovered snapshot across turns; verify one live turn with a deliberately wrong declared ID fails loudly and advances the fallback order rather than silently answering as the default; record the executor-reported model from the stream as the answering identity, distinct from the requested ID.

**Verification plan:** unit tests for the new reason and the capability field against the unfixed tree first, so they go red; one rendered owner session declaring a real Codex ID and seeing it answer; the Codex discovered path on the owner account once, with the receipt showing `executor_enumerated`.

**Limitations.** No PLAN sections were read. The app was read as source, not exercised. No CLI, provider, or network call was made. Claude control-protocol behaviour on 2.1.261 is inferred from the research doc, not observed. No live native-account catalogue completeness is proven for either provider, and the six smoke passes say nothing about model choice.

VERDICT: ADAPT
