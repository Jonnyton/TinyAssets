# Agent Village security — Opus 5 review

Date: 2026-07-25  
Reviewer: Claude Opus 5, independent read-only peer  
Reviewed implementation: `dd053ebfad643f08762eb818435e66d5c9090e24`  
Final verdict: **APPROVE**

## Scope

The review covered the cumulative `secure-agent-village-local-surface` change:
loopback defaults, generated and explicit bearer handling, private read/write
authorization, query-token rejection, browser fragment bootstrap, persistent
401 recovery, request-body boundaries, security headers, tests, and OpenSpec
alignment.

## Review history

Opus's first two passes returned `CHANGES_REQUIRED`. The implementation then
closed every blocking finding:

- non-ASCII or malformed bearers now fail closed with `401` rather than
  crashing `compare_digest`;
- invalid explicit tokens fail at startup;
- a tokenless browser shows a dedicated persistent access-required alert;
- same-tab fragment navigation reloads, strips the fragment, and resumes
  authenticated polling;
- ordinary toasts cannot replace the access alert;
- centralized `401` handling covers state, provider, chat, talk, and hire
  requests and clears the chat timer;
- the fragment share button preserves the bearer after visible-history cleanup;
- browser-auth regression tests go red when the handler is removed.

## Independent evidence

The approving pass reported:

- `49 passed` for `tests/command_center/`;
- Ruff clean;
- strict OpenSpec validation clean;
- raw-socket probes for malformed bearers, CSRF/CORS, request boundaries, and
  headers;
- mutation probes across authorization, query tokens, token validation, body
  caps, loopback defaults, share URLs, and security headers;
- real Chrome proof for tokenless load, persistent alert, same-tab recovery,
  token rotation with an open chat sheet, fragment removal, resumed polling,
  timer quiescence, and a clean console.

No authorization bypass or blocking requirement gap remained.

## Non-blocking follow-up

The reviewer retained optional hardening ideas around socket deadlines, stricter
HTTP framing, legacy query-token residue, edge-case explicit-token ergonomics,
CLI argument visibility, and still-finer browser mutation coverage. Per the
2026-07-25 product decision, these do not create a new Agent Village product
lane: the existing unsafe surface receives this minimum containment, while the
chatbot + connector path remains the canonical first-class experience and
Village shape is deferred until the rest of the platform is mature.
