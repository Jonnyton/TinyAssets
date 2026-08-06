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
from dataclasses import dataclass, replace
from pathlib import Path

from tinyassets.app_event_ingress import is_admissible_principal_event
from tinyassets.app_principal_mapping import (
    AppPrincipalMappingError,
    AppPrincipalMappingService,
    AppPrincipalTarget,
)

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

    def recognize(
        self,
        event: object,
        *,
        universe_id: str = "",
        agent_binding_id: str = "",
        binding_revision: int = 0,
    ) -> FounderGrant | None:
        """Return a grant, or ``None`` for every other sender.

        ``None`` is the answer for a stranger, a revoked founder, a rotated
        binding and a malformed event alike. The caller's job is to treat the
        absence of a grant as "not the founder" — never to inspect why, and
        never to fall back to a tier of its own choosing.

        The optional universe triple asks "is this sender the founder of *that*
        universe", which is what channel routing needs: a message can be routed
        to a universe other than the one this sender's mapping was created
        against, and ownership is a per-universe fact. Omitted, the question is
        asked about the mapping's own universe.
        """
        try:
            return self._recognize(
                event,
                universe_id=universe_id,
                agent_binding_id=agent_binding_id,
                binding_revision=binding_revision,
            )
        except (AppPrincipalMappingError, OSError, TypeError, ValueError) as exc:
            logger.debug("founder recognition failed closed (%s)", type(exc).__name__)
            return None

    def _recognize(
        self,
        event: object,
        *,
        universe_id: str = "",
        agent_binding_id: str = "",
        binding_revision: int = 0,
    ) -> FounderGrant | None:
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

        # `resolve` already re-derived this subject's admin row on the MAPPED
        # universe, the binding being `configured`, and a matching revision.
        #
        # When routing sent the message somewhere else, that proves nothing
        # about where it actually landed: ownership is per-universe, so it is
        # re-derived from scratch against the routed universe. Only the
        # *identity* — which subject this sender is — carries over.
        universe = universe_id or record.universe_id
        agent_binding = agent_binding_id or record.agent_binding_id
        revision = binding_revision or record.binding_revision
        if universe != record.universe_id:
            current = self.mapping.current_founder_binding(
                AppPrincipalTarget(
                    subject_id=record.subject_id,
                    universe_id=universe,
                    agent_binding_id=agent_binding,
                    binding_revision=revision,
                )
            )
            if current is None:
                return None
            record = replace(
                record,
                universe_id=current.universe_id,
                agent_binding_id=current.agent_binding_id,
                binding_revision=current.binding_revision,
                membership_generation=current.membership_generation,
            )

        # No cardinality rule, deliberately.
        #
        # Two earlier attempts were both wrong, in opposite directions. "The
        # universe has exactly one admin" locked the real founder out the
        # moment they added a co-admin. Replacing it with "exactly one admin
        # whose founder HOME is this universe" then broke multi-universe: a
        # user with work, personal and hobby universes has `founder_home`
        # pointing at just one of them, so on the other two the claimant set is
        # empty and no grant could ever mint.
        #
        # The question that actually needs answering is per-universe and has a
        # per-universe answer: does this subject own THIS universe? That is the
        # admin ACL row `resolve` already re-derived. Co-owners are then both
        # founders of that universe, which is a coherent product answer and the
        # host's to change later; what matters is that a NON-owner is
        # structurally excluded, and that property does not need uniqueness.

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
