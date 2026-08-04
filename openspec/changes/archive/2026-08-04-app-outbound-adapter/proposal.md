# Proposal: Server-owned app outbound adapter

## Why

Ingress, founder mapping, custody issuance, and content-free reply authorization now exist, but no bounded server-owned adapter can turn an authorized response into an app delivery. The V1 experience therefore stops before the agent can answer the user's Slack thread.

## What changes

- Add a durable, idempotent adapter boundary that accepts only `AppReplyAuthorization` plus private response text.
- Recompute and verify the response digest before transport invocation.
- Invoke a server-owned transport callback with an exact destination and no credential material.
- Persist only redacted receipt metadata and make replays return the same receipt without a second delivery.

## Out of scope

No MCP handle, cloud mint, provider execution, workflow mutation, Slack secret storage, or production transport registration is added by this dark prerequisite.
