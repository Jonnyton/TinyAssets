## 1. Design

- [x] 1.1 Research the four reference harnesses from current sources; audit tiny's code paths, production turns and its own files (design.md §1-2).
- [x] 1.2 Founder approval of the design (2026-10-01, "approved"); open questions proceed on the recommendations (design.md §5). gpt-6-astra refute review ADAPT folded in.
- [ ] 1.3 Archive `universe-harness-four-tools` after syncing its built S1 delta; this change carries its S2-S8 plan forward.

## 2. Slices (each its own PR, live-proven in the founder's app before the next starts; a slice touching storage shape opens its own proposal first)

- [ ] 2.1 S1 Sessions, tone, authority: resume-capable adapters continue a durable native session per thread or agent node (no `--ephemeral`); resumed turns send only the new message and unseen messages; editable seeded `AGENTS.md` carries tone and authority; persona warmth/ask/per-turn-consent text deleted.
- [ ] 2.2 S2 Owner messages steer the live turn: owner messages and owner-relevant events appended to the next tool result with the unread count; the same mechanical line opens an idle session's next turn.
- [ ] 2.3 S3 Network, browser, toolchain, writable root: filtered egress, headless browser, python/node/git in the jail; platform state moved to `.runtime/`.
- [ ] 2.4 S4 Truthful tools, full journal, platform session log: HTTP-loop session log with compaction on the universe's own model; every adapter journals tool calls; oversized output spills to a file; one-line real causes; live tool activity in the app.
- [ ] 2.5 S5 The platform is one extension: `ta` CLI over the per-universe socket and deferred MCP; resident tool block cut to the core four; handbook chapters become skills.
- [ ] 2.6 S6 Self-improvement with versioning: jailed history store and Undo; `MEMORY.md`; `settings.yaml`; seed skill and curator workflows; owner `read_brain`/`write_brain`/`soul_edit` and the separate learning call deleted.
- [ ] 2.7 S7 Outward actions without friction: `ta connect call`/`ask` over the existing credential-blind effectors and standing destination grants (checks unchanged); batched asks; remaining per-action-consent guidance removed.
- [ ] 2.8 S8 Every universe gets the harness: seed new universes from an explicitly published, reviewed starter template (never the live private subtree); delete the replaced handles and resident guidance; `ui-test` plus canary `--assert-handles`.

## 3. Close

- [ ] 3.1 Sync the deltas into `openspec/specs/` and archive this change once S8 is live.
