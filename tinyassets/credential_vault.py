"""RETIRED — the legacy per-universe plaintext credential vault is gone.

This module is a fail-closed marker, kept only so any stale caller fails
LOUDLY with a pointer to the replacement instead of a bare ImportError
(Hard Rule 11: the known-bad shape gets no shim, no fallback reader, no
dual path — and Hard Rule 8: fail loudly, never silently).

The legacy surface stored secrets base64/plaintext in
``.credential-vault.json`` + ``.credentials/`` inside the universe
directory. It is replaced by:

* :mod:`tinyassets.credentials` — the provider-generic encrypted vault CORE;
* :mod:`tinyassets.credential_broker` — deposit / binding-lookup /
  resolution seam (the single production route);
* :mod:`tinyassets.credential_migration` — one-way quarantine migration off
  the plaintext files (values are never promoted; founders re-deposit).

Every entry point below raises :class:`LegacyCredentialVaultRetired`.
"""

from __future__ import annotations

from typing import Any, NoReturn


class LegacyCredentialVaultRetired(RuntimeError):
    """The legacy plaintext credential vault has no reader and no writer."""


def _retired(name: str) -> Any:
    def _raise(*_args: Any, **_kwargs: Any) -> NoReturn:
        raise LegacyCredentialVaultRetired(
            f"tinyassets.credential_vault.{name} is retired. Use "
            "tinyassets.credential_broker (deposit/resolve) and "
            "tinyassets.credential_migration (legacy quarantine) instead."
        )

    _raise.__name__ = name
    return _raise


load_credential_vault = _retired("load_credential_vault")
write_credential_vault = _retired("write_credential_vault")
credential_vault_path = _retired("credential_vault_path")
vault_exists = _retired("vault_exists")
resolve_github_token = _retired("resolve_github_token")
resolve_codex_home = _retired("resolve_codex_home")
ensure_codex_home_from_vault = _retired("ensure_codex_home_from_vault")
codex_subscription_auth_available = _retired("codex_subscription_auth_available")
resolve_claude_config_dir = _retired("resolve_claude_config_dir")
ensure_claude_config_dir_from_vault = _retired("ensure_claude_config_dir_from_vault")
resolve_claude_home = _retired("resolve_claude_home")
ensure_claude_home_from_vault = _retired("ensure_claude_home_from_vault")
resolve_claude_oauth_token = _retired("resolve_claude_oauth_token")
claude_subscription_auth_available = _retired("claude_subscription_auth_available")
supported_llm_api_key_services = _retired("supported_llm_api_key_services")
resolve_llm_api_key = _retired("resolve_llm_api_key")
provider_auth_env_overrides = _retired("provider_auth_env_overrides")
resolve_universe_from_env = _retired("resolve_universe_from_env")
apply_provider_auth_env = _retired("apply_provider_auth_env")
