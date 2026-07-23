## Context

`_canary_common._post` converts an HTTP failure into `ToolCanaryError` and
retains the original `urllib.error.HTTPError` as its exception cause. The
canonical connector contract now challenges anonymous pure writes before tool
dispatch, so a successful authentication-gate probe is intentionally an HTTP
error at the shared transport seam.

## Goals / Non-Goals

**Goals:**

- Recognize only the canonical HTTP 401 with a non-empty
  `WWW-Authenticate` header as green anonymous-write evidence.
- Continue the persisted anonymous read proof after that challenge.
- Keep the diagnostic captured by the GitHub Actions canary output.

**Non-Goals:**

- Change the connector authentication protocol, OAuth negotiation, or
  `_canary_common`'s shared error behavior.
- Treat a JSON rejection envelope as compatible fallback behavior.
- Add authenticated wiki-write coverage or mutate the persisted probe draft.

## Decisions

### Inspect the chained HTTP error at the wiki boundary

`wiki_canary` will catch the write-step `ToolCanaryError` and inspect
`__cause__` for `urllib.error.HTTPError`. It accepts only code 401 plus a
non-empty `WWW-Authenticate` header, then proceeds to the read check. This
keeps the exception transport contract shared and avoids weakening the canary
with message parsing.

Alternative considered: changing `_canary_common._post` to return HTTP status
and headers. Rejected because other canaries rely on the existing fail-closed
error mapping and this exception is solely an expected outcome for this probe.

### Dispatched tool JSON remains a failure

A returned JSON-RPC result proves that `write_page` was dispatched. The old
rejection envelope and any accepted response therefore remain exit 6, even if
their contents imply an authorization refusal. This enforces the connector
owner's pre-dispatch contract rather than preserving a retired transport shape.

### Request GitHub Actions output mode explicitly

The workflow will call `wiki_canary.py --format gha` while retaining the
captured stdout/stderr block in `wiki_msg`, so an exit-6 diagnosis appears in
the combined incident evidence.

## Risks / Trade-offs

- [A gateway returns 401 without OAuth metadata] → Fail red; the header is
  required evidence that clients can launch sign-in.
- [A non-HTTP exception uses a similar message] → Fail red; classification is
  based on exception type, code, and header rather than text.
- [A tool response continues to return JSON rejection] → Fail red; this
  reveals a connector protocol regression rather than masking it.
