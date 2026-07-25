"""Sealed verifier-neutral evidence shared by M1, M2, and M3 adapters.

The package bootstrap transfers each mechanism capability exactly once into a
reviewed adapter closure.  Importing this module after package initialization
therefore exposes no callable that can mint arbitrary evidence.

Authenticity and issuer identity live only in a closure-held weak identity
registry, never in object slots that a caller could extract and transplant.
The same entry snapshots every authority-relevant field and the exact immutable
value object, so reflective replacement of a frozen object's public slots fails
at the sink.  M1 evidence is additionally bound to the exact verifier instance
that issued it, so evidence from a caller-created trust root is not accepted by
a different root.  These controls remain misuse prevention rather than an
in-process sandbox: arbitrary reflective Python already executing inside the
trusted package can inspect closures or mutate interpreter state.
"""

from __future__ import annotations

import re
import weakref
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from typing import Any, Generic, Literal, TypeVar, final

T = TypeVar("T")
VerificationMechanism = Literal["m1", "m2", "m3"]

_MAX_JSON_INTEGER = (1 << 53) - 1
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _is_deeply_immutable(value: object, seen: set[int] | None = None) -> bool:
    """Return whether a value has no mutable reachable state.

    Mappings are rejected even when wrapped by ``MappingProxyType`` because a
    proxy retains a mutable backing dictionary.  Reviewed adapters currently
    mint frozen dataclass values, tuples, and scalar JSON values only.
    """

    if value is None or type(value) in (bool, int, float, str, bytes):
        return True
    if isinstance(value, Mapping):
        return False
    if seen is None:
        seen = set()
    identity = id(value)
    if identity in seen:
        return True
    seen.add(identity)
    if type(value) in (tuple, frozenset):
        return all(_is_deeply_immutable(item, seen) for item in value)
    if is_dataclass(value):
        parameters = getattr(type(value), "__dataclass_params__", None)
        return bool(parameters and parameters.frozen) and all(
            _is_deeply_immutable(getattr(value, item.name), seen) for item in fields(value)
        )
    return False


def _build_verified_contract():
    @dataclass(frozen=True, slots=True)
    class _Registration:
        reference: weakref.ReferenceType[Any]
        issuer: object
        value: object
        mechanism: VerificationMechanism
        domain: str
        evidence_digest: str
        verifier_id: str
        verified_at: int

    default_issuer = object()
    registry: dict[int, _Registration] = {}
    bootstrap_taken = False

    @final
    @dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
    class Verified(Generic[T]):
        """Immutable evidence authenticated by closure-held object identity."""

        value: T
        mechanism: VerificationMechanism
        domain: str
        evidence_digest: str
        verifier_id: str
        verified_at: int

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise TypeError("Verified evidence can only be constructed after verification")

        def __init_subclass__(cls, **kwargs: Any) -> None:
            raise TypeError("Verified cannot be subclassed")

        def __copy__(self):
            raise TypeError("Verified evidence cannot be copied")

        def __deepcopy__(self, memo: dict[int, Any]):
            raise TypeError("Verified evidence cannot be copied")

        def __reduce__(self):
            raise TypeError("Verified evidence cannot be pickled")

        def __reduce_ex__(self, protocol: int):
            raise TypeError("Verified evidence cannot be pickled")

    def require_authentic(
        evidence: Verified[T],
        *,
        expected_mechanism: VerificationMechanism | None = None,
        expected_issuer: object | None = None,
    ) -> Verified[T]:
        if type(evidence) is not Verified:
            raise TypeError("Verified evidence has no authentic package provenance")
        registered = registry.get(id(evidence))
        # Exact referent identity makes a stale entry fail closed even if an
        # interpreter reuses the dead object's integer id.
        if registered is None or registered.reference() is not evidence:
            raise TypeError("Verified evidence has no authentic package provenance")
        try:
            current_value = evidence.value
            current_metadata = (
                evidence.mechanism,
                evidence.domain,
                evidence.evidence_digest,
                evidence.verifier_id,
                evidence.verified_at,
            )
        except AttributeError as exc:
            raise TypeError("Verified evidence no longer matches its authority snapshot") from exc
        expected_metadata = (
            registered.mechanism,
            registered.domain,
            registered.evidence_digest,
            registered.verifier_id,
            registered.verified_at,
        )
        metadata_matches = all(
            type(current) is type(expected) and current == expected
            for current, expected in zip(
                current_metadata,
                expected_metadata,
                strict=True,
            )
        )
        if current_value is not registered.value or not metadata_matches:
            raise TypeError("Verified evidence no longer matches its authority snapshot")
        if expected_issuer is not None:
            issuer = registered.issuer
            if issuer is not expected_issuer:
                raise TypeError("Verified evidence issuer does not match the authority sink")
        if expected_mechanism is not None and evidence.mechanism != expected_mechanism:
            raise TypeError("Verified evidence mechanism does not match the sink")
        return evidence

    def create_mechanism_minter(
        mechanism: VerificationMechanism,
    ):
        def mechanism_minter(
            value: T,
            *,
            domain: str,
            evidence_digest: str,
            verifier_id: str,
            verified_at: int,
            issuer: object | None = None,
        ) -> Verified[T]:
            if type(domain) is not str or not domain or "\0" in domain:
                raise TypeError("verification domain must be a nonempty canonical string")
            if type(evidence_digest) is not str or _SHA256_RE.fullmatch(evidence_digest) is None:
                raise TypeError("evidence_digest must be a lowercase SHA-256 digest")
            if type(verifier_id) is not str or not verifier_id.strip():
                raise TypeError("verifier_id must be a nonempty string")
            if type(verified_at) is not int or verified_at < 0 or verified_at > _MAX_JSON_INTEGER:
                raise TypeError("verified_at must be a bounded non-negative integer")
            if not _is_deeply_immutable(value):
                raise TypeError("Verified values must be deeply immutable")

            instance = object.__new__(Verified)
            object.__setattr__(instance, "value", value)
            object.__setattr__(instance, "mechanism", mechanism)
            object.__setattr__(instance, "domain", domain)
            object.__setattr__(instance, "evidence_digest", evidence_digest)
            object.__setattr__(instance, "verifier_id", verifier_id)
            object.__setattr__(instance, "verified_at", verified_at)

            identity = id(instance)

            def discard(reference: weakref.ReferenceType[Any]) -> None:
                registered = registry.get(identity)
                # A delayed callback must not erase a newer registration whose
                # object received the same recycled integer id.
                if registered is not None and registered.reference is reference:
                    del registry[identity]

            reference = weakref.ref(instance, discard)
            registry[identity] = _Registration(
                reference=reference,
                issuer=default_issuer if issuer is None else issuer,
                value=value,
                mechanism=mechanism,
                domain=domain,
                evidence_digest=evidence_digest,
                verifier_id=verifier_id,
                verified_at=verified_at,
            )
            return instance

        return mechanism_minter

    mechanism_capabilities = (
        create_mechanism_minter("m1"),
        create_mechanism_minter("m2"),
        create_mechanism_minter("m3"),
    )

    def take_bootstrap_capabilities():
        nonlocal bootstrap_taken
        if bootstrap_taken:
            raise RuntimeError("Verified mechanism capabilities were already transferred")
        bootstrap_taken = True
        return (*mechanism_capabilities, require_authentic)

    return Verified, require_authentic, take_bootstrap_capabilities


Verified, _require_authentic_verified, _take_bootstrap_capabilities = _build_verified_contract()
del _build_verified_contract


__all__ = ["Verified", "VerificationMechanism"]
