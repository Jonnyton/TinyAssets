## Context

Run `30062035537` was dispatched from landed SHA
`2fbd77410c04cc247929eeb222f1bc65a8fd0c01`. Archive validation succeeded, and
the newly bounded API surface exposed the next failure precisely: DigitalOcean
returned HTTP 422 because `debian-12-x64` is no longer a valid creation image.
DigitalOcean's current image catalog names `debian-13-x64`.

The image is provider inventory, not a TinyAssets release identity. Pinning it
in source turns routine provider retirement into a code outage for the DR
surface.

## Goals / Non-Goals

**Goals:**

- Select a currently available Debian x64 distribution image before resource
  creation.
- Keep selection deterministic, region-aware, and independently testable at
  the workflow-contract boundary.
- Preserve bounded/redacted provider diagnostics and the no-resource cleanup
  invariant.

**Non-Goals:**

- Rewriting the bootstrap script for a non-Debian distribution.
- Hiding a bootstrap incompatibility with a newly current Debian release.
- Dispatching again before this change lands.

## Decisions

### Resolve provider inventory at dispatch time with bounded pagination

Before key lookup/creation or any other mutating request, the provision step
invokes `scripts/select_do_image.py`. The selector uses
`scripts/do_api_request.py` to start at
`/v2/images?type=distribution&per_page=200`, then follows
`links.pages.next` for at most 10 pages. Every continuation must remain an
HTTPS URL on `api.digitalocean.com` with the exact `/v2/images` path. Repeated
URLs, cycles, malformed pagination, a continuation beyond the page budget, or
any failed continuation are red. A response with no `links`/`pages`
navigation is a valid terminal page; navigation that is present but malformed
is red.

Selection runs over the aggregate. An eligible item satisfies the provider
schema exactly: `public is true`, `status == "available"`,
`distribution == "Debian"`, `regions` is a string array containing the
configured region, and `slug` fully matches `debian-<numeric-major>-x64`. The
selector chooses the highest numeric major. Missing/malformed inventory is red
before the conditional SSH-key POST and before the Droplet POST; there is no
fallback pin.

The selected slug is written to the provision step output before later
operations and is included in PASS logs, probe-failure issues,
delete-failure escalations, and the step summary.

### Let the drill expose bootstrap compatibility

Selecting the provider's newest available Debian image may reveal bootstrap
incompatibility when Debian advances. That is a truthful DR failure: the
fresh-host path is not recoverable on the currently provisionable base image.
The existing bootstrap log capture, mid-job cleanup, and bounded escalation
remain responsible for that evidence.

## Risks / Trade-offs

- **[The token needs image catalog read access]** → `image:read` is an explicit
  prerequisite alongside account-key and Droplet scopes. The first selector
  request is the pre-rerun permission check; a missing scope fails before any
  mutation with the bounded diagnostic. The runbook names this requirement.
- **[A future Debian major may require bootstrap changes]** → the drill becomes
  red after provisioning and performs cleanup, rather than silently testing an
  unavailable retired image.
- **[Provider pagination could hide candidates or loop]** → the selector
  aggregates up to 10 pages, validates the exact continuation origin/path,
  detects repetition/cycles, and fails closed rather than treating a partial
  page as complete inventory.

## Migration Plan

1. Land the workflow, selector, tests, runbook scope prerequisite, canonical
   delta, and archived change.
2. Dispatch drill #3 from the exact landed SHA. The initial catalog request
   verifies `image:read`; do not retry if it returns a bounded permission error.
3. Treat a green bootstrap on the selected Debian 13 image as the compatibility
   proof needed to update the bootstrap's Debian-version claim; if bootstrap is
   red, retain its log and let cleanup run.
4. Record selected image plus the terminal restore/cleanup evidence or the next
   bounded failure.

Rollback is a normal git revert.
