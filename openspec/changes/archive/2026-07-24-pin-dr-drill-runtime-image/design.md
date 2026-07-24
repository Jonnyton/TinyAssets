## Context

Bootstrap intentionally creates `/etc/tinyassets/env` from a secret-free
template whose `TINYASSETS_IMAGE` is empty. The production host contains the
current immutable image reference, but its environment also contains secrets
that must not be copied to a disposable drill host. Docker Compose evaluates
required interpolation across the compose model before selecting the requested
service, so `up -d daemon` cannot start with an empty image.

The DR workflow already has read-only SSH access to the primary host for backup
selection and transfer. The image reference is operational configuration, not
a credential.

## Goals / Non-Goals

**Goals:**

- Start the drill daemon with the exact immutable image configured in
  production.
- Fail before provisioning if the image is missing, mutable, or outside the
  canonical GHCR repository.
- Avoid copying or persisting any production secret on the drill host.
- Distinguish the Debian base image from the daemon runtime image in evidence.

**Non-Goals:**

- Reproduce production tunnel, OAuth, provider, or logging credentials.
- Start worker, tunnel, or log-sidecar services during the drill.
- Resolve a new runtime image from a mutable tag.

## Decisions

### Read and validate only the configured image assignment

A pre-provision step reads only the final `TINYASSETS_IMAGE=` assignment from
`/etc/tinyassets/env` on the primary host. Because the canonical environment
format permits quoted or unquoted values, the runner removes at most one
matching pair of surrounding single or double quotes. It then accepts only:

`ghcr.io/jonnyton/tinyassets-daemon@sha256:<64 lowercase hex>`

The validated value is safe for a single-line GitHub output. Missing,
mismatched/nested quotes, duplicate-output injection, whitespace, tags,
alternate repositories, and malformed digests fail before any DigitalOcean
mutation.

Alternative considered: copy the primary environment. Rejected because it
would place tunnel, OAuth, and provider credentials on an ephemeral host.

Alternative considered: derive an image from the workflow SHA. Rejected
because a documentation-only merge may have no image, while the drill must
test restored data against the image production is actually configured to run.

### Supply the image ephemerally to Compose

The start step shell-quotes the validated reference and supplies it as the
`TINYASSETS_IMAGE` process environment while also loading the fresh host's
template with `--env-file /etc/tinyassets/env`. It does not write the production
reference or any primary environment material to disk.

### Retain both image identities in terminal evidence

PASS, probe-failure, deletion-failure, and summary evidence label the provider
base image and daemon runtime image separately.

## Risks / Trade-offs

- **[Configured production image could be stale]** → The deploy pipeline owns
  configured/running identity convergence; this drill consumes its canonical
  immutable configuration rather than inventing another image authority.
- **[A malicious value could inject workflow output or shell syntax]** → Exact
  full-string repository/digest validation after bounded quote normalization
  precedes output publication, and the remote shell receives a `printf
  %q`-quoted value.
- **[Fresh template may omit a future daemon-required nonsecret value]** → The
  drill remains red at daemon start and exposes that recovery prerequisite
  rather than copying the whole production environment.

## Migration Plan

1. Land workflow, tests, synced spec, and archived change.
2. Dispatch the exact landed commit through the production DR workflow.
3. Record daemon start, MCP probe, and deletion evidence or the next bounded
   failure.

Rollback is a normal git revert.

## Open Questions

None.
