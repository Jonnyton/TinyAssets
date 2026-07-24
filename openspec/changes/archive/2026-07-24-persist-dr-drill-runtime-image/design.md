## Context

Run `30065054549` used the exact landed runtime-image pin. Compose could pull
and create the daemon because the digest was supplied as a command-scoped
interpolation variable, but `compose.yml` gives the container its environment
from `/etc/tinyassets/env`. The fresh template's `TINYASSETS_IMAGE=` remained
empty, so the image entrypoint correctly failed closed with `ENV-UNREADABLE`.
On retained Droplet `587161699`, replacing only that assignment with the
already validated public digest made the container healthy and an MCP
initialize/tool call passed.

The red probe also exposed two workflow-truth gaps: the probe step records a
red output but exits zero after emitting it, and retained hosts currently need
an operator's local DigitalOcean credential even though the repository already
has a scoped cleanup credential.

## Goals / Non-Goals

**Goals:**

- Make the validated digest available both to Compose interpolation and to the
  daemon container without transferring production secrets.
- Require exactly one fresh-template assignment so malformed templates fail
  closed.
- Make a red MCP probe produce a red workflow conclusion after issue creation.
- Provide a cleanup-only manual dispatch for one explicitly supplied Droplet
  ID without provisioning or touching backup/SSH inputs.

**Non-Goals:**

- Copying the primary host's env file or any secret.
- Starting cloudflared, vector, or workers in the recovery drill.
- General-purpose DigitalOcean resource administration.

## Decisions

1. **Persist only the public digest in the disposable host template.** After
   bootstrap, a remote Python snippet validates the same canonical digest
   shape, requires exactly one `TINYASSETS_IMAGE=` line, and replaces its
   value in place. Compose then reads the one env file for interpolation and
   container injection. This is safer and easier to audit than adding a second
   container-environment override or copying production configuration.

2. **Use a separate cleanup job selected by one optional input.** A non-empty
   `cleanup_droplet_id` skips the drill job entirely. The cleanup job validates
   a positive decimal ID, checks only `DIGITALOCEAN_TOKEN`, reads that resource
   through the bounded helper, requires the exact drill name plus both drill
   tags, and only then invokes one DELETE. This avoids creating a second host
   merely to clean up the first or deleting an unrelated Droplet after an ID
   typo.

3. **Fail explicitly after red-probe handling.** The probe continues to emit
   structured outputs so issue and retention policy steps can run. A final
   conditional step exits nonzero when `color == red`; the run conclusion can
   no longer contradict its evidence.

## Risks / Trade-offs

- **[Template drift creates zero or duplicate assignments]** → fail before
  Compose rather than guessing which value wins.
- **[Cleanup input targets the wrong Droplet]** → require an explicit positive
  decimal ID plus the expected `tinyassets-dr-drill` name and both
  `dr-drill`/`tinyassets` tags; expose no list or wildcard operation.
- **[Public digest persists until failed-host inspection ends]** → it is
  already published in image metadata and failure evidence; no credential is
  added.

## Migration Plan

Land through CI, invoke cleanup-only for retained Droplet `587161699`, then
dispatch the full drill from the exact merge SHA. A successful run must prove
fresh bootstrap, verified restore, healthy daemon, MCP initialization, and
confirmed deletion before its PASS log is accepted.

## Open Questions

None.
