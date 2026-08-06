"""Binary founder recognition for external chat surfaces.

The platform capability is: *a user makes a custom agent, however they want* —
a Hermes agent, an OpenClaw agent, a coding agent, a customer-service agent, or
their own remix. Whatever shape it takes, the agent must know **for a fact**
whether it is talking to the verified founder, and when it is not it must be
*programmatically unable* to do founder-only things.

Deliberately binary. There is no role taxonomy here — no org chart, no
moderators, no customer tiers — because those differ per agent shape and none
of them is needed yet. A customer-service agent's founder is the business owner
and everyone else is a customer; a coding agent may have exactly one user. Same
recognition, different populations.

The output is a :class:`FounderGrant`: a sealed capability that only
:class:`FounderRecognizer` can mint. A caller cannot construct one, so "did the
platform recognise this sender as the founder?" is answerable by possession of
the object rather than by trusting a tier string that any layer could pass.

Everything is re-derived on every call. A grant is never cached, never stored,
and never outlives the turn it was minted for: revoking admin, rotating the
binding, or deleting the universe takes effect on the very next message.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from tinyassets.app_event_ingress import is_admissible_principal_event
from tinyassets.app_principal_mapping import (
    AppPrincipalMappingError,
    AppPrincipalMappingService,
)
from tinyassets.daemon_server import get_founder_home, list_universe_acl

logger = logging.getLogger(__name__)

_FOUNDER_GRANT_SEAL = object()


class FounderRecognitionError(PermissionError):
    """Recognition failed closed. Never raised to distinguish *why*."""


@dataclass(frozen=True, init=False)
class FounderGrant:
    """Proof that this exact turn is with the verified founder.

    Possession is the authority. The constructor refuses to build one without
    the recognizer's seal, so no caller — including a compromised transport —
    can forge founder capability by constructing the type it expects.

    ``_seal`` is deliberately NOT a dataclass field. As one it was assignable
    by :func:`dataclasses.replace`, which passes every field back to the
    constructor: a cross-family review turned a legitimate grant into one for
    *another universe* — ``replace(grant, universe_id='u2')`` — and it still
    passed :func:`is_founder_grant`. Off the field list, ``replace`` cannot
    supply the seal and fails instead.
    """

    universe_id: str
    subject_id: str
    agent_binding_id: str
    binding_revision: int
    mapping_generation: int
    provider: str
    workspace_id: str
    external_sender_id: str

    def __init__(
        self,
        *,
        universe_id: str,
        subject_id: str,
        agent_binding_id: str,
        binding_revision: int,
        mapping_generation: int,
        provider: str,
        workspace_id: str,
        external_sender_id: str,
        _seal: object,
    ) -> None:
        if _seal is not _FOUNDER_GRANT_SEAL:
            raise TypeError("FounderGrant may only be minted by FounderRecognizer")
        object.__setattr__(self, "universe_id", universe_id)
        object.__setattr__(self, "subject_id", subject_id)
        object.__setattr__(self, "agent_binding_id", agent_binding_id)
        object.__setattr__(self, "binding_revision", binding_revision)
        object.__setattr__(self, "mapping_generation", mapping_generation)
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "workspace_id", workspace_id)
        object.__setattr__(self, "external_sender_id", external_sender_id)
        object.__setattr__(self, "_seal", _seal)


def is_founder_grant(value: object) -> bool:
    """Return whether ``value`` carries this process's recognizer seal.

    ``type(...) is`` rather than ``isinstance``: a subclass is a caller-defined
    type, and inheriting the check is not the same as passing it.
    """

    return (
        type(value) is FounderGrant
        and getattr(value, "_seal", None) is _FOUNDER_GRANT_SEAL
    )


class FounderRecognizer:
    """Re-derive founder authority from current server state, every turn."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        mapping: AppPrincipalMappingService | None = None,
    ) -> None:
        self.base_path = Path(base_path)
        self.mapping = mapping or AppPrincipalMappingService(self.base_path)

    def recognize(self, event: object) -> FounderGrant | None:
        """Return a grant, or ``None`` for every other sender.

        ``None`` is the answer for a stranger, a revoked founder, a rotated
        binding and a malformed event alike. The caller's job is to treat the
        absence of a grant as "not the founder" — never to inspect why, and
        never to fall back to a tier of its own choosing.
        """
        try:
            return self._recognize(event)
        except (AppPrincipalMappingError, OSError, TypeError, ValueError) as exc:
            logger.debug("founder recognition failed closed (%s)", type(exc).__name__)
            return None

    def _recognize(self, event: object) -> FounderGrant | None:
        if not is_admissible_principal_event(event):
            return None

        # A founder installed this app in their own workspace, so a sender
        # whose home workspace is not the installation's cannot be that
        # founder. This closes Slack Connect: a guest from another workspace
        # reaching a shared channel is structurally ineligible, independent of
        # whether their user id happens to collide with the founder's.
        actor_team = getattr(event, "actor_team_id", "") or event.team_id
        if actor_team != event.team_id:
            return None

        record = self.mapping.resolve(event)

        # `resolve` already re-derived: founder home, this subject's single
        # admin row, binding `configured`, and matching revision. Two checks
        # remain, both of which it cannot make.

        # Founder cardinality. `resolve` asserts that *this subject* holds an
        # admin row and that this universe is their founder home; it does not
        # assert that nobody ELSE also calls it home. Two subjects could, and
        # "the verified founder" would stop being a single answerable fact.
        #
        # The test is deliberately NOT "exactly one admin". A cross-family
        # review pointed out that would lock the real founder out the moment
        # they add a co-admin — an availability bug, and a co-admin is not a
        # rival claim to being the founder. What must be unique is the set of
        # admins who call this universe their founder home.
        claimants = {
            actor
            for row in list_universe_acl(self.base_path, universe_id=record.universe_id)
            if row.get("permission") == "admin"
            and (actor := row.get("actor_id"))
            and get_founder_home(self.base_path, actor) == record.universe_id
        }
        if claimants != {record.subject_id}:
            return None

        # The universe directory must exist. A mapping can outlive the thing it
        # points at, and every founder-only capability downstream writes into
        # this directory.
        if not (self.base_path / record.universe_id).is_dir():
            return None

        return FounderGrant(
            universe_id=record.universe_id,
            subject_id=record.subject_id,
            agent_binding_id=record.agent_binding_id,
            binding_revision=record.binding_revision,
            mapping_generation=record.mapping_generation,
            provider=event.provider,
            workspace_id=actor_team,
            external_sender_id=event.external_sender_id,
            _seal=_FOUNDER_GRANT_SEAL,
        )


__all__ = [
    "FounderGrant",
    "FounderRecognitionError",
    "FounderRecognizer",
    "is_founder_grant",
]
