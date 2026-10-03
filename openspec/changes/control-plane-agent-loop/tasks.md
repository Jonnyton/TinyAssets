## 1. The loop (PR 1)

- [x] 1.1 Thin turns run where turns run today; the shared loop is 2.1
      (`design.md` decision 1).
- [x] 1.2 Box tools by `op_id` over a handle bound at turn start; lost replies
      asked with the same `op_id`; unknown holds; ordered writes; bounded,
      owned cancel/timeout kill in the box.
- [x] 1.3 Owner reads `history`/`activity` in the loop, read-only, never
      forwarded to the box.
- [x] 1.4 Tool router + coordinator hook (`open_tools`, `op_id`); journal
      unchanged; per-account owner setting `agent_loop=thin` (default `engine`).
- [x] 1.5 Memory per waiting turn: 500 concurrent against a mock SSE server
      (`design.md` § Measurement).

## 2. Production path (PR 2, after S4's driver, S6's streaming contract, S8a)

- [x] 2.1 Shape first: three REJECT rounds on PR 1 are a shape signal. Before
      adding to it, re-derive the concurrency shape (one asyncio task per
      turn, box operations as awaitables on an async `BoxProvider` client)
      and delete the thread/slot/cancel layering it makes unnecessary.
- [ ] 2.2 One shared loop: task-aware, non-blocking provider-assignment
      admission; journal writes off the loop; then turns as tasks on it.
- [ ] 2.3 Adopt `tinyassets.boxes` (#4274) in place of `BoxExec` (DONE on the
      2.1 branch: slice collection, owned boundary, contract tests against
      `LocalBoxProvider`); configure a production driver in the daemon once a
      kernel-isolated one exists (the local driver refuses without
      `allow_unisolated`). Its shapes differ from
      PR 1's assumptions:
      - events are `kind` "output"|"exit", merged in order;
      - `offset` is the chunk START, so resume from `offset + len(data)`;
      - exit carries `exit_code` and `killed`;
      - `stream(timeout=)` ends without an exit event (resume, not done);
      - the refusal class is `tinyassets.boxes.BoxOperationRefused`;
      - the root is the constant `BOX_ROOT`, with no `handle.root`;
      - `ensure_awake` comes before exec;
      - `write(mode="cas", expect_generation=)` is an atomic alternative to
        the flock script.
      The image ships `flock` (design Risks).
- [ ] 2.4 Model stream to the app over the S6 contract
      (`openspec/changes/broker-streaming-contract`) -> loop -> the
      frontend's SSE response, cancellation propagated both ways.
- [ ] 2.5 Owner generation from `control_plane.lease.current_owner_lease()
      .generation`, passed through to the journal unchanged (S8a wires the
      fence inside `AgentTurnJournal`).
- [ ] 2.6 Retire the tool jail and the engine route's four tools for HTTP
      turns on the thin loop (HTTP model calls never used the provider jail);
      keep both for CLI paths.
- [ ] 2.7 Addressed agents (#4287): the owner read `history` takes its
      session from `addressed_agents.memory_session(owner, agent_id)`, never a
      hardcoded `principal:<owner>`. The turn carries `agent_id` the way
      `converse(addressed_agent=)` does, and steering keeps reading the
      session from the turn's config.
- [ ] 2.8 CLI-in-box only for command adapters and file-OAuth CLIs; Claude
      subscription serving stays owner-only (D6).

## 3. Rollout (the switch is temporary)

- [ ] 3.1 A fresh cross-family review of the whole thin path, including the
      two post-cap fixes of PR 1 (c6418af3), gates turning the switch on in
      production.
- [ ] 3.2 The harness owner flips the founder's account first through
      `scripts/set_agent_loop.py --owner <owner_user_id> --loop thin` on the
      production host, targeting the production data root. Verify by reading
      the owner's stored setting back from that root before claiming it is on;
      other accounts follow once proven.
- [ ] 3.3 Live proof: a rendered conversation through the live app with the
      switch on, plus `mcp_public_canary.py`.
- [ ] 3.4 Remove the per-account setting: once proven, the thin loop is the
      only path for HTTP turns, for every account (one code path); delete the
      `account_agent_loop` store, maintainer script, and engine path code that
      only the old HTTP path used.
- [ ] 3.5 Spec sync to `openspec/specs/control-plane-agent-loop/` and archive.
