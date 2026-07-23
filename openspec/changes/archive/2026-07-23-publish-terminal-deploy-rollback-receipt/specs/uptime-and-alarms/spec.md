## MODIFIED Requirements

### Requirement: Digest-Pinned Deploy Admission Rollback And Receipt

The production deploy workflow SHALL resolve the requested image to an
immutable digest before mutating production, capture a previous rollback image
only from agreeing configured and actual-running daemon identities, and capture
the bounded prior active-release receipt before mutation. It SHALL verify
`/etc/tinyassets/env` remains readable by the daemon user after restart and
require the canonical MCP canary and advertised-handle assertion to pass.

An immutable image identity MUST match exactly a canonical
`repository@sha256:<64 lowercase hex>` value under
`^[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]+)?(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+@sha256:[0-9a-f]{64}$`.
The workflow SHALL independently observe the canonical configured ref from
`TINYASSETS_IMAGE` and the canonical RepoDigest derived from the actual daemon
container's Docker image ID. It SHALL record `active_identity_status` as exactly
`agreed`, `mismatch`, `configured_unknown`, `running_unknown`, or
`both_unknown`. Only two valid, byte-for-byte equal observations are `agreed`;
no tag, bare image ID, digest prefix, or ambiguous RepoDigest set is agreement.

The captured prior receipt SHALL use strict base64 and SHALL be rejected in its
entirety when its decoded payload exceeds exactly 65,536 bytes, is invalid
base64 or UTF-8, is not a JSON object, contains unsupported types in a consumed
field, or contains inconsistent/invalid active identity fields. A structurally
valid version-1 receipt MAY only corroborate identity after configured and
actual-running observations already agree with its canonical `image_ref`; no
version-1 field may seed Git/build provenance, `image_tag`, `deployed_at`, or a
future `rollback_target`.

Prior provenance or ancestry MUST be reused only from a version-2
**terminal-proof** receipt whose `release_state_version=2`,
`outcome=deployed|rolled_back`, `active_identity_status=agreed`,
configured/running/active/legacy canonical refs all agree,
`canary_bundle_status=passed`, and active ref exactly matches the newly observed
agreed ref. Each reused field MUST pass its own type/format validation. A reused
`rollback_target` MUST additionally be canonical and differ from the failed
attempted ref. The bounded prior-match enum SHALL be
`absent|invalid|mismatch|v1_identity_match|v2_terminal_proof_match`.

Image source SHA SHALL come only from a full 40-lowercase-hex
`org.opencontainers.image.revision` label inspected from the exact immutable
digest, or from a matching version-2 terminal-proof receipt.
For a `workflow_run`, current build-run provenance SHALL be populated only when
that digest-bound revision equals the triggering run's full `head_sha`. A
manual dispatch MUST NOT derive source SHA from `github.sha`, tag text, or a
SHA-shaped tag; when digest-bound provenance is unavailable or inconsistent,
the source SHA and build provenance fields SHALL be empty. An active image
matching only a version-1 receipt SHALL derive provenance afresh from its
digest-bound revision label or remain unknown.

The workflow SHALL emit `production_mutation_started=true` immediately before
its first state-changing command directed at the production host and
`image_mutation_started=true` immediately before its first
`TINYASSETS_IMAGE` write. In the current workflow the first marker is
immediately before the `Scrub stale cloud env overrides` SSH command. The
checkout action and the `Resolve image tag`, `Verify secrets present`, `Install
SSH key`, and expanded read-only `Capture previous image tag (for rollback)`
steps are exactly the pre-host-write paths: both markers remain false, no host
mutation or terminal host publication occurs, terminal result is
`not_applicable`, and the prior receipt is unchanged.

Once the production marker is true, terminal publication SHALL be attempted
even if the immediately following remote command fails before a write can be
proven. Image rollback MUST be attempted only when the image marker is true.
Rollback handling SHALL run after the forward stages with `if: always()`, emit
safe outputs before fallible commands, and emit final outputs before its exact
exit. Its bounded outputs are `rollback_attempted=true|false`,
`rollback_result=succeeded|failed|not_attempted`,
`rollback_canary_status=passed|failed|not_run`, and
`rollback_reason=attempted|not_needed|pre_host_write_failure|image_mutation_not_started|no_valid_target`.

Rollback step exit SHALL follow this complete table:

| State and final tuple | Required exit |
|---|---|
| both markers false; `false/not_attempted/not_run/pre_host_write_failure` | zero |
| production marker true and image marker false; `false/not_attempted/not_run/image_mutation_not_started` | zero |
| fully green forward path; `false/not_attempted/not_run/not_needed` | zero |
| image marker true, failed forward path, no valid previous ref; `false/not_attempted/not_run/no_valid_target` | nonzero |
| image marker true; `true/succeeded/passed/attempted`; configured/running refs agree with previous ref | zero |
| image marker true and rollback command, canary, or required identity proof fails or is unavailable | nonzero |
| any missing, invalid, or contradictory marker/output tuple | nonzero |

`not_needed` is valid only for a fully green forward path. A passed rollback
canary with missing/mismatched image identity is an unproven required rollback
and MUST exit nonzero.

Every path whose production marker is true SHALL reach a post-rollback terminal
step that attempts to invoke a small pure executable receipt-classifier/builder. Its
classification core
MUST accept explicit JSON observations and return deterministic JSON without
reading environment variables, Docker, SSH, GitHub, clocks, or the filesystem.
It SHALL validate and atomically publish version-2
`/data/release-state.json`, while a pre-host-write path SHALL leave the prior
receipt unchanged. The terminal step SHALL use `if: always()` and emit
`terminal_receipt_result=failed` before any fallible post-production-mutation work,
overwrite it with `published` only after atomic installation, or emit
`not_applicable` without host contact when production mutation did not start.
The output enum is exactly `published|failed|not_applicable`; writer failure
SHALL remain red and MUST NOT destroy the last atomic receipt. Before attempting
atomic installation, the terminal step SHALL expose the classifier's bounded
`terminal_outcome`, `terminal_active_identity_status`, and
`terminal_canary_status` outputs for failure-issue wording.
`terminal_canary_status` SHALL be forward canary status for `deployed`,
rollback canary status for `rolled_back` or an attempted rollback, and forward
canary status for a non-rollback failure.

The version-2 receipt SHALL use exactly these bounded classifications:

- `release_state_version`: integer `2`;
- `outcome`:
  `deployed|rolled_back|rollback_failed|failed_without_rollback`;
- `forward_deploy_status`: `succeeded|failed`;
- `forward_canary_status`: `passed|failed|not_run`;
- `production_mutation_started` and `image_mutation_started`: booleans;
- `prior_receipt_match_status` as defined above;
- `attempted_source_provenance`: `digest_revision_label|unknown`;
- `active_source_provenance`:
  `attempted_digest|digest_revision_label|v2_terminal_proof|unknown`;
- `active_identity_status` as defined above;
- rollback fields and enums as defined above.

`deployed` SHALL require both markers true, all forward admission checks and
forward canary green, rollback reason `not_needed`, and configured/running
agreement with the attempted ref. `rolled_back` SHALL require both markers
true, a failed forward path, the successful rollback tuple, and
configured/running agreement with the captured previous ref. Any image-marked
path lacking required rollback command, canary, or terminal identity proof
SHALL be `rollback_failed`. Any production-marked path that is not `deployed`
and did not attempt image rollback SHALL be `failed_without_rollback`,
including failure before image mutation and unavailable rollback target.
Receipt publication failure SHALL NOT change this observed-host outcome; it
separately keeps the workflow red through `terminal_receipt_result=failed`.

All version-2 receipts SHALL contain
`attempted_git_sha`, `attempted_image_tag`, `attempted_image_ref`,
`attempted_image_digest`, `configured_image_ref`, `running_image_ref`,
`active_git_sha`, `active_image_ref`, `active_image_digest`, `terminal_at`, and
all legacy keys. Attempted/active `image_digest` fields SHALL preserve the
legacy representation as full canonical RepoDigests. Active/legacy identity
fields SHALL be empty unless configured and running observations agree.

Every legacy key SHALL have exactly this version-2 meaning:

| Legacy field | Required meaning |
|---|---|
| `git_sha` | proven SHA of the agreed active image from fresh digest-label provenance or a matching version-2 terminal-proof receipt; never copied from version 1; otherwise empty |
| `image_tag` | mutable display ref proven to have resolved to the agreed active digest in the current run or a matching version-2 terminal-proof receipt; never copied from version 1; otherwise empty |
| `image_ref` | agreed canonical active RepoDigest; otherwise empty |
| `image_digest` | same agreed canonical active RepoDigest; otherwise empty |
| `build_run_id`, `build_run_url` | build run proven to have produced the active digest; matching current trigger or version-2 terminal-proof prior values; never copied from version 1; otherwise empty |
| `deploy_run_id`, `deploy_run_url` | current terminal deploy workflow run |
| `config_hash` | terminal hash of readable live env as `sha256:<64 lowercase hex>`; otherwise empty |
| `config_version` | `tinyassets-env-v1` when `config_hash` is present; otherwise empty |
| `schema_migration_rev` | `not_applicable` until a real observed revision exists |
| `canary_bundle_status` | `passed`, `failed`, or `not_run` for the canary applicable to the agreed active identity; never `passed` on identity mismatch |
| `deployed_at` | `terminal_at` for `deployed`/`rolled_back`; validated version-2 terminal-proof prior value for a failed outcome still matching prior active; never copied from version 1; otherwise empty |
| `rollback_target` | canonical future repair target selected only by the matrix below; otherwise empty |
| `actor` | actor of the current terminal deploy workflow |
| `repository` | repository of the current terminal deploy workflow |
| `workflow_event` | event name of the current terminal deploy workflow |

`rollback_target` SHALL follow the complete matrix:

| Outcome | Agreed active identity | Required value |
|---|---|---|
| `deployed` | attempted ref | independently agreed canonical pre-image-mutation previous ref; else empty |
| `rolled_back` | previous ref | canonical prior target only from a version-2 terminal-proof receipt matching restored ref; else empty |
| `rollback_failed` | attempted ref | captured canonical previous ref; else empty |
| `rollback_failed` | previous ref | canonical target from matching version-2 terminal-proof prior receipt; else empty |
| `rollback_failed` | another ref or no agreement | empty |
| `failed_without_rollback` | attempted ref | captured canonical previous ref; else empty |
| `failed_without_rollback` | previous ref | canonical target from matching version-2 terminal-proof prior receipt; else empty |
| `failed_without_rollback` | another ref or no agreement | empty |

A failed attempted image MUST NOT become a future `rollback_target`.

Deploy failure SHALL remain red and open a distinct `deploy-failed` issue with
rollback wording selected exactly as follows:

| Condition | Required wording |
|---|---|
| production marker false; `pre_host_write_failure` | "Production host write did not start; image rollback was not attempted." |
| production marker true; image marker false; `image_mutation_not_started` | "Production mutation started, but image mutation did not; image rollback was not required." |
| `not_needed` plus terminal outcome `deployed`, terminal active identity `agreed`, and terminal applicable canary `passed` | "Rollback was not needed because terminal outcome is deployed, active image identity agrees, and the applicable canary passed." |
| `not_needed` without that complete terminal tuple | "Rollback was not attempted; forward production health is unproven." |
| image marker true; `no_valid_target` | "Rollback was not attempted because no validated immutable previous image was available." |
| successful rollback tuple plus terminal outcome `rolled_back` and terminal agreement with previous ref | "Rollback succeeded and the rollback canary passed." |
| attempted; canary failed | "Rollback failed; the rollback canary failed." |
| attempted; canary not run | "Rollback failed before the rollback canary ran." |
| attempted; canary passed; terminal identity not agreed with previous ref | "Rollback was not proven: the canary passed but configured and running image identity did not agree with the rollback target." |
| missing, invalid, or contradictory rollback outputs | "Rollback status is unavailable; rollback success was not proven." |

The issue SHALL append exactly one terminal receipt sentence:

| `terminal_receipt_result` | Required wording |
|---|---|
| `published` | "Terminal release-state receipt published." |
| `failed` | "Terminal release-state publication failed; durable active-release truth is not proven and the prior receipt may be stale." |
| `not_applicable` with production marker false | "Terminal release-state publication was not applicable; the prior receipt was left unchanged." |
| `not_applicable` after production marker, empty, or other | "Terminal release-state status is unavailable or inconsistent; durable active-release truth is not proven." |

The issue SHALL show the canonical active ref only for `agreed`, show both refs
and state that they disagree for `mismatch`, identify the unavailable
observation for unknown identity states, and MUST NOT convert empty outputs into
a success claim. It MUST NOT describe a `not_needed` path as proven healthy
without terminal `deployed` outcome, agreed active identity, and applicable
passed canary.

#### Scenario: Mutable or missing target is rejected before production host write

- **WHEN** the requested build tag cannot be resolved to a canonical immutable ref
- **THEN** the deploy fails before `production_mutation_started` and before any production-host write
- **AND** it leaves the active release receipt unchanged
- **AND** terminal receipt result is `not_applicable`

#### Scenario: Successful deploy publishes agreed active and attempted identity

- **WHEN** the immutable target is configured and running, env readability passes, and the canonical canary plus handle assertion pass
- **THEN** the workflow atomically writes an owned, readable version-2 receipt with `outcome=deployed`
- **AND** both production and image mutation markers are true
- **AND** configured, running, attempted, active, and legacy image identity agree with the target
- **AND** terminal receipt result is `published`

#### Scenario: Manual old tag does not inherit workflow source

- **WHEN** `workflow_dispatch` selects an arbitrary old tag whose immutable image has no valid digest-bound revision
- **THEN** the receipt leaves attempted and active Git SHA and build-run provenance empty
- **AND** it does not use `github.sha`, tag text, or a SHA-shaped tag as source provenance

#### Scenario: Failed image-mutating deploy rolls back and proves recovery

- **WHEN** image mutation began, the forward path fails, a canonical agreed previous image was captured, rollback commands succeed, and the rollback canary passes
- **THEN** the workflow re-observes the configured and actual running daemon images
- **AND** it publishes `outcome=rolled_back` only when both equal the previous ref
- **AND** legacy active fields describe the restored release
- **AND** the failed attempted image is not the next rollback target

#### Scenario: Canary green without rollback identity agreement is not recovery

- **WHEN** the rollback canary passes but configured and running identities disagree or do not equal the previous ref
- **THEN** the workflow remains red and classifies `outcome=rollback_failed`
- **AND** the issue states that rollback was not proven

#### Scenario: Failed required rollback remains red and explicit

- **WHEN** image mutation began and rollback command, rollback canary, or required terminal identity proof fails
- **THEN** the workflow emits final rollback outputs before returning nonzero
- **AND** it attempts to publish `outcome=rollback_failed`
- **AND** the issue says rollback failed rather than saying production was rolled back

#### Scenario: Image mutation without rollback target is not reported as recovery

- **WHEN** image mutation began, the forward path fails, and no agreed canonical previous image is available
- **THEN** the workflow publishes `outcome=failed_without_rollback` with `rollback_result=not_attempted` and `rollback_reason=no_valid_target`
- **AND** the issue says rollback was not attempted

#### Scenario: Malformed oversized or mismatched prior receipt is untrusted

- **WHEN** the prior receipt is malformed, decodes beyond 65,536 bytes, or does not match the agreed previous ref
- **THEN** the classifier does not reuse any of its source provenance or rollback ancestry
- **AND** independently observed terminal identities and outcome remain reportable

#### Scenario: Version one receipt corroborates identity only

- **WHEN** a structurally valid version-1 prior receipt matches dual observed current identity
- **THEN** the classifier records `prior_receipt_match_status=v1_identity_match`
- **AND** it does not copy version-1 Git SHA, image tag, build provenance, deployed time, or rollback target
- **AND** it derives source afresh from the active immutable digest label or leaves it unknown

#### Scenario: Version two terminal proof may seed ancestry

- **WHEN** a version-2 prior receipt satisfies every terminal-proof invariant and matches dual observed current identity
- **THEN** the classifier records `prior_receipt_match_status=v2_terminal_proof_match`
- **AND** only individually validated provenance and rollback ancestry fields may be reused

#### Scenario: Configured and running image mismatch remains explicit

- **WHEN** terminal configured and actual-running image refs are valid but unequal
- **THEN** active and legacy identity/provenance fields remain empty
- **AND** the receipt records `active_identity_status=mismatch` and both observations
- **AND** neither `deployed` nor `rolled_back` is allowed

#### Scenario: Production mutation before image mutation still publishes terminal truth

- **WHEN** production mutation began but a failure occurred before `image_mutation_started`
- **THEN** image rollback exits zero with `rollback_reason=image_mutation_not_started` and does not write `TINYASSETS_IMAGE`
- **AND** the terminal step attempts to publish `outcome=failed_without_rollback`

#### Scenario: Terminal writer failure remains visible and red

- **WHEN** production mutation began but host observation, classification, transfer, or atomic receipt installation fails
- **THEN** `terminal_receipt_result=failed` is visible to later steps
- **AND** the workflow remains failed, the last atomic receipt remains intact, and the issue says durable terminal truth is not proven

#### Scenario: Pre-host-write failure leaves receipt untouched

- **WHEN** any enumerated runner/read-only step fails before the production mutation marker
- **THEN** always-running rollback and terminal steps emit `pre_host_write_failure` and `not_applicable`
- **AND** neither step mutates production or the prior receipt

#### Scenario: Validly unnecessary rollback exits zero

- **WHEN** the path is pre-host-write, failed before image mutation, or fully forward-green with its corresponding valid non-required tuple
- **THEN** the rollback step exits zero after emitting final outputs

#### Scenario: Required unproven rollback exits nonzero

- **WHEN** image mutation began and rollback is unavailable, fails, has a red canary, or lacks required terminal identity proof
- **THEN** the rollback step emits its truthful final tuple and exits nonzero

#### Scenario: Not needed alone cannot prove forward health in the issue

- **WHEN** rollback reason is `not_needed` but terminal outcome is not `deployed`, terminal active identity is not `agreed`, or the applicable terminal canary is not `passed`
- **THEN** the deploy-failed issue says forward production health is unproven

#### Scenario: Pure classifier matrix is directly executable

- **WHEN** the receipt classifier is invoked with fixture observations for forward success, rollback variants, identity mismatch, prior-receipt rejection, or manual provenance
- **THEN** it returns deterministic outcomes, legacy projections, and safe rollback targets without host or workflow side effects
