"""Proof-carrying values produced only after an authority mechanism verifies.

The M1 signature verifier will share this wrapper when its trust-root work lands.
M2 and M3 verifiers use the package-private mint seam only after completing
their own mechanism-specific checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar, final

T = TypeVar("T")


def _verified_contract():
    construction_token = object()

    @final
    @dataclass(frozen=True, init=False)
    class Verified(Generic[T]):
        """Frozen proof wrapper minted after an authority mechanism verifies."""

        payload: T

        def __init__(self, payload: T, *, _token: object | None = None) -> None:
            if _token is not construction_token:
                raise TypeError(
                    "Verified can only be constructed by an authority verifier"
                )
            object.__setattr__(self, "payload", payload)

        def __init_subclass__(cls, **kwargs: Any) -> None:
            raise TypeError("Verified cannot be subclassed")

        def __copy__(self):
            raise TypeError("Verified proof wrappers cannot be copied")

        def __deepcopy__(self, memo: dict[int, Any]):
            raise TypeError("Verified proof wrappers cannot be copied")

        def __reduce__(self):
            raise TypeError("Verified proof wrappers cannot be pickled")

        def __reduce_ex__(self, protocol: int):
            raise TypeError("Verified proof wrappers cannot be pickled")

    def verified_after_mechanism_check(payload: T) -> Verified[T]:
        """Package-private mint seam for a completed authority check."""
        return Verified(payload, _token=construction_token)

    return Verified, verified_after_mechanism_check


Verified, _verified_after_mechanism_check = _verified_contract()


__all__ = ["Verified"]
