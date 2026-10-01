## 1. Design

- [x] 1.1 Research the four reference harnesses from current sources; audit tiny's code paths, production turns and its own files (design.md §1-2).
- [ ] 1.2 Founder approval of the design and answers to the two open questions (design.md §5).
- [ ] 1.3 Archive `universe-harness-four-tools` after syncing its built S1 delta; this change carries its S2-S8 plan forward.

## 2. Slices (each its own PR, live-proven in the founder's app before the next starts; a slice touching storage shape opens its own proposal first)

- [ ] 2.1 S1 Sessions, tone, authority: session log + resume + compaction with flush; seed `AGENTS.md` replaces the persona prompt; per-turn consent line and the separate learning call deleted.
- [ ] 2.2 S2 Wakes are events into the session: agent-node sessions resumed by events; steering at tool boundaries; unread counter; mechanical "since your last turn" message.
- [ ] 2.3 S3 Network, browser, toolchain, writable root: filtered egress, headless browser, python/node/git in the jail; platform state moved to `.runtime/`.
- [ ] 2.4 S4 Truthful tools, full journal: every adapter journals tool calls; oversized output spills to a file; one-line real causes; live tool activity in the app.
- [ ] 2.5 S5 The platform is one extension: `ta` CLI over the per-universe socket and deferred MCP; resident tool block cut to the core four; handbook chapters become skills.
- [ ] 2.6 S6 Self-improvement with versioning: universe git auto-commit and Undo; `MEMORY.md`; `settings.yaml`; seed skill and curator workflows; owner `read_brain`/`write_brain`/`soul_edit` deleted.
- [ ] 2.7 S7 Outward actions on standing grants: credential-blind `ta connect call`; grants per destination; batched asks; effector per-turn consent deleted.
- [ ] 2.8 S8 Every universe gets the harness: seed new universes from the founder's harness subtree; delete the replaced handles and resident guidance; `ui-test` plus canary `--assert-handles`.

## 3. Close

- [ ] 3.1 Sync the deltas into `openspec/specs/` and archive this change once S8 is live.
