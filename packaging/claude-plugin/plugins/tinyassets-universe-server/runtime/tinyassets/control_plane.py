"""Process-wide control-plane credential quarantine."""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path

CONTROL_PLANE_ENV = "TINYASSETS_CONTROL_PLANE"
_CREDENTIAL_MANIFEST = Path(__file__).with_name("provider_credential_env_vars.txt")
_VALID_KINDS = frozenset({"api_key", "host_auth", "provider_policy"})


def _load_provider_credential_manifest() -> tuple[tuple[str, str], ...]:
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for lineno, raw_line in enumerate(
        _CREDENTIAL_MANIFEST.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 2 or fields[0] not in _VALID_KINDS:
            raise RuntimeError(
                f"invalid provider credential manifest entry at line {lineno}"
            )
        kind, name = fields
        if not name.isidentifier() or name != name.upper() or name in seen:
            raise RuntimeError(
                f"invalid provider credential environment name at line {lineno}"
            )
        entries.append((kind, name))
        seen.add(name)
    if not entries:
        raise RuntimeError("provider credential manifest must not be empty")
    return tuple(entries)


PROVIDER_CREDENTIAL_ENV_ENTRIES = _load_provider_credential_manifest()
PROVIDER_CREDENTIAL_ENV_VARS = tuple(
    name for _kind, name in PROVIDER_CREDENTIAL_ENV_ENTRIES
)
API_KEY_PROVIDER_ENV_VARS = tuple(
    name for kind, name in PROVIDER_CREDENTIAL_ENV_ENTRIES if kind == "api_key"
)
HOST_AUTH_ENV_VARS = tuple(
    name
    for kind, name in PROVIDER_CREDENTIAL_ENV_ENTRIES
    if kind in {"api_key", "host_auth"}
)


def truthy_env(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def assert_provider_credential_env_write_allowed(
    name: str,
    environ: MutableMapping[str, str] | None = None,
) -> None:
    """Fail before a manifest credential enters a control-plane environment."""
    if name not in PROVIDER_CREDENTIAL_ENV_VARS:
        raise ValueError(f"not a provider credential manifest variable: {name}")
    target = os.environ if environ is None else environ
    if truthy_env(target.get(CONTROL_PLANE_ENV)):
        raise RuntimeError(
            "control-plane process refuses provider credential environment "
            f"write: {name}"
        )


def scrub_control_plane_provider_credentials(
    environ: MutableMapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Remove every provider credential from a marked process environment."""
    target = os.environ if environ is None else environ
    if not truthy_env(target.get(CONTROL_PLANE_ENV)):
        return ()
    removed = tuple(name for name in PROVIDER_CREDENTIAL_ENV_VARS if name in target)
    for name in PROVIDER_CREDENTIAL_ENV_VARS:
        target.pop(name, None)
    return removed
