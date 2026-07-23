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
entirety for provenance and rollback ancestry when its decoded payload exceeds
exactly 65,536 bytes, is invalid base64 or UTF-8, is not a JSON object, contains
unsupported types in a consumed field, or contains inconsistent/invalid active
identity fields. Prior provenance and ancestry MUST be reused only when the
receipt's canonical active image exactly matches the agreed observed previous
image. A prior `rollback_target` MUST additionally be canonical and differ from
the failed attempted ref.

Image source SHA SHALL come only from a full 40-lowercase-hex
`org.opencontainers.image.revision` label inspected from the exact immutable
digest, or from a validated prior receipt matching the exact active digest.
For a `workflow_run`, current build-run provenance SHALL be populated only when
that digest-bound revision equals the triggering run's full `head_sha`. A
manual dispatch MUST NOT derive source SHA from `github.sha`, tag text, or a
SHA-shaped tag; when digest-bound provenance is unavailable or inconsistent,
the source SHA and build provenance fields SHALL be empty.

The deploy step SHALL emit `mutation_started=true` immediately before invoking
the first `TINYASSETS_IMAGE` mutation. Rollback handling SHALL run after the
forward stages with an always condition, emit safe outputs before fallible
commands, and emit final outputs before returning failure. Its bounded outputs
are `rollback_attempted=true|false`,
`rollback_result=succeeded|failed|not_attempted`,
`rollback_canary_status=passed|failed|not_run`, and
`rollback_reason=attempted|not_needed|pre_mutation_failure|no_valid_target`.
The only successful rollback tuple is
`true/succeeded/passed/attempted`, and `rolled_back` additionally requires
terminal configured/running agreement with the captured previous ref.

Every path that begins mutation SHALL reach a post-rollback terminal step that
attempts to invoke a small pure executable receipt-classifier/builder. Its
classification core
MUST accept explicit JSON observations and return deterministic JSON without
reading environment variables, Docker, SSH, GitHub, clocks, or the filesystem.
It SHALL validate and atomically publish version-2
`/data/release-state.json`, while a pre-mutation path SHALL leave the prior
receipt unchanged. The terminal step SHALL use `if: always()` and emit
`terminal_receipt_result=failed` before any fallible post-mutation work,
overwrite it with `published` only after atomic installation, or emit
`not_applicable` without host mutation when mutation did not start. The output
enum is exactly `published|failed|not_applicable`; writer failure SHALL remain
red and MUST NOT destroy the last atomic receipt.

The version-2 receipt SHALL use exactly these bounded classifications:

- `release_state_version`: integer `2`;
- `outcome`:
  `deployed|rolled_back|rollback_failed|failed_without_rollback`;
- `forward_deploy_status`: `succeeded|failed`;
- `forward_canary_status`: `passed|failed|not_run`;
- `attempted_source_provenance`: `digest_revision_label|unknown`;
- `active_source_provenance`:
  `attempted_digest|prior_receipt|unknown`;
- `active_identity_status` as defined above;
- rollback fields and enums as defined above.

`deployed` SHALL require mutation, all forward admission checks and forward
canary green, rollback reason `not_needed`, and configured/running agreement
with the attempted ref. `rolled_back` SHALL require mutation, a failed forward
path, the successful rollback tuple, and configured/running agreement with the
captured previous ref. Any attempted rollback lacking command, canary, or
terminal identity proof SHALL be `rollback_failed`. Any mutated path that is
not `deployed` and did not attempt rollback SHALL be
`failed_without_rollback`. Receipt publication failure SHALL NOT change this
observed-host outcome; it separately keeps the workflow red through
`terminal_receipt_result=failed`.

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
| `git_sha` | proven SHA of the agreed active image from attempted digest provenance or a validated matching prior receipt; otherwise empty |
| `image_tag` | mutable display ref proven to have resolved to the agreed active digest in its source run/receipt; otherwise empty |
| `image_ref` | agreed canonical active RepoDigest; otherwise empty |
| `image_digest` | same agreed canonical active RepoDigest; otherwise empty |
| `build_run_id`, `build_run_url` | build run proven to have produced the active digest; matching current trigger or validated matching prior values; otherwise empty |
| `deploy_run_id`, `deploy_run_url` | current terminal deploy workflow run |
| `config_hash` | terminal hash of readable live env as `sha256:<64 lowercase hex>`; otherwise empty |
| `config_version` | `tinyassets-env-v1` when `config_hash` is present; otherwise empty |
| `schema_migration_rev` | `not_applicable` until a real observed revision exists |
| `canary_bundle_status` | `passed`, `failed`, or `not_run` for the canary applicable to the agreed active identity; never `passed` on identity mismatch |
| `deployed_at` | `terminal_at` for `deployed`/`rolled_back`; validated prior value for a failed outcome still matching prior active; otherwise empty |
| `rollback_target` | canonical future repair target selected only by the matrix below; otherwise empty |
| `actor` | actor of the current terminal deploy workflow |
| `repository` | repository of the current terminal deploy workflow |
| `workflow_event` | event name of the current terminal deploy workflow |

`rollback_target` SHALL follow the complete matrix:

| Outcome | Agreed active identity | Required value |
|---|---|---|
| `deployed` | attempted ref | independently agreed canonical pre-mutation previous ref; else empty |
| `rolled_back` | previous ref | canonical prior-receipt target only when the receipt validates and matches restored ref; else empty |
| `rollback_failed` | attempted ref | captured canonical previous ref; else empty |
| `rollback_failed` | previous ref | canonical target from validated matching prior receipt; else empty |
| `rollback_failed` | another ref or no agreement | empty |
| `failed_without_rollback` | attempted ref | captured canonical previous ref; else empty |
| `failed_without_rollback` | previous ref | canonical target from validated matching prior receipt; else empty |
| `failed_without_rollback` | another ref or no agreement | empty |

A failed attempted image MUST NOT become a future `rollback_target`.

Deploy failure SHALL remain red and open a distinct `deploy-failed` issue with
rollback wording selected exactly as follows:

| Condition | Required wording |
|---|---|
| no mutation; `pre_mutation_failure` | "Production mutation did not start; rollback was not attempted." |
| mutation; `not_needed`; forward checks green | "Rollback was not needed because the forward deployment was proven healthy." |
| mutation; `no_valid_target` | "Rollback was not attempted because no validated immutable previous image was available." |
| successful rollback tuple and terminal agreement with previous ref | "Rollback succeeded and the rollback canary passed." |
| attempted; canary failed | "Rollback failed; the rollback canary failed." |
| attempted; canary not run | "Rollback failed before the rollback canary ran." |
| attempted; canary passed; terminal identity not agreed with previous ref | "Rollback was not proven: the canary passed but configured and running image identity did not agree with the rollback target." |
| missing, invalid, or contradictory rollback outputs | "Rollback status is unavailable; rollback success was not proven." |

The issue SHALL append exactly one terminal receipt sentence:

| `terminal_receipt_result` | Required wording |
|---|---|
| `published` | "Terminal release-state receipt published." |
| `failed` | "Terminal release-state publication failed; durable active-release truth is not proven and the prior receipt may be stale." |
| `not_applicable` with no mutation | "Terminal release-state publication was not applicable; the prior receipt was left unchanged." |
| `not_applicable` after mutation, empty, or other | "Terminal release-state status is unavailable or inconsistent; durable active-release truth is not proven." |

The issue SHALL show the canonical active ref only for `agreed`, show both refs
and state that they disagree for `mismatch`, identify the unavailable
observation for unknown identity states, and MUST NOT convert empty outputs into
a success claim.

#### Scenario: Mutable or missing target is rejected before production mutation

- **WHEN** the requested build tag cannot be resolved to a canonical immutable ref
- **THEN** the deploy fails before changing `TINYASSETS_IMAGE` or restarting production
- **AND** it leaves the active release receipt unchanged
- **AND** terminal receipt result is `not_applicable`

#### Scenario: Successful deploy publishes agreed active and attempted identity

- **WHEN** the immutable target is configured and running, env readability passes, and the canonical canary plus handle assertion pass
- **THEN** the workflow atomically writes an owned, readable version-2 receipt with `outcome=deployed`
- **AND** configured, running, attempted, active, and legacy image identity agree with the target
- **AND** terminal receipt result is `published`

#### Scenario: Manual old tag does not inherit workflow source

- **WHEN** `workflow_dispatch` selects an arbitrary old tag whose immutable image has no valid digest-bound revision
- **THEN** the receipt leaves attempted and active Git SHA and build-run provenance empty
- **AND** it does not use `github.sha`, tag text, or a SHA-shaped tag as source provenance

#### Scenario: Failed admitted deploy rolls back and proves recovery

- **WHEN** mutation began, the forward path fails, a canonical agreed previous image was captured, rollback commands succeed, and the rollback canary passes
- **THEN** the workflow re-observes the configured and actual running daemon images
- **AND** it publishes `outcome=rolled_back` only when both equal the previous ref
- **AND** legacy active fields describe the restored release
- **AND** the failed attempted image is not the next rollback target

#### Scenario: Canary green without rollback identity agreement is not recovery

- **WHEN** the rollback canary passes but configured and running identities disagree or do not equal the previous ref
- **THEN** the workflow remains red and classifies `outcome=rollback_failed`
- **AND** the issue states that rollback was not proven

#### Scenario: Failed rollback remains red and explicit

- **WHEN** mutation began and rollback command or rollback canary fails
- **THEN** the workflow emits final rollback outputs before returning nonzero
- **AND** it attempts to publish `outcome=rollback_failed`
- **AND** the issue says rollback failed rather than saying production was rolled back

#### Scenario: Mutation without rollback target is not reported as recovery

- **WHEN** mutation began, the forward path fails, and no agreed canonical previous image is available
- **THEN** the workflow publishes `outcome=failed_without_rollback` with `rollback_result=not_attempted` and `rollback_reason=no_valid_target`
- **AND** the issue says rollback was not attempted

#### Scenario: Malformed oversized or mismatched prior receipt is untrusted

- **WHEN** the prior receipt is malformed, decodes beyond 65,536 bytes, or does not match the agreed previous ref
- **THEN** the classifier does not reuse any of its source provenance or rollback ancestry
- **AND** independently observed terminal identities and outcome remain reportable

#### Scenario: Configured and running image mismatch remains explicit

- **WHEN** terminal configured and actual-running image refs are valid but unequal
- **THEN** active and legacy identity/provenance fields remain empty
- **AND** the receipt records `active_identity_status=mismatch` and both observations
- **AND** neither `deployed` nor `rolled_back` is allowed

#### Scenario: Terminal writer failure remains visible and red

- **WHEN** mutation began but host observation, classification, transfer, or atomic receipt installation fails
- **THEN** `terminal_receipt_result=failed` is visible to later steps
- **AND** the workflow remains failed, the last atomic receipt remains intact, and the issue says durable terminal truth is not proven

#### Scenario: Pre-mutation failure leaves receipt untouched

- **WHEN** any step fails before the mutation marker
- **THEN** always-running rollback and terminal steps emit `pre_mutation_failure` and `not_applicable`
- **AND** neither step mutates production or the prior receipt

#### Scenario: Pure classifier matrix is directly executable

- **WHEN** the receipt classifier is invoked with fixture observations for forward success, rollback variants, identity mismatch, prior-receipt rejection, or manual provenance
- **THEN** it returns deterministic outcomes, legacy projections, and safe rollback targets without host or workflow side effects
