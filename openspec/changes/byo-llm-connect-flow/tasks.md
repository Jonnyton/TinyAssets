# Tasks — byo-llm-connect-flow

Generic for every user; no special path for the dogfood universe. Security
substrate — Codex-built, dual-family reviewed before any live rollout. The Slack
recall+reply proof completes once slice 1 lands.

## Slice 1 — mint + wire a requester-owned chat/completion provider binding
- [x] 1.1 Add a way to MINT a general-purpose chat/completion `provider_binding`
      (agent/host *serving*, not automation-shaped) from a requester-owned
      credential already present in a universe's vault. Requester-owned +
      forgery-proof (authority derived from server-held state, per keystone #2399,
      not caller-asserted payload).
- [x] 1.2 Wire a universe's `agent_binding.provider_ref` to a real minted binding,
      replacing a placeholder / mis-scoped ref; reject binding to a provider_binding
      whose `allowed_operations` does not include chat/completion.
- [x] 1.3 Host serving path: a controlled write-path so a universe with a connected
      chat/completion binding actually serves conversational turns (the flag the
      connector has no path to today) — fail-closed when absent.
- [ ] 1.4 Reset the drift left by the 2026-08-10 live diagnosis:
      `agent_binding_01kz0k6mwe61a0ph60a2hzp01x` points at the GitHub grant
      `pwb_fbddd0e8…` (grants no authority); repoint at its real minted binding.
- [x] 1.5 Tests: minting is requester-owned + rejects non-chat/completion scopes;
      wiring rejects mis-scoped refs; a served turn resolves the universe's own
      binding and never an ambient host credential. Mirror parity rebuilt.
- [ ] 1.6 Live proof: u-tiny/Demo App serves a real Slack reply; the durable-memory
      recall+reply proof (store advances past 130, recalls prior context) completes.

## Slice 2 — one-click provider-OAuth connect UX + vault capture
- [ ] 2.1 "Connect Claude" / "Connect ChatGPT/Codex" federating to each provider's
      own OAuth/device-flow; capture the returned credential as requester-owned into
      the universe's vault. API-key paste as the alternate for API-key providers.
- [ ] 2.2 A `connections` entry per connected provider (Anthropic/OpenAI), surfaced
      in `read_graph target=connections`; connect once → mint bindings (slice 1) from it.
- [ ] 2.3 Generic "point this universe at its GitHub project" binding — available to
      any user, no special path — so a universe has both its provider and its repo.
- [ ] 2.4 `ui-test`: a user connects a subscription through the chatbot and the
      universe becomes runnable, end to end.

## Slice 3 — prune every non-intended LLM route + guard
- [ ] 3.1 Remove host-writer / writer-"fleet" / `fantasy_daemon` LLM-provisioning
      code and the ambient host-credential fallback in `providers/base.py`
      (`CLAUDE_CODE_OAUTH_TOKEN`/`CODEX_HOME` borrow) + any platform-supplies-an-LLM
      branch. The connect flow (slices 1–2) is the ONLY surviving LLM route.
- [ ] 3.2 GUARD test: assert no code path can reach an LLM without a
      universe-authorized, requester-owned provider — fail-closed everywhere, no
      ambient borrow. Differential/grep-based enforcement, not just a happy-path test.
- [ ] 3.3 Delta-spec `provider-routing`: sole-path resolution + fail-closed
      requirements + scenarios; sync into `openspec/specs/` on land.

## Cross-cutting
- [ ] 4.1 Dual-family (Claude + Codex, latest models) review BEFORE any live rollout
      of each slice; leave a durable review artifact.
- [ ] 4.2 No platform-supplied-LLM path may survive slice 3 — verify against code.
