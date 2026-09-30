---
severity: note
title: A generic HTTP 5xx does not attest zero upstream generation
filed: '2026-09-30'
summary: The adapter proves that no response was decoded locally, but does not prove that a remote model generated or billed nothing before a gateway error.
---

Review concern, not a reproduced upstream incident, at b3a37d37.

`tinyassets/providers/api_key_http_provider.py:413` and `:424` attach
`side_effect_state=none` to capacity errors and generic 5xx envelopes. The broker
retains only the returned HTTP status, headers and buffered body
(`tinyassets/storage/outbound_connections.py:3396`). This cannot rule out an
upstream gateway returning 502/504 after its model generated output or began an
upstream stream. Local decoding and tool dispatch have not happened: decoding
starts at `api_key_http_provider.py:440`. That narrower fact is supported.

The claim that no token was generated is stronger. The workflow router also
settles these ProviderUnavailableError subclasses with zero usage
(`tinyassets/providers/router.py:1224`). That settlement predates this change;
the new workflow fallthrough makes another invocation possible afterward.
Invocation counts and accepted request price ceilings remain bounded.

Clarify the evidence's scope and avoid treating a generic remote 5xx as proof of
zero remote usage without a source contract guaranteeing pre-generation refusal.
