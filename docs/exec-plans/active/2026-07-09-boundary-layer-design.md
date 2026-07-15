# Boundary Layer — Inputs, Outputs, Connectivity (2026-07-09)

**Status:** Binding design note. Composes existing primitives (design law holds). Worked example: the weekly payables run.

## 1. MCP both directions
The platform serves MCP inward (chatbots -> universes) and universes speak MCP OUTWARD as clients (Gmail, accounting, calendars, anything). The platform builds no integrations; nodes hold *connections* exactly as nodes hold models. Connector definitions (MCP client config + normalization workflows) are commons artifacts, remixable with attribution.

## 2. Grants live in the resource ledger
USER-PATH Step 1 generalizes: attach capabilities = compute + subscriptions + keys + **connections**. Credentials are user grants, scoped per-universe, revocable; universes never own them. A source/effector node declares its needed connection class (`source:gmail`, `sink:<payables>`); binding happens against the ledger's grants at run time.

## 3. Action caps (autonomy envelope, second column)
Alongside unprompted-SPEND caps, unprompted-ACTION caps: e.g. `read: auto · file: auto · send: auto · pay <= $500: auto · pay > $500: hold-for-confirmation`. Consequential effectors default to hold-above-threshold with an actionable confirmation surface (the P0 lesson generalized: writes get gates with useful holds, never silent behavior in either direction).

## 4. Exactly-once effects (HARD RULE — Opus must not improvise)
- Every effector call carries a **deterministic idempotency key** = hash(goal_id, schedule_period, item_fingerprint). "Invoice #4471 in the 2026-07-10 run" can effect exactly once, ever, across any number of retries.
- Every external effect is journaled in an **effect ledger** (intent row before firing, result row after), keyed by idempotency key; replays consult the journal first.
- Failure posture: fail loud, HOLD THE WHOLE BATCH, surface the hold with remediation. Never partial-silent. This is the boundary sibling of settlement conservation.

## 5. Human as sensor: the goal inbox
Standing goals expose an inbox: the user drops items in from any surface (photo of a paper invoice from the phone) and they join the next scheduled batch. Inputs are APIs + humans, symmetrically.

## 6. Scheduling
Standing goals carry a schedule field (cron-class: "Thu 08:00 weekly", timezone-aware) executed on the proactivity heartbeat. Schedule is part of the goal spec, visible in the commons archetype.

## 7. Worked example — weekly payables (commons archetype: "payables-run")
Thu 08:00 -> source:gmail pulls invoices + goal inbox drains (mailed/scanned items) -> normalize nodes (vendor match, company conventions, filename policy — commons recipes) -> reconciliation gate (machine-checkable: totals match, no duplicate idempotency keys, vendor whitelist) -> effector sink:payables files/schedules payments under action caps (auto <= threshold, hold above) -> effect ledger entries -> summary lands for the user. Every step remixable; the archetype ships as a launch commons artifact.

## 8. Strategic note — the fourth door
Small-business ops (the payables owner) is the door with day-one willingness-to-pay: recurring, high-value standing goals that monetize before the hobbyist doors do. Marketed last, monetizes first. Add to GTM as such; the archetype in §7 is its seed.

## 9. Generality: the thousands of servers/APIs (amended same day)
- **MCP servers:** native — self-describing tools, discovered at connect time; grants = {server, auth, scopes}.
- **Non-MCP APIs (the long tail):** **adapters are commons artifacts** — small programs wrapping an API into MCP shape. OpenAPI spec -> adapter is mechanical generation, run as a workflow: "connect to X" is something the universe DOES, not a platform integration ticket. Vibe coder gets found/generated adapters; hardcore user forks adapter source. Coverage is community-shaped.

## 10. HARD RULE — adapters never see credentials
Commons adapter code + user secrets = credential theft as a service. The connection runtime injects auth at the boundary (proxy pattern): adapters declare scopes and receive authenticated transport, never keys. Grants scope domains + verbs; every outbound call lands in the effect ledger. Worst-case malicious adapter = in-scope, fully-journaled calls — never exfiltrated credentials.

## 11. Addressable inboxes (inbound primitive)
Every universe/goal exposes a webhook URL AND an email address (e.g. pay@<user>.tinyassets.io). Email is the most universal API on earth; vendors emailing invoices straight into Thursday's batch costs one MX record. Inbox items are typed artifacts (§12) entering the next scheduled run.

## 12. Typed artifact flows (files: any type, both directions)
Every node input/output is a typed artifact: content-addressed blob + MIME + optional schema. Decoders (`decode:pdf`, `decode:image-ocr`, `decode:xlsx`, ...) and encoders (`encode:pdf`, `encode:stl`, ...) are ordinary capability-class nodes — deterministic or AI, commons-supplied, community-extensible forever (no platform format matrix). **Type mismatches are graph-validation errors at design time** — pipelines fail loud before a token is spent, never silently at Thursday 08:00.
