# Codex cross-family review — write grant is not the founder (#2632)

Three rounds, 2026-08-28, `codex exec` on Codex's own budget. Verdict trail:
**REJECT → REJECT → REJECT (test-gap on correct code)**, then a single mechanical
re-verification of round 3's own reproduction.

---

## Round 1

VERDICT: REJECT

The admin comparison itself is correct, and the public MCP path currently binds it correctly. But T2 remains caller-selectable at the sensitive sink, and the fail-closed test does not exercise the real entrypoint.

1. DISAGREE_EVIDENCE — T2 remains routable around in-process.

`universe_intelligence.converse` accepts a caller-provided `tier` at [tinyassets/universe_intelligence.py:796](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/universe_intelligence.py:796), and any non-`None` value bypasses resolution at [tinyassets/universe_intelligence.py:833](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/universe_intelligence.py:833). That asserted value controls founder grounding and learning at lines [877](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/universe_intelligence.py:877) and [938](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/universe_intelligence.py:938).

I reproduced:

```text
{'resolved': 'T1', 'explicit_t2_disclosed_founder_fact': True}
```

The actor held only `write`, correctly resolved as T1, then received founder grounding through `converse(..., tier=T2)`.

The current public MCP caller is safe: it resolves authorization at [tinyassets/universe_server.py:1757](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/universe_server.py:1757) and passes the resulting tier at [tinyassets/universe_server.py:1791](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/universe_server.py:1791). I found no current remote transport route that lets a write holder supply `tier`. Nevertheless, the authority-sensitive sink still treats T2 as configuration, exactly the direct-caller class earlier tests treat as security-relevant.

Required adaptation: resolve authority inside the sink, or replace the string with unforgeable server-issued authority evidence.

2. AGREE — the new helper itself fails closed.

At [tinyassets/api/interlocutor.py:126](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/api/interlocutor.py:126):

- Empty/whitespace universe or actor returns `False`.
- Unknown/corrupt permission levels fail the exact `== "admin"` comparison.
- Storage exceptions return `False`.
- Empty or anonymous request actors become T0 at [tinyassets/api/interlocutor.py:148](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/api/interlocutor.py:148).

Authenticated identity is derived from the bearer-backed request context; environment fallback is explicitly absent at [tinyassets/api/permissions.py:238](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/api/permissions.py:238).

3. DISAGREE_EVIDENCE — the real entrypoint does not handle ACL-store errors as claimed.

Before reaching the protected `authorize_conversation_turn` block, public `converse` calls `universe_access_allows` at [tinyassets/universe_server.py:1738](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/universe_server.py:1738). That helper performs an uncaught ACL read at [tinyassets/api/permissions.py:317](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/api/permissions.py:317).

I patched the actual grant-store function to raise `OSError`; `universe_server.converse` propagated:

```text
{'raised': 'OSError', 'message': 'acl down'}
```

Authority fails closed, but the public call does not return its promised honest error envelope. The new assertion at [tests/test_interlocutor_tier.py:627](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tests/test_interlocutor_tier.py:627) only invokes `_holds_admin_grant` directly. The older entrypoint test also patches `authorize_conversation_turn` rather than the store at [tests/test_interlocutor_tier.py:537](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tests/test_interlocutor_tier.py:537), so it misses this ordering defect.

4. DISAGREE_EVIDENCE — mutation strength is partial.

For these mutations—delete the resolver gate at lines 162–163, invert the helper comparison, or weaken it to accept `write`—the new assertions behave as follows:

| Assertion | Delete resolver gate | Invert comparison | Accept write/admin |
|---|---:|---:|---:|
| Write collaborator is T1, line 603 | stays green | red | red |
| Admin owner is T2, line 616 | red | red | stays green |
| Store error returns false, line 627 | stays green | stays green | stays green |
| Source contains `== "admin"`, line 639 | stays green | red | red |
| Helper omits permissive helper, line 644 | stays green | stays green | stays green |

The last two are source-shape checks, not enforcement checks. Reintroducing `permissions.universe_access_allows(uid, write=True)` directly in the resolver while leaving `_holds_admin_grant` dead would leave assertions 627, 639, and 644 green. Routing around the resolver through `converse(..., tier=T2)` leaves all five green.

An end-to-end write-collaborator test against `universe_server.converse`, plus a direct-sink test, is needed.

5. AGREE — I found no legitimate-caller regression.

The only production resolution paths found are `authorize_conversation_turn` at [tinyassets/api/interlocutor.py:220](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/api/interlocutor.py:220) and the `tier=None` fallback in `universe_intelligence` at line 834. New universe creation has granted founders `admin` since that mechanism was introduced, at [tinyassets/api/universe.py:5807](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/api/universe.py:5807).

No migration or seeding caller invokes the resolver. The “23 internal callers” note belongs to the separate universe-creation gate, not this tier resolver.

6. AGREE — no separate public self-grant/header/env escalation was found.

- `grant_universe_access` is an ambient internal primitive with no caller authorization at [tinyassets/daemon_server.py:4640](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/daemon_server.py:4640), but no public ACL-mutation route calls it.
- Its sole production use grants the authenticated creator admin on a new universe; existing IDs are rejected at [tinyassets/api/universe.py:5729](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/api/universe.py:5729).
- MCP identity comes from a validated bearer token, not an actor header, at [tinyassets/auth/middleware.py:768](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/auth/middleware.py:768).
- Synthetic `Identity` contexts are possible for trusted in-process callers, but not through the public transport.
- The surviving privilege route is the explicit `tier=T2` sink override described above.

7. DISAGREE_CONCERN — requirement truth remains contradictory.

The as-built connector spec still says `converse` accepts write or admin at [openspec/specs/live-mcp-connector-surface/spec.md:81](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/openspec/specs/live-mcp-connector-surface/spec.md:81). The module also still describes T2 as “write/admin” at [tinyassets/api/interlocutor.py:47](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/api/interlocutor.py:47) and [tinyassets/api/interlocutor.py:70](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/api/interlocutor.py:70).

The exact old concern also remains open. Once enforcement is closed at the sink, delete `docs/concerns/2026-08-05-write-acl-grants-founder-tier.md` and its README row as required by AGENTS.md.

Verification: 2026-08-28, Windows checkout; `python -m pytest tests/test_interlocutor_tier.py -q` → 45 passed. The opposite-family peer agreed the admin comparison is correct and found no public self-grant surface, but did not invalidate either direct reproduction above.

---

## Round 2

VERDICT: REJECT

1. Sink escalation

AGREE — the original reproduction is closed.

`{'resolved': 'T1', 'founder_fact_disclosed': False, 'provider_calls': 1}`

The independently resolved/clamped `bound_tier` governs prompt assembly, history, engine privileges, and persistence. Neither `agent_binding_id`, `actor_id`, nor `conversation_history` can raise it. [universe_intelligence.py](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/universe_intelligence.py:842)

No exposed alternate caller of `_build_persona_system_prompt` was found.

2. Store-error envelope

DISAGREE_EVIDENCE — the patched ACL read is fixed, but another pre-envelope store read still escapes.

Persistent grant-store failure now returns:

```python
{"error": "Only this universe's founder can talk with it.",
 "auth_scope_required": True}
```

The first, second, and third ACL permission reads did not escape. However, omitting `graph_id` calls `ensure_founder_home` before the new `try`: [universe_server.py](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/universe_server.py:1728). Its initial `get_founder_home` read is unwrapped: [first_contact.py](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/api/first_contact.py:43).

Fault injection reproduced:

```python
{'escaped': 'OSError', 'message': 'home store unavailable'}
```

3. Mutation strength

DISAGREE_EVIDENCE — `clamp_tier` is genuinely reached and used, but the assertions do not prove a general ceiling.

This plausible exact-CVE-only mutant passed all 52 interlocutor tests:

```python
if requested is None:
    return resolved
if requested == T2 and resolved == T1:
    return T1
return requested
```

Under it, anonymous `T0` calling a public universe with `tier=T2` disclosed the founder fact:

```python
{'resolved': 'T0', 'founder_fact_disclosed': True}
```

The source-shape assertion is also individually decorative: a dead `clamp_tier(...)` call plus an alternate raw-tier assignment would satisfy it. Add an exhaustive known-tier pair matrix and, critically, an end-to-end `T0 + requested T2` disclosure test.

Fresh checks

- AGREE — the actual `_rank`/`clamp_tier` implementation behaves safely for every pair. Equal recognized tiers return that tier; both unknown returns the resolved unknown; any known tier loses to an unknown resolved tier; `None` preserves resolved authority. [interlocutor.py](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/api/interlocutor.py:139)
- DISAGREE_EVIDENCE — the change leaves existing internal-contract regressions. Five targeted `test_universe_intelligence.py` tests produced four failures because direct founder calls now resolve anonymous and lose persistence/history. No production caller beyond `universe_server` was found, but the tests must be updated to establish authenticated founder state.
- DISAGREE_CONCERN — the spec’s core access/authority distinction matches the code: write/admin passes the access check while only admin resolves T2. But its claim that a write collaborator’s turn is relayed is misleading because `authorize_conversation_turn` still rejects every T1 before relay. [spec.md](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/openspec/specs/live-mcp-connector-surface/spec.md:81), [interlocutor.py](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/api/interlocutor.py:241)

Verification: 2026-08-28, local Windows checkout at `d4c87eee`. Focused tier suite: `52 passed`; targeted internal-caller check: `4 failed, 1 passed`. No files changed.

---

## Round 3

VERDICT: REJECT

1. **AGREE — sink escalation remains closed.** Current `clamp_tier` usage correctly resolves authenticated authority before narrowing.

2. **AGREE — store-error path is closed.** Universe resolution, ACL access, and authorization are enveloped at [universe_server.py](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/universe_server.py:1734), line 1755, and line 1780. I found no fourth pre-relay store read. The corrected real-message test reaches `get_founder_home`.

3. **DISAGREE_EVIDENCE — the suite still proves cases, not the sink invariant.** Insert after [universe_intelligence.py:842](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/universe_intelligence.py:842):

```diff
     bound_tier = interlocutor.clamp_tier(
         tier, resolved=interlocutor.resolve_interlocutor_tier(uid).tier
     )
+    if actor_id and tier == interlocutor.T1 and bound_tier == interlocutor.T0:
+        bound_tier = interlocutor.T2
```

Reproduction:

- Unchanged focused suite: **93 passed**.
- Exercise the existing anonymous E2E call with `actor_id="forged-founder", tier=T1`: it fails because `FOUNDER_FACT` appears in the assembled system prompt.
- This is a post-clamp widening through another existing caller-controlled sink argument—not a test-literal special case.

4. **AGREE — `_become_founder` is honest.** It writes a real `admin` ACL row, installs an authenticated identity through middleware, and does not stub the resolver, access check, authorization, or sink. The only production caller is [universe_server.py:1815](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/tinyassets/universe_server.py:1815), plus its packaging mirror. No background, proactive, or engine-MCP caller invokes this sink.

5. **AGREE — spec wording is accurate.** Write/admin passes `universe_access_allows`; write-only resolves T1 and is refused by `authorize_conversation_turn` before `_converse_impl` is reached.

Verification on 2026-08-28, Windows:

- Baseline: `93 passed`
- Restored checkout: `29 passed` covering both store-failure tests and all 27 intelligence tests
- `git diff --check`: clean

Per the three-round cap, I recorded the unresolved gate failure for the founder in [2026-08-28-founder-tier-sink-mutation-gap.md](C:/Users/Jonathan/Projects/wf-founder-tier-is-admin/docs/concerns/2026-08-28-founder-tier-sink-mutation-gap.md). No fourth review.

---

## Re-verification (not a fourth round)

The three-round cap was reached. Round 3's REJECT rested on one mechanical claim —
that its post-clamp insert stayed green. Codex was asked only whether that is still
true at `e7b2f45b`, explicitly not to review anything:

```
1. `1 failed, 124 passed in 23.41s` — `TestDisclosureMatchesResolutionForEveryCallerInput::test_founder_grounding_appears_iff_resolution_says_t2[anon-forged-founder-T1]`
2. No.
3. Yes—the gap is closed and the concern was correctly deleted.

VERDICT: APPROVE
```
