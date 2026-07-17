"""Non-observable secret containers.

:class:`SecretBytes` and :class:`SecretLease` hold raw credential material that
MUST NOT leak through the accidental channels that plain ``bytes`` leaks through:
``repr``/``str`` (logs, tracebacks, f-strings), ``pickle``/``copy`` (serializing
into node state, receipts, checkpoints), ``format``, or iteration.

The ONLY way to read the value is the explicit :meth:`reveal` call, which is the
grep-able seam a reviewer can audit. Buffers are zeroed best-effort on
``zero()`` / context exit; this is defense-in-depth, not a guarantee (CPython may
have already copied the bytes elsewhere).
"""

from __future__ import annotations

from typing import NoReturn

_REDACTED = "<redacted-secret>"

# A credential value (token / PEM / key bundle) is small; cap it generously so a
# bug or abuse can't deposit an unbounded blob. Reject empty at the boundary too.
MAX_SECRET_BYTES = 1 * 1024 * 1024  # 1 MiB


def require_nonempty_bounded(value: "SecretBytes") -> None:
    """Reject an empty or oversized credential payload at the broker boundary.

    Raised BEFORE any write, so a rejected CAS/deposit preserves the prior value.
    """
    length = len(value)
    if length == 0:
        raise ValueError("empty credential payload is not allowed")
    if length > MAX_SECRET_BYTES:
        raise ValueError(f"credential payload exceeds the {MAX_SECRET_BYTES}-byte cap")


def _refuse_serialize(*_args: object, **_kwargs: object) -> NoReturn:
    raise TypeError(
        "secret material cannot be serialized/pickled/copied; "
        "read it explicitly via .reveal() at the point of use"
    )


class SecretBytes:
    """A byte buffer that cannot stringify, serialize, pickle, or repr its value.

    Construct from ``bytes``/``bytearray``; read only via :meth:`reveal`.
    """

    __slots__ = ("_buf",)

    def __init__(self, value: bytes | bytearray | memoryview) -> None:
        if isinstance(value, memoryview):
            value = value.tobytes()
        if not isinstance(value, (bytes, bytearray)):
            raise TypeError("SecretBytes requires bytes-like input")
        # Own a private mutable copy so callers cannot retain a handle and so
        # we can zero it later.
        self._buf = bytearray(value)

    def reveal(self) -> bytes:
        """Return the raw bytes. This is the single audited disclosure point."""
        return bytes(self._buf)

    def __len__(self) -> int:
        return len(self._buf)

    def zero(self) -> None:
        """Best-effort wipe of the underlying buffer."""
        for i in range(len(self._buf)):
            self._buf[i] = 0

    # --- context manager: wipe on exit ---------------------------------
    def __enter__(self) -> "SecretBytes":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.zero()

    # --- disclosure blockers -------------------------------------------
    def __repr__(self) -> str:
        return f"SecretBytes({_REDACTED}, len={len(self._buf)})"

    __str__ = __repr__

    def __format__(self, _spec: str) -> str:
        return _REDACTED

    # equality/identity must not fingerprint the value
    def __eq__(self, other: object) -> bool:
        return self is other

    __hash__ = None  # type: ignore[assignment]  # unhashable → can't become a dict key

    # block pickling / copy / iteration
    __reduce__ = _refuse_serialize
    __reduce_ex__ = _refuse_serialize
    __getstate__ = _refuse_serialize
    __copy__ = _refuse_serialize
    __deepcopy__ = _refuse_serialize

    def __iter__(self) -> NoReturn:
        raise TypeError("SecretBytes is not iterable; use .reveal()")


class SecretLease:
    """A short-lived, non-observable disclosure of a stored secret.

    A lease carries non-secret descriptor identity (``ref``/``kind``/``scope``)
    for the adapter to sanity-check, plus the protected value which is readable
    only via :meth:`reveal`. Use it as a context manager so the buffer is zeroed
    the instant the outbound call returns::

        with broker.get(binding, expected=scope) as lease:
            do_request(lease.reveal())
        # value is zeroed here
    """

    __slots__ = ("_secret", "ref", "kind", "scope", "version")

    def __init__(
        self,
        secret: SecretBytes,
        *,
        ref: str,
        kind: str,
        scope: object,
        version: int,
    ) -> None:
        self._secret = secret
        self.ref = ref
        self.kind = kind
        self.scope = scope
        self.version = version

    def reveal(self) -> bytes:
        """Return the raw secret bytes (single audited disclosure point)."""
        return self._secret.reveal()

    def zero(self) -> None:
        self._secret.zero()

    def __enter__(self) -> "SecretLease":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.zero()

    def __repr__(self) -> str:
        # Allowlist only: ref + kind (both log-safe). No version (internal
        # lifecycle counter) and never the value.
        return f"SecretLease(ref={self.ref!r}, kind={self.kind!r}, value={_REDACTED})"

    __str__ = __repr__

    def __format__(self, _spec: str) -> str:
        return f"SecretLease(ref={self.ref}, value={_REDACTED})"

    __reduce__ = _refuse_serialize
    __reduce_ex__ = _refuse_serialize
    __getstate__ = _refuse_serialize
    __copy__ = _refuse_serialize
    __deepcopy__ = _refuse_serialize
