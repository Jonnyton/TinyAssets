# Test chat provider request rejected with HTTP 413

Observed 2026-10-02 at 13:41 PDT in the live Chrome conversation at
https://tinyassets.io/app, immediately after Spot sent the user-authorized `hi`
at 13:40 PDT. Browser account inspection, typing, and Send all succeeded under
normal approval review.

The rendered reply reported HTTP 413, "Request too large", for Groq's
`openai/gpt-oss-120b`, one model request, and "Nothing ran". Error reference:
`5846f6bcc68648199be3cafeeefaf822`. The conversation history and model bar were
OpenRouter-labeled; the error named Groq. The cause and significance of this
provider-label difference have not been established.

Evidence: Spot task `01a0fe56-f550-74bf-aec8-f5e4981e8007`, Chrome 3 tab
`1346524224`. Completed tool calls inspected the account, typed `hi`, clicked
Send, read the resulting page, and captured a screenshot. Local evidence is
`C:/Users/Jonathan/Documents/Codex/2026-10-02/browser-access-repair-01a0fdcf/spot-browser-send-success.json`.
Captured with `python -u app-tools-probe.py spot-greeting-task-read.json` from
that diagnostic directory, using the official app-tools MCP read_thread tool.

Follow-up: trace the error reference in server logs and inspect the actual
provider request size and routing. Do not infer a root cause from the greeting's
short length. This is separate from the verified recovery of Spot's browser
startup and inherited user-authorization context. No runtime code or provider
settings were changed for this finding; no retry was sent.
