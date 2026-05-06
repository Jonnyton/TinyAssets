# Export-As-App Artifact Recipe

Date: 2026-05-06
Status: proposed
Request: Issue #440 / WIKI-PATCH / PR-038
Wiki source: `pages/patch-requests/pr-038-workflow-needs-an-export-as-app-primitive-bundle-a-workflow-.md`
Classification: project design

## Context

The request asks for an "export-as-app primitive" that bundles a workflow as a
runnable local desktop application. The user value is real: a workflow should
eventually be shareable as something a local-app user can run without knowing
Workflow internals.

The current design, however, has an explicit minimal-primitive rule:
conveniences should not expand the MCP tool surface when they compose from
smaller primitives. The proposed primitive set already treats `workflow` as the
place to define executable graph shape, `run` as the place to deliver outputs,
`commons` as the publishing/remix surface, and `host` as the local-app hosting
surface.

## Proposed Decision

Do not add a top-level `export_as_app` MCP primitive.

Treat export-as-app as a first-class artifact recipe produced by existing
primitives:

- `workflow` defines the workflow, entrypoint, inputs, state schema, and node
  graph.
- `run` can build and return an app-bundle artifact from a workflow ref when a
  packaging recipe exists.
- `commons` publishes or remixes approved recipes and templates.
- `host` enables local-app users to execute, inspect, and approve the bundled
  runtime on their own machine.

If this later needs an API shape, prefer an additive artifact type such as
`app_bundle_recipe` or `app_bundle` under the existing workflow/run contract
over a new primitive/action.

## Minimal Contract Shape

An app-bundle recipe should be declarative and reproducible:

```yaml
type: app_bundle_recipe
schema_version: 1
workflow_ref: "<universe>/<branch-or-workflow-id>@<version>"
entrypoint:
  node_id: "<node-id>"
  input_schema_ref: "<schema-id>"
runtime:
  profile: "local-desktop"
  python: "<specifier>"
  workflow_version: "<specifier-or-lock>"
capabilities:
  required:
    - filesystem.read
    - filesystem.write
    - subprocess.spawn
  host_approvals:
    - filesystem.write
assets:
  include:
    - path: "..."
outputs:
  target: "desktop_app"
  formats:
    - "source_bundle"
    - "platform_installer"
provenance:
  source_workflow_ref: "<immutable-ref>"
  generated_by_run_id: "<run-id>"
  recipe_hash: "<hash>"
```

The source bundle is the first acceptance target. Platform installers are a
later packaging layer, not the initial contract.

## Required Safety Properties

- No secrets are embedded in the bundle. Secrets remain host-local and are
  requested through the host approval/keychain path.
- Capabilities are explicit before build and before first run.
- The generated bundle records provenance: source workflow ref, recipe hash,
  build run id, Workflow version, and template version.
- A host can inspect the recipe without executing arbitrary code.
- App templates are signed or otherwise tied to trusted Workflow releases.
- Builds are reproducible enough for review: same recipe plus same locked
  workflow should produce the same source bundle structure.

## Capability-Tier Behavior

Browser-only users can request or publish an app-bundle recipe and receive a
downloadable source bundle or shareable artifact URL, but they cannot execute a
native desktop app locally through the browser-only MCP surface.

Local-app users can build and run the bundle through their chat client or host
tray after approving the declared capabilities. This matches the user
capability axis: the primitive composition is the same, while the local tier has
more leverage.

## Non-Goals

- No new MCP tool or action in this proposal.
- No Electron, Tauri, PyInstaller, or platform-installer choice yet.
- No automatic execution of generated code.
- No code-signing policy decision beyond the requirement that installer work
  must define one before shipping.

## Acceptance Path

1. Accept or revise this design note.
2. Write a focused spec for `app_bundle_recipe` validation and provenance.
3. Add one source-bundle generator behind existing workflow/run boundaries.
4. Add tests for validation, secret exclusion, provenance, and capability
   declaration.
5. Only after source bundles are proven, decide whether platform installers are
   worth shipping.

## Rationale

The requested outcome is a delivery artifact, not an irreducible platform
primitive. Shipping it as a separate primitive would increase tool-surface
weight and overlap with `workflow`, `run`, `commons`, and `host`. Capturing it
as an artifact recipe preserves the user value while keeping the public
interface small and safer to evolve.
