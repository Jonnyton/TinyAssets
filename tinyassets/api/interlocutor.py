"""Interlocutor identity tiers — *who* the universe is talking to.

Companion to :mod:`tinyassets.api.visibility`, which answers the orthogonal
question *what may this reader read*. Neither substitutes for the other, and
neither is inferred from the other.

Contract source of truth:
``openspec/changes/archive/2026-08-26-reconcile-universe-personification-relay/implementation-notes.md``
§6.2 (the tier<->visibility reconciliation, discharged as task 6.2), discharging
the delta requirement *"Interlocutor identity binds to a tier before the universe
answers"*:

  * ``T0`` — no TinyAssets OAuth to the universe (anonymous). Identical to the
    "unauthenticated reader" principal of the ``universe-visibility`` capability;
    they denote the same caller.
  * ``T1`` — a durable host/OAuth subject that is not the universe's founder.
  * ``T2`` — a verified founder, evidenced by an ``admin`` ``universe_acl`` grant on
    *that* universe. A ``write`` grant is a collaborator, not the founder: it may
    change the universe's work without being handed the founder's private grounding.
    Tier is per-universe: the same subject is ``T2`` on their own universe and ``T1``
    on someone else's.

Four invariants, each with a test in ``tests/test_interlocutor_tier.py``:

  1. **Disclosure is an intersection.** :func:`disclosure_permits` is
     ``visibility_permits() AND tier-allowance``. It is **tighten-only**: it can
     never open a capability the visibility layer (legacy ``public_read`` gate
     AND the declared level) withholds.
  2. **Fail-closed agreement.** A non-founder turn against an *undeclared*
     universe is refused. This is not redundant with the visibility layer: a
     reader holding an explicit ACL grant satisfies ``visibility_permits`` even
     on an undeclared universe (``_reader_has_grant`` short-circuits), and the
     tier layer refuses that case anyway.
  3. **Separation of source.** The tier comes only from authenticated request
     state — :func:`resolve_interlocutor_tier` takes no message and cannot see
     one, so a caller's asserted role is structurally unable to influence it.
  4. **Founder path unchanged.** ``T2`` keeps founder-tier disclosure on their
     own universe; visibility levels bound *other* readers.

**The ceiling binds every tier, including the founder.** ``visibility_permits``
is consulted for ``T0``, ``T1`` and ``T2`` alike — there is deliberately no
founder short-circuit around it, so no tier can open a capability the visibility
layer withholds (``TestTightenOnly`` forces the layer closed and asserts every
tier stays closed). ``T2``'s only exemption is from the *declaration* rule in
item 2: a founder may talk to their own universe before the boot backfill has
declared it. That exemption cannot leak, because ``T2`` is defined by exactly the
``admin`` ``universe_acl`` row that makes ``visibility._reader_has_grant``
true — asserted by
``TestDisclosureIntersection::test_founder_tier_implies_visibility_permits``, which
also guards against the new ceiling accidentally locking the founder out of their
own universe.

The **founder-only conversation floor** stays the floor:
:func:`authorize_conversation_turn` refuses every non-founder tier, because no
non-founder conversation path exists yet (delta spec scenario "the founder-only
gate remains the floor until a visitor path exists"). This module binds the tier
and narrows assembly; it does not open a visitor path.
"""

from __future__ import annotations

from dataclasses import dataclass

from tinyassets.api import visibility

#: No TinyAssets OAuth to the universe — the anonymous reader.
T0 = "T0"
#: A durable host/OAuth subject that is not this universe's founder.
T1 = "T1"
#: A verified founder of this universe — an ``admin`` grant. A ``write``
#: grant is a collaborator and binds to T1 (Codex REJECT 2026-08-28).
T2 = "T2"

#: Every recognized tier, weakest first. An unrecognized tier fails loudly.
TIERS: tuple[str, ...] = (T0, T1, T2)

#: The founder-authority tier, named for callers that would otherwise hardcode
#: the string.
FOUNDER = T2

#: OKF grounding files whose content is the founder's own person-dossier. These
#: are withheld from every non-founder interlocutor regardless of how permissive
#: the universe's visibility level is: a universe may be fully public without its
#: founder's private description becoming public. The universe's own governed
#: learning path still writes ``founder.md`` freely — that is sole-writership,
#: not a disclosure grant (see the anti-collision requirement).
#:
#: ``orgchart.md`` joined 2026-08-29, in the same change that started reading it
#: back into the turn: it records who works with the founder — collaborators,
#: delegations, reporting lines — which is the founder's organisation, not the
#: universe's public face. Making it readable to the universe itself must not
#: make it readable to a visitor.
FOUNDER_PRIVATE_GROUNDING: frozenset[str] = frozenset(
    {"founder.md", "orgchart.md"}
)


@dataclass(frozen=True)
class Interlocutor:
    """The bound identity of the party a universe is answering."""

    tier: str
    actor_id: str
    universe_id: str

    @property
    def is_founder(self) -> bool:
        return self.tier == T2

    @property
    def is_anonymous(self) -> bool:
        return self.tier == T0


@dataclass(frozen=True)
class ConversationAuthorization:
    """Whether a conversation turn may proceed, and for whom."""

    interlocutor: Interlocutor
    permitted: bool
    refusal: str = ""


def _holds_admin_grant(universe_id: str, actor_id: str) -> bool:
    """Whether ``actor_id`` holds the ``admin`` grant on ``universe_id``.

    Deliberately not `universe_access_allows(..., write=True)`: that accepts write
    OR admin, and the whole point here is that those are different people once a
    universe has collaborators. Fail-closed on any storage error -- an unreadable ACL
    must not confer founder authority.
    """
    from tinyassets.api.permissions import _base_path
    from tinyassets.daemon_server import universe_access_permission

    uid = (universe_id or "").strip()
    aid = (actor_id or "").strip()
    if not uid or not aid:
        return False
    try:
        return universe_access_permission(
            _base_path(), universe_id=uid, actor_id=aid
        ) == "admin"
    except Exception:  # noqa: BLE001 -- fail closed, same as universe_owner_actor
        return False


#: Rank a tier for comparison. An unrecognized value ranks below ``T0``, so an
#: unknown string can only ever narrow.
def _rank(tier: str) -> int:
    try:
        return TIERS.index(tier)
    except ValueError:
        return -1


def clamp_tier(requested: str | None, *, resolved: str) -> str:
    """Return the WEAKER of a caller's requested tier and the resolved one.

    A tier is authority, so a caller may hand one down but never hand itself one
    up. Codex reproduced the escalation this closes (REJECT 2026-08-28): an actor
    holding only ``write`` resolved correctly to ``T1`` and then received founder
    grounding by calling the conversation sink with ``tier=T2`` directly. The
    resolver was right; the sink treated its own parameter as configuration.

    ``None`` means "no opinion" and yields the resolved tier. An unrecognized
    string ranks below ``T0`` and therefore narrows to itself — a caller passing
    nonsense gets less, never more.
    """
    if requested is None:
        return resolved
    return requested if _rank(requested) < _rank(resolved) else resolved


def resolve_interlocutor_tier(universe_id: str) -> Interlocutor:
    """Bind the current caller to a tier for ``universe_id``.

    Resolved **only** from authenticated request state. This function takes no
    message and has no way to read one, which is how the "tier is never taken
    from message content" scenario is guaranteed rather than merely intended.
    """
    from tinyassets.api import permissions

    uid = (universe_id or "").strip()
    actor = permissions.current_request_actor_id()
    if not actor or actor == "anonymous":
        return Interlocutor(tier=T0, actor_id="anonymous", universe_id=uid)
    # Founder authority is the ADMIN grant on THIS universe, not merely write.
    #
    # This used to accept write, and with exactly one founder the two were the same
    # set, so nothing showed. They diverge the moment a collaborator is granted write:
    # that collaborator became T2 and received founder-tier disclosure -- the
    # universe's private grounding -- and could persist learning into it.
    #
    # `admin` is already the canonical ownership signal elsewhere in the codebase:
    # `source_channel.universe_owner_actor` documents it as such and explicitly
    # excludes read/write holders. Two different notions of "owner" in one codebase is
    # the actual defect; this makes them agree (Codex, 2026-08-28).
    if uid and _holds_admin_grant(uid, actor):
        return Interlocutor(tier=T2, actor_id=actor, universe_id=uid)
    return Interlocutor(tier=T1, actor_id=actor, universe_id=uid)


def disclosure_permits(universe_id: str, capability: str, *, tier: str) -> bool:
    """Whether ``tier`` may be disclosed ``capability`` on ``universe_id``.

    The intersection of tier authority and declared visibility (contract item 1),
    tighten-only by construction: the visibility layer is the ceiling for every
    non-founder tier, and ``T2`` is proven to imply it (see module docstring).

    Fails loudly on an unknown tier or capability rather than guessing — a typo
    must not silently resolve to "permitted".
    """
    if tier not in TIERS:
        raise ValueError(f"unknown interlocutor tier: {tier!r}; expected one of {TIERS}")
    if capability not in visibility.CAPABILITIES:
        raise ValueError(
            f"unknown visibility capability: {capability!r}; expected one of "
            f"{visibility.CAPABILITIES}"
        )

    # Ceiling: the landed visibility layer (legacy public_read gate AND the
    # declared level), applied to EVERY tier including the founder. Nothing below
    # widens it; this layer only ever narrows.
    if not visibility.visibility_permits(universe_id, capability):
        return False
    if tier == T2:
        return True
    # Contract item 2 — fail closed on an undeclared universe for any
    # non-founder tier, even when an ACL grant satisfied the ceiling above.
    return visibility.is_declared(universe_id)


def permitted_grounding_files(
    universe_id: str, candidates: tuple[str, ...], *, tier: str
) -> tuple[str, ...]:
    """The subset of OKF grounding files disclosable to ``tier``.

    This is the *authorization-precedes-voice* filter: excluded content never
    enters the assembled system prompt, so no instruction-following is relied on
    to withhold it.
    """
    if not disclosure_permits(universe_id, "read_content", tier=tier):
        return ()
    if tier == T2:
        return tuple(candidates)
    return tuple(name for name in candidates if name not in FOUNDER_PRIVATE_GROUNDING)


def authorize_conversation_turn(universe_id: str) -> ConversationAuthorization:
    """Bind the interlocutor and apply the founder-only conversation floor.

    Composes with — never replaces — the landed `converse` gate. Because no
    non-founder conversation path exists, every non-founder tier is refused here;
    when a visitor path ships, this is the single place that decision changes.
    """
    who = resolve_interlocutor_tier(universe_id)
    if who.is_founder:
        return ConversationAuthorization(interlocutor=who, permitted=True)
    return ConversationAuthorization(
        interlocutor=who,
        permitted=False,
        refusal="conversation_founder_only",
    )
