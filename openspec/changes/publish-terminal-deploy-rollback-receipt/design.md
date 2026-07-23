## Context

`deploy-prod.yml` resolves an immutable target, captures a previous configured
image, mutates production, verifies the forward release, and publishes
`/data/release-state.json` only on success. Its later rollback step runs under
`failure()` but exposes no structured result. The final issue step therefore
cannot tell whether rollback was unavailable, skipped, green, or red, and a
successful rollback leaves the forward-deploy receipt on disk.

The receipt is consumed as active-release truth by `get_status` and its
`rollback_target` is the only allowed immutable repair target for image-pull
recovery. It is therefore unsafe to classify the active release from
`/etc/tinyassets/env` alone: that file can say one digest while the daemon
container still runs another. It is also unsafe to use `github.sha` as image
source provenance for `workflow_dispatch`; that SHA identifies the workflow
definition checkout, not necessarily a manually selected old image.

Legacy top-level fields must remain present and acquire exact semantics. A
field whose provenance cannot be proven is empty; compatibility does not permit
inventing a value.

## Goals / Non-Goals

**Goals:**

- Publish one truthful terminal receipt after every deploy path that began the
  `TINYASSETS_IMAGE` mutation.
- Require configured/running immutable-image agreement before classifying
  `deployed` or `rolled_back`.
- Keep legacy release-state fields as explicitly defined projections of the
  active release and current terminal workflow.
- Record attempted release, observations, provenance, and rollback state
  separately with bounded enums.
- Never infer image source SHA from a manual tag or from `github.sha` alone.
- Preserve the workflow's red conclusion after a failed forward deploy,
  rollback, or terminal writer.
- Make failure issue language mechanically conditional on bounded outputs.
- Keep receipt classification pure, deterministic, and matrix-testable.

**Non-Goals:**

- Change image admission, deploy concurrency, rollback eligibility, or the
  canonical canary itself.
- Claim that a pre-mutation failure changed production.
- Make receipt publication itself a successful recovery.
- Modify public MCP response fields in this change.
- Prove the workflow has executed on the production host.

## Decisions

### 1. Use exact immutable identities and two independent observations

A valid immutable image reference is exactly a canonical
`repository@sha256:<64 lowercase hex>` string. Validation uses:

```text
^[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]+)?(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+@sha256:[0-9a-f]{64}$
```

No tag, uppercase character, whitespace, digest prefix, bare image ID, or
multiple-repository ambiguity is accepted.

The workflow obtains two terminal observations:

1. `configured_image_ref`: the canonical immutable value actually read from
   `TINYASSETS_IMAGE` in `/etc/tinyassets/env`.
2. `running_image_ref`: the canonical RepoDigest derived from the actual daemon
   container's Docker image ID. The workflow inspects the daemon container,
   resolves that content ID to RepoDigests, filters to the admitted repository,
   and accepts exactly one canonical value.

The classifier records both observations and sets `active_identity_status` to
one of:

- `agreed`: both are valid and byte-for-byte equal;
- `mismatch`: both are valid and unequal;
- `configured_unknown`: configured identity is invalid/missing and running is
  valid;
- `running_unknown`: configured identity is valid and running is
  invalid/missing/ambiguous;
- `both_unknown`: neither observation is valid.

`active_image_ref`, `active_image_digest`, legacy `image_ref`, and legacy
`image_digest` are populated only for `agreed`; otherwise they are empty.
`active_image_digest` and legacy `image_digest` preserve the existing receipt
shape by containing the full canonical RepoDigest, not a bare digest.

Forward admission includes this observation. A forward canary cannot produce
`deployed` if configured and running identity do not agree with the immutable
attempted ref. Rollback completion re-observes both sources and cannot produce
`rolled_back` unless they agree with the captured immutable previous ref.

Alternative: trust the env file or the container's configured image string.
Rejected because neither proves the bytes the daemon container is running.

### 2. Capture prior truth with a fixed decoded bound

Before mutation, the workflow captures the prior receipt as strict base64. The
decoded payload limit is exactly **65,536 bytes**, measured before UTF-8 or JSON
parsing. Empty input means absent. Invalid base64, decoded byte 65,537 or later,
invalid UTF-8, non-object JSON, unsupported field types, or invalid identity
fields makes the entire prior receipt unusable for provenance and ancestry.
Unknown fields are ignored rather than copied.

The pre-mutation previous image is rollback-eligible only when the configured
and actual running daemon observations both validate and agree. A mutable
configured tag is not converted into proof after the fact. The captured prior
receipt may contribute source provenance and ancestry only when its canonical
active identity exactly equals that agreed previous ref.

For a version-1 receipt, the prior active identity is its canonical `image_ref`
(and `image_digest`, when present, must equal it). For version 2 it is
`active_image_ref` (and its active/legacy identity fields, when non-empty, must
agree). A prior `rollback_target` is reusable only when it is canonical, differs
from the failed attempted ref, and the prior receipt matches the restored
active ref.

Alternative: infer prior source SHA from registry tags. Rejected because tags
are mutable and do not bind source to bytes.

### 3. Bind source provenance to the digest

The classifier accepts a Git SHA only from evidence bound to the exact
immutable image digest:

- the admitted repository's `org.opencontainers.image.revision` label read by
  inspecting that immutable digest, validated as a full 40-lowercase-hex SHA;
  or
- a validated prior receipt whose active image exactly matches the observed
  active ref.

For a `workflow_run`, build run fields are retained only when the digest-bound
revision also equals the triggering run's full `head_sha`. For
`workflow_dispatch`, the digest-bound revision may identify source, but
`github.sha`, the tag text, and a SHA-shaped tag are never evidence. If the
label is missing, malformed, or disagrees with event metadata,
`attempted_git_sha` is empty. This is the required behavior for a manually
selected arbitrary old tag.

The bounded provenance enums are:

- `attempted_source_provenance`:
  `digest_revision_label|unknown`;
- `active_source_provenance`:
  `attempted_digest|prior_receipt|unknown`.

Alternative: use `${{ github.event.workflow_run.head_sha || github.sha }}`.
Rejected because its manual-dispatch branch lies about old image source.

### 4. Mark mutation and make rollback outputs survive failure

The deploy step writes `mutation_started=true` to `GITHUB_OUTPUT` immediately
before invoking the atomic helper that changes `TINYASSETS_IMAGE`. The output
therefore survives a helper failure. Pre-mutation failures leave the durable
receipt untouched.

Rollback handling runs after the forward stages with `if: always()`. It writes
safe defaults before any fallible command, updates outputs as work occurs, then
returns nonzero after all final outputs are present when rollback is not proven.
The bounded outputs are:

- `rollback_attempted`: JSON-style `true|false`;
- `rollback_result`: `succeeded|failed|not_attempted`;
- `rollback_canary_status`: `passed|failed|not_run`;
- `rollback_reason`:
  `attempted|not_needed|pre_mutation_failure|no_valid_target`.

The only success tuple is
`true/succeeded/passed/attempted`, and it additionally requires terminal
configured/running agreement with the previous ref. A passed canary with image
mismatch is still a failed rollback classification. A rollback command failure
before the canary produces `true/failed/not_run/attempted`; a red canary
produces `true/failed/failed/attempted`.

### 5. Use a small pure classifier/builder

Receipt validation, outcome classification, legacy projection, and safe
`rollback_target` selection live in one small standard-library Python
executable (planned as `scripts/deploy_terminal_receipt.py`). Its core function
accepts a JSON observation object and returns a receipt object without reading
environment variables, Docker, SSH, GitHub, clocks, or the filesystem. The CLI
only decodes/validates its explicit inputs and prints canonical JSON. The
workflow supplies `terminal_at` explicitly.

This isolates the truth table from YAML/shell and permits direct table-driven
tests. Shell remains responsible for observing host state, performing mutation,
transporting the generated file, and atomically installing it.

Alternative: keep a large inline Python heredoc in YAML. Rejected because it
would make the outcome matrix difficult to invoke directly and easy for
structural tests to miss.

### 6. Classify terminal outcome conservatively

The bounded receipt fields are:

- `release_state_version`: integer `2`;
- `outcome`:
  `deployed|rolled_back|rollback_failed|failed_without_rollback`;
- `forward_deploy_status`: `succeeded|failed`;
- `forward_canary_status`: `passed|failed|not_run`;
- the identity and provenance enums above;
- `attempted_git_sha`, `attempted_image_tag`, `attempted_image_ref`,
  `attempted_image_digest`;
- `configured_image_ref`, `running_image_ref`, `active_image_ref`,
  `active_image_digest`, `active_git_sha`;
- the four rollback fields above; and
- `terminal_at`.

`attempted_image_ref` is the admitted canonical target and
`attempted_image_digest` is the same full RepoDigest for compatibility with the
existing digest representation.

Outcome classification is exact:

| Outcome | Required conditions |
|---|---|
| `deployed` | mutation started; every forward admission check and forward canary passed; rollback was not needed; configured and running refs agree exactly with attempted ref |
| `rolled_back` | mutation started; forward path failed; rollback tuple is `true/succeeded/passed/attempted`; configured and running refs agree exactly with captured previous ref |
| `rollback_failed` | mutation started and rollback was attempted, but command, canary, or terminal identity agreement with the previous ref is not proven |
| `failed_without_rollback` | mutation started, `deployed` is not proven, and rollback was not attempted |

Receipt publication failure does not rewrite this observed-host outcome. For
example, a healthy agreed forward release may classify `deployed` while the
step output reports that saving the receipt failed; the job and issue remain
red because durable terminal truth was not published.

### 7. Define every legacy field

All version-2 receipts contain every legacy key. Empty string means unknown or
unproven; it is preferable to false attribution.

| Legacy field | Exact version-2 meaning |
|---|---|
| `git_sha` | proven Git SHA for the agreed active image; attempted digest provenance for the attempted image, matching prior receipt provenance for the restored prior image, otherwise empty |
| `image_tag` | mutable display ref known to have resolved to the agreed active digest in its source receipt/run; otherwise empty |
| `image_ref` | agreed canonical active RepoDigest; otherwise empty |
| `image_digest` | same agreed canonical active RepoDigest (the legacy field historically stores the full RepoDigest); otherwise empty |
| `build_run_id`, `build_run_url` | build run proven to have produced the active digest; current triggering run only when digest-bound revision equals `head_sha`, matching prior values for a restored prior release, otherwise empty |
| `deploy_run_id`, `deploy_run_url` | current deploy workflow run that published this terminal receipt, for every version-2 receipt |
| `config_hash` | terminal SHA-256 hash of the readable live `/etc/tinyassets/env`, prefixed `sha256:`; otherwise empty |
| `config_version` | `tinyassets-env-v1` when `config_hash` is present; otherwise empty |
| `schema_migration_rev` | `not_applicable` until a real observed migration revision exists; it never carries image provenance |
| `canary_bundle_status` | canary applicable to the agreed active identity: `passed`, `failed`, or `not_run`; never `passed` for an identity mismatch |
| `deployed_at` | `terminal_at` for `deployed` or `rolled_back`; for a failed outcome whose active image matches a valid prior receipt, its validated prior `deployed_at`; otherwise empty |
| `rollback_target` | canonical future repair target selected only by the matrix below; otherwise empty |
| `actor` | actor of the current terminal deploy workflow |
| `repository` | repository of the current terminal deploy workflow |
| `workflow_event` | event name of the current terminal deploy workflow |

The complete `rollback_target` matrix is:

| Outcome | Agreed active identity | `rollback_target` |
|---|---|---|
| `deployed` | attempted ref | pre-mutation previous ref, only when pre-mutation configured/running observations agreed canonically; else empty |
| `rolled_back` | previous ref | prior receipt's canonical `rollback_target`, only when that receipt validates and matches the restored ref; else empty |
| `rollback_failed` | attempted ref | captured canonical previous ref; else empty |
| `rollback_failed` | previous ref | validated matching prior receipt's canonical `rollback_target`; else empty |
| `rollback_failed` | another ref or no agreement | empty |
| `failed_without_rollback` | attempted ref | captured canonical previous ref; else empty |
| `failed_without_rollback` | previous ref | validated matching prior receipt's canonical `rollback_target`; else empty |
| `failed_without_rollback` | another ref or no agreement | empty |

The target must always pass the canonical-ref validator and must never equal the
failed attempted image. Thus a failed attempted image cannot become the next
image-pull repair target, while a failure that left the attempted image running
can still point safely to the independently observed previous image.

### 8. Publish terminal receipt status before failure

One step after rollback uses `if: always()`. Its first action emits a safe
`terminal_receipt_result` default:

- `not_applicable` when `mutation_started` is not `true`; it does not contact
  the host or replace the prior receipt;
- `failed` when mutation started, before any observation, classification,
  transfer, or install command;
- `published` only after the validated receipt is atomically installed with the
  existing numeric `1001:1001`, mode `0644` contract.

The output enum is exactly `published|failed|not_applicable`. Because `failed`
is emitted before fallible work, a shell/SSH/classifier/writer failure leaves a
visible output before the step returns nonzero. The step does not use
`continue-on-error`; writer failure keeps the job red and leaves the last
atomic receipt intact.

### 9. Derive complete issue wording from outputs

The `deploy-failed` issue step uses `if: always() && failure()` and treats empty,
unknown, or contradictory values as unproven. Its rollback sentence is selected
from this complete matrix:

| Outputs/condition | Required issue wording |
|---|---|
| mutation not started; reason `pre_mutation_failure` | "Production mutation did not start; rollback was not attempted." |
| mutation started; reason `not_needed`; forward checks passed | "Rollback was not needed because the forward deployment was proven healthy." |
| mutation started; reason `no_valid_target` | "Rollback was not attempted because no validated immutable previous image was available." |
| `true/succeeded/passed/attempted` plus terminal agreement with previous ref | "Rollback succeeded and the rollback canary passed." |
| attempted; canary `failed` | "Rollback failed; the rollback canary failed." |
| attempted; canary `not_run` | "Rollback failed before the rollback canary ran." |
| attempted; canary passed but active identity is not agreed with previous ref | "Rollback was not proven: the canary passed but configured and running image identity did not agree with the rollback target." |
| any missing, invalid, or contradictory rollback tuple | "Rollback status is unavailable; rollback success was not proven." |

It then appends exactly one receipt sentence:

| `terminal_receipt_result` | Required issue wording |
|---|---|
| `published` | "Terminal release-state receipt published." |
| `failed` | "Terminal release-state publication failed; durable active-release truth is not proven and the prior receipt may be stale." |
| `not_applicable` with no mutation | "Terminal release-state publication was not applicable; the prior receipt was left unchanged." |
| `not_applicable` after mutation, empty, or any other value | "Terminal release-state status is unavailable or inconsistent; durable active-release truth is not proven." |

For active identity, `agreed` prints the canonical active ref; `mismatch` prints
both configured and running refs and explicitly says they disagree; an unknown
state names which observation was unavailable. No branch substitutes an empty
previous image into "rolled back to", and no branch turns missing outputs into
success.

## Risks / Trade-offs

- **[Terminal writer cannot reach the host]** -> the default `failed` output is
  already visible, the workflow remains red, the issue says durable truth is
  unproven, and the last atomic receipt is not overwritten.
- **[Prior receipt is stale, malformed, or oversized]** -> reject the entire
  receipt for provenance/ancestry, retain independently observed identities,
  and leave unverifiable legacy fields/rollback ancestry empty.
- **[Env and running container diverge]** -> record both observations, classify
  mismatch, forbid `deployed`/`rolled_back`, and keep unsafe identity fields
  empty.
- **[Rollback output is lost by shell exit]** -> write defaults first and all
  final outputs before the final nonzero return.
- **[Pure helper grows into an orchestration layer]** -> keep it standard-library,
  side-effect-free at its core, with no Docker/SSH/GitHub/filesystem access.
- **[Structural tests miss GitHub runtime behavior]** -> require actionlint,
  failed-step output tests, and a deliberately failed production-safe live
  exercise before claiming operational verification.

## Migration Plan

1. Land the pure classifier/builder and matrix tests, then wire workflow
   observations and outputs to it.
2. On the next successful deploy, verify a version-2 `outcome=deployed`
   receipt, dual-observation agreement, and unchanged public legacy projection.
3. Exercise an isolated post-mutation failure with a known prior immutable
   image and verify rollback, terminal receipt, issue wording, red workflow
   conclusion, and safe next rollback target.
4. Exercise or simulate terminal writer failure and confirm
   `terminal_receipt_result=failed` remains visible to the issue step.
5. If terminal publication causes a regression, revert the workflow; the last
   atomic receipt remains intact.

## Open Questions

None. Extending `get_status.release_state` to promote every version-2 field from
`extra` and teaching release reconciliation to consume the new outcome are
separate follow-up changes.
