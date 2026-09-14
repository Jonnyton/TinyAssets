## Contract map

Read [primitives.md](primitives.md) for the detailed component/toolset contract
and [research.md](research.md) for source evidence and implementation pickup.
This file owns project packaging and the first offline proof. The new documents
extend the behavioral target without claiming that the deterministic fixture
proves a model-backed harness or cross-device experience.

The 2026-09-14 refinement also inspected the existing governed component compiler:
its adapter pins, typed ports, capability/resource/provider requirements,
confinement and diagnostics are integration anchors, not a reason to add a
parallel registry. General packaged JSON Schema port validation remains proposed.

## Context and verified baseline

Repository inspection on 2026-09-13 found:

- `tinyassets/custom_agents.py` owns immutable public definitions and private
  bindings. It currently limits canonical agent JSON to 256 KiB and components
  to 64. These limits are not silently increased by this proposal.
- `tinyassets/api/custom_agents.py` exposes native import, staged foreign
  import, publication, export conversion, and binding operations.
- `tinyassets/agent_interchange.py` validates conversion reports and adapters,
  creates receipts, and separates staged imports from publication.
- `openspec/specs/universe-custom-agents/spec.md` already requires private-data
  exclusion, fingerprint validation, unknown-component preservation, and
  revision-guarded bindings.
- The archived `agent-interchange-pipeline` proposal describes native
  round-tripping and loss-aware adapters. It is historical context; current code
  and current specs take precedence.
- OpenSpec delivery audit reported zero claimed delivery WIP. The OpenSpec CLI
  was absent in the execution workspace; this change uses the repository
  skill's manual proposal layout.

The unproven step is carrying and executing a complete source project outside
the hosted app. This proposal does not equate a successful JSON round-trip with
that proof, and does not claim a comprehensive absence audit of every runtime.

## Goals and non-goals

Deliver one verifiable source-project export/import path using existing native
definitions and runtime authority boundaries. A user must be able to edit the
exported harness without patching the hosted service.

Arbitrary live-state migration, universal foreign-format execution, a package
marketplace, dependency resolution from the network, and a replacement agent
runtime are outside this first change. Each would obscure the portability proof.
The complete long-term harness may replace context assembly, compaction,
planning, delegation, and the agent loop; this slice demonstrates the boundary
with an ordinary deterministic composition.

## Decision 1: retain the native definition; add a project adapter

Treat the project as a versioned adapter representation of the existing native
definition, not a competing definition registry or new MCP handle. Preserve
the native definition and its existing content fingerprint exactly. Compute a
separate project digest over the declared project inventory.

Candidate filenames, to be finalized in shape review:

```text
example-harness/
  agent.json             # existing canonical portable definition
  project.json           # project representation version and entry points
  project.lock.json      # exact file inventory and dependency identities
  README.md
  LICENSE
  src/
  fixtures/
  evals/
```

The project descriptor names its representation version, native definition
path, user-named entry points, input/output schema paths, and runtime
requirements. A component may reference project files through the adapter's
documented namespaced extension. Do not add arbitrary fields to the native
envelope or bypass its validator.

Every inventory record has a normalized relative path, byte length, and
SHA-256 digest. The project digest covers a canonical JSON encoding of the
descriptor and sorted inventory; the lock file itself is excluded to avoid a
self-hash cycle. The representation specification must fix that encoding and
reject duplicate JSON keys. Dependency identities include exact versions or
content digests and provenance locators; a moving branch or version range alone
is insufficient. A digest proves integrity, not author trust or permission.

Keep large source assets outside the 256 KiB definition envelope. Before
implementation, specify bounded artifact count, individual size, expanded
total size, and supported file types using existing governed artifact limits.
This is a review decision, not permission for unbounded archive extraction.

## Decision 2: definition, installation, and run remain separate

| Object | Export behavior |
| --- | --- |
| Definition/project | Explicitly inventoried source, declared dependencies, schemas, intentional seed fixtures, license, and portable public lineage |
| Installation | Private model, resource, channel, and authority bindings; never copied into a definition export |
| Run | Events, conversation, learned memory, outputs, checkpoints, pending effects; absent from this export |

Export from an explicit project inventory, never by recursively copying a
universe or working directory. A seed file must be intentionally declared as
shareable source. Do not relabel learned memory as a seed automatically.
Potential secret-bearing source must produce an actionable refusal or private
staging result before publication. Detection is defense in depth; it cannot
prove that arbitrary source contains no secret. Keep existing sensitive-field
validation and never include rejected values in diagnostics or receipts.

Public lineage declarations travel; local verification remains local. A missing
parent in the destination commons must not fabricate verified attribution or
prevent preservation of its portable declaration.

## Decision 3: import is inert and compatibility is explicit

Import first verifies the bounded inventory and native fingerprint, then
creates a private staged result. It performs no package installation, network
fetch, source execution, tool registration, provider binding, or activation.
Reject absolute paths, traversal, duplicate normalized paths, unsupported link
entries, and undeclared files before materialization. Validate the entire
package before publishing any visible result; failures leave no partial
definition or active binding.

Report compatibility separately for:
1. representation understood;
2. content preserved;
3. runtime requirements satisfied;
4. executable after local binding.

Unknown components remain intact and inspectable. Unsupported executable
components make the project non-runnable with named missing requirements;
they must never be silently omitted or executed through a permissive fallback.
The receipt includes source/project digest, adapter version, preserved or
rejected items, conversion loss, and compatibility outcome. Reuse existing
receipt mechanisms where their contract fits; document any necessary extension.

A new installation resolves its own private bindings. Activation is an explicit
subsequent operation under the destination's existing authority checks.
An imported request for a capability is data, never a grant.

## Decision 4: keep runtime enforcement below the replaceable harness

The harness owns its strategy and composition. The runtime owns durable run
identity, authoritative events/checkpoints, cancellation, resource limits, and
provider/tool/effect authorization. Exporting source cannot transport those
grants.

For the first fixture, use existing Node/Edge/State contracts and a deterministic
code path with no model or external effect. Record runtime version and supported
capabilities in the project. Replacing its transformation source must change
the fixture output without editing platform code.

Do not prematurely freeze a second session or task API. Where a custom loop
needs a missing runtime seam, demonstrate the smallest concrete failure and
review that seam separately. A stable interface is a compatibility commitment,
not a forecast of what the industry will name tools in two years.

## Acceptance experiment

1. Create a small ordinary harness with source, a declared input/output schema,
   a deterministic fixture, and one unfamiliar non-executable component.
2. Export the project and record native fingerprint, project digest, adapter
   version, and runtime identity.
3. Transfer it to an empty local installation with no hosted-app credentials,
   no commons database copied over, and network disabled for the fixture.
4. Inspect and import it without invoking source or activating a binding.
5. Re-export unchanged content: native fingerprint and file bytes must agree.
   Container timestamps need not agree; inventory and project digest must.
6. Explicitly run the supported fixture through the local runtime and compare
   its output with the frozen expected output.
7. Edit a source file and update the inventory using ordinary development
   tools. Run again and observe the intended changed result.
8. Import the same artifact through a browser user's governed workspace and
   demonstrate the same inspection and binding boundary. Retain a rendered
   conversation before claiming browser parity.

Negative cases cover tampered bytes, traversal/link entries, duplicate paths,
missing dependencies, unknown executable components, seeded private binding/run
sentinels, and interrupted import. A second-account import must acquire no
authority from the original account.

## Review decisions and delivery

Before implementation, resolve the namespaced project extension, artifact
storage/size limits, local fixture runner entry point, and exact digest encoding
against existing contracts. Obtain one cross-family shape review covering
portability, composition fit, and authority boundaries. Record its findings
and disposition in this change.

This PR is a reviewable proposal. It supplies no executable compatibility
claim, no live acceptance result, and no authorization to merge or deploy.

## Additional conformance scenarios

The delta spec and primitives.md require incompatible-port refusal, governed
strategy replacement, uncertain-effect reconciliation, and preservation of
external-content provenance. A descriptive-only unknown component proves
preservation; it cannot satisfy an executable requirement. Keep source export,
offline deterministic execution, model-backed replacement and rendered device
parity as separate evidence claims.

## Reviewed execution and materialization boundary

The first executable profile must define a concrete mapping from inventory source
references to Branch node source and its installed execution adapter. Merely
compiling a GovernedComponentDescriptor is not an execution result.

Materialize into a fresh governed workspace only after validating the complete
declared inventory. Canonical package paths use slash-separated relative segments;
reject empty, dot/dot-dot, absolute/drive/UNC paths, backslashes, NULs, links,
duplicate names and names colliding under the destination filesystem's case or
Unicode rules. Refuse unsupported names rather than silently normalizing two names
into one. Check each file's byte length and digest before exposing a staged project.
Keep the existing native fingerprint algorithm unchanged. For the new project
digest, choose RFC 8785 canonical JSON over the descriptor plus sorted inventory,
excluding the lock file itself; pin a conforming implementation and cross-language
vectors before executable compatibility is claimed.

Resolve the full required dependency closure from locked inventory/provider
identities, including nested compositions. Reject unresolved/ambiguous dependencies;
detect import cycles and support them only under an explicitly documented runtime
contract. Branch control-flow iteration is distinct from a cyclic package import.
No depth-one ceiling or speculative numeric package limits are adopted. Existing
runtime limits still apply; proposed package bounds must come from measured
representative projects and governed resource limits, with compatibility diagnostics.

For browser import, use an authenticated upload/staging transport that yields an
owner-scoped artifact reference to the governed workspace. The browser selects
bytes; it does not provide a server filesystem path. Fetching a remote package
requires separately held channel access. The implementation must identify the
actual existing upload handler or smallest missing seam, stage the bytes without
execution, and apply the same inventory validator as local import. A generic
workspace checkout alone does not prove this browser upload path.

Record the actual local Branch runner command, runtime revision, fixture paths,
materialization receipt and node/effect trace. The offline fixture must execute
through that runner with network disabled. Running the source as a standalone
script or displaying a compiled descriptor does not pass the Branch execution proof.
Browser acceptance additionally retains a rendered import/inspect/activate trace.
These are explicit unresolved implementation seams, not newly shipped APIs.
