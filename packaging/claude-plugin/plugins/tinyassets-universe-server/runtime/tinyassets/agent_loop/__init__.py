"""The thin agent loop: model turns in the execution owner, tools in the box.

Target architecture D6 (``openspec/changes/target-architecture/design.md``),
slice S7; change ``control-plane-agent-loop``.

A turn that speaks a standard HTTP model protocol is a coroutine in ONE
long-lived process, the execution owner (:mod:`.execution_owner`), not a
subprocess. The model call goes through the existing credential broker
(``ApiKeyHttpProvider`` -> ``resolve_exact_scoped_proxy``), so no model
credential is ever in the loop. The loop never executes model output: it
parses tool-call JSON and routes each call by NAME to exactly one place
(:mod:`.tool_session`):

* the four box tools (``read``/``write``/``edit``/``bash``) go to the turn's
  command-center box over a :class:`BoxHandle` bound once at turn start, each
  call carrying an ``op_id`` (:mod:`.box_tools`);
* the owner-door reads (``history``, ``activity``) are answered by the loop
  itself, read-only, and never reach the box (:mod:`.owner_reads`);
* every other served tool keeps its existing engine route, where its own gates
  (owner rules, auto-review, effect consent) already sit.

The per-round journal is the existing :class:`AgentTurnJournal`, written only
by the execution owner. An operation whose outcome is unknown is recorded as
unknown and the turn HOLDS; nothing replays.
"""
