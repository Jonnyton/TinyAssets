## Why

The authenticated ingress and founder mapping now exist, and the custody issuer produces signed handoff evidence, but no server-owned seam decides whether a reply may target the mapped app destination.

## What Changes

Add a dark reply-authority gate that verifies the canonical custody signature, revalidates the current founder mapping, resolves a server-owned destination, and emits a content-free authorization for a future outbound adapter. It adds no route, public handle, message storage, effect, or runtime invocation.
