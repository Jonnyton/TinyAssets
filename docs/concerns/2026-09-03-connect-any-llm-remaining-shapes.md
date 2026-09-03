# "Connect any LLM" is real for one endpoint shape, not every shape

Filed 2026-09-03, from the Codex review of `claude/connect-any-llm` (verdict
ADAPT). The lane fixed the findings it could; these two need a decision, not a
patch, so they are here rather than half-built.

## 1. `anthropic_messages` is offered but can never authenticate (P1, half fixed)

The endpoint pane offers two wire protocols. The deposit always sends
`auth_scheme="bearer"` (`tinyassets/onboarding/app.html`, `depositEndpoint`),
because `bearer` is the only scheme the pane can express. An endpoint that wants
the key in a named header (`x-api-key`, the shape the Messages API documents)
therefore gets the wrong authentication and fails at call time.

`connect_http` already accepts `header` in `_DEPOSITABLE_AUTH_SCHEMES`
(`tinyassets/api/http_connection.py:105`), but **`header_name` is not a
deposit-time field** — it exists only for `authenticated_external_call`. So the
pane cannot express "this key goes in `x-api-key`" today.

Not silently removed, because it is not universally broken: gateways that speak
the Messages wire shape while accepting `Bearer` do work. It is broken for
endpoints that follow the published spec, which is the more common case.

**Decision needed:** add `header_name` to the deposit contract (a public-surface
change — wants a proposal), or stop offering the protocol until it can be
authenticated honestly.

**Fixed in the same lane, for contrast:** the *path* half of the same finding.
The grant carried the user's own path while the runtime called the protocol's
canonical one, so every endpoint whose path was not `/v1/chat/completions` was
registerable and never servable. `_declared_path` in
`tinyassets/providers/api_key_http_provider.py` now calls what the user granted.

## 2. The picker's company names — RESOLVED 2026-09-03

Founder's ruling: **reword neutrally.** Done in this lane. The two options and
`SERVICE_LABELS` are now named by the CREDENTIAL SHAPE the user hands over ("a
subscription — you paste an OAuth token" / "...a signed-in CLI's auth.json";
"your OAuth subscription" / "your CLI subscription"). The `value="claude"` /
`value="codex"` wire ids are unchanged, so existing bindings keep working.

`test_the_whole_connect_surface_names_no_vendor` and
`test_the_serving_status_lines_name_no_vendor` now cover the picker and the
status lines, which the pane-scoped test could not see. Both mutation-checked:
putting either company name back goes red.

**Correction worth keeping.** I first put this to the founder as "these two
options are host-CLI-backed", implying they conflict with "the platform never
supplies an LLM", and the founder reasonably chose to CUT them. That framing was
wrong. `bind_serving_provider` calls `adopt_llm_subscription_custody(...)` and
the CLI runs against a sealed read-only snapshot of the USER's deposited
credential (`credential_snapshot_dir` -> a private tmpfs `CODEX_HOME`). The host
supplies the binary; the user supplies the credential — which is the BYO-LLM
model, not the platform lending an LLM. Cutting them would have deleted the
working subscription path for every user. What IS host state is
`llm_endpoint_bound` in `get_status` (§ below), and conflating the two is what
produced the bad question.

## The real host-state problem, which is NOT this one

`get_status` reports `active_host.llm_endpoint_bound` — computed from the
daemon container's own filesystem (`shutil.which("codex")` plus
`~/.codex/auth.json` existing) — and has **no per-universe serving field at
all**, alongside a cooldown table for six host providers that may never serve
anyone. A universe with no serving binding therefore reads as powered.

That is what tiny hit on 2026-09-03: prompt nodes failing
`permission_denied:provider_not_bound` while workspace and http branches
completed, with status insisting a provider was bound. It concluded "internal
runtime mismatch" and told the founder *"this does not look like a case where
I'm waiting on your approval"* — the opposite of the truth. The universe simply
had nothing serving, and the founder was the only one who could fix it.

Filed separately from the two items above because it is a different defect: not
copy, not a missing capability, but a field named for a per-universe fact that
measures a host fact. The fix is a real per-universe serving field in
`get_status`, not a better caveat string.
