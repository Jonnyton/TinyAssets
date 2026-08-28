# A refused outbound effect still completes the run, logs nothing, and reports no error

**Filed:** 2026-08-28
**Verified:** 2026-08-28, live, on the founder's own universe.
**Severity:** P1 — it does not corrupt anything, but it makes a failed action
indistinguishable from a successful one, which is the failure mode Hard Rule 8
exists to prevent.

## What happened

The universe ran its `GitHub HTTP Caller` branch to create a branch. GitHub
refused with **403**. The run recorded:

```
status:  completed
error:   ""
node:    call_github -> ran
```

No branch was created. **Nothing about the 403 reached any log**: across a 25
minute window the daemon log contained *zero* lines matching `github`,
`external_call`, `effect`, or `403`.

The refusal was not lost — it is in the effect-evidence map, which the agent had
to be asked for by name:

```json
{"call_github": {"authenticated_external_call": {
  "delivered": true,
  "response": {"body": "{\"message\":\"Resource not accessible by personal
     access token\",\"status\":\"403\"}",
     "headers": {"x-accepted-github-permissions": "contents=write; ..."}}}}}
```

## Why it matters

Three observers all saw success or silence:

* **The run record** said `completed` with an empty `error`.
* **The log** said nothing at all.
* **The agent** reported *"the platform run is still stuck after the outbound
  step, so I do not have a GitHub response I can report honestly"* — it could not
  see its own result either, and it was right not to guess.

So the universe retried variations of the same call for hours, built a second
connection (`github-theme`) to work around a wall that was not where it thought,
and raised approval tabs asking the founder to paste a key that was already in
the vault and already working. The one fact that would have ended it —
`x-accepted-github-permissions: contents=write` — was sitting in a response
nobody surfaced.

It also cost this session directly: with the log empty and the run green, the
reasonable reading was that the effect never fired at all. It had fired.
`delivered: true` and a 403 body were both there the whole time.

## The structural point

`delivered` means *the HTTP request reached the destination*, not *the action
succeeded*. Nothing downstream distinguishes those, so a 4xx/5xx response is
recorded exactly like a 201. `_run_external_write_effectors` is documented as
"never raises — all errors are folded into the returned evidence map", which is
right for robustness and wrong as the whole story: folding an error into a map
nobody reads is not reporting it.

## What would fix it

1. **A non-2xx effect response must fail the run, or at minimum populate
   `error`.** A run whose only purpose was one outbound call, where that call was
   refused, is not `completed`.
2. **Log the status line.** One `logger.warning` with sink, destination, status,
   and the response's first bytes would have ended this in seconds. There is no
   secret in a status code or in `x-accepted-github-permissions`.
3. **Surface the evidence to the agent by default**, so it does not have to be
   asked for the raw map. The agent behaved correctly — it refused to invent a
   status it could not see. It simply had no way to look.

## How to resolve this file

Delete it when an outbound effect that receives a 403 produces a run that is not
`completed`-with-empty-error, and a log line naming the status — both proven by
test, and observed once on the live surface.
