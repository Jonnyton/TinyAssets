"""Per-universe credential vault helpers.

The vault stores credentials that are scoped to one universe directory. Public
state and run evidence should reference only summaries; resolver helpers return
secret values only to daemon-side effectors/providers that need them.
"""

from __future__ import annotations

import base64
import json
import os
import threading
from pathlib import Path
from typing import Any

VAULT_FILENAME = ".credential-vault.json"
CREDENTIAL_ARTIFACT_DIR = ".credentials"

# Per-vault-path locks so a load→merge→write upsert is atomic against concurrent
# writers in the same process (C5). Keyed by the resolved vault file path.
_VAULT_LOCKS: dict[str, threading.Lock] = {}
_VAULT_LOCKS_GUARD = threading.Lock()
VALID_CREDENTIAL_TYPES = frozenset(
    {"social", "llm_subscription", "llm_api_key", "vcs"}
)

# Map a deposited llm_api_key record's ``service`` to the provider-subprocess
# env var that CLI providers read. Only CLI-subprocess providers are reachable
# via the vault env overlay (claude-code / codex); the in-process HTTP free-tier
# providers build their client from process env at import and are out of scope.
_LLM_API_KEY_ENV_BY_SERVICE: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "claude-code": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "codex": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "google": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "xai": "XAI_API_KEY",
    "grok": "XAI_API_KEY",
}


def credential_vault_path(universe_dir: str | Path) -> Path:
    """Return the vault file path for *universe_dir*."""
    return Path(universe_dir) / VAULT_FILENAME


def vault_exists(universe_dir: str | Path | None) -> bool:
    """Return True when a vault file exists for *universe_dir*."""
    return universe_dir is not None and credential_vault_path(universe_dir).is_file()


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _as_path(value: Any, universe_dir: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = universe_dir / candidate
    return candidate


def _secret_artifact_dir(universe_dir: Path, service: str) -> Path:
    service_part = "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "-"
        for ch in service.strip().lower()
    ) or "credential"
    target = universe_dir / CREDENTIAL_ARTIFACT_DIR / service_part
    target.mkdir(parents=True, exist_ok=True)
    _chmod_best_effort(target.parent, 0o700)
    _chmod_best_effort(target, 0o700)
    return target


def _normalize_record(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("credential entries must be JSON objects")
    record = dict(raw)
    credential_type = record.get("credential_type")
    if not isinstance(credential_type, str) or not credential_type.strip():
        raise ValueError("credential_type is required")
    normalized_type = credential_type.strip()
    if normalized_type not in VALID_CREDENTIAL_TYPES:
        allowed = ", ".join(sorted(VALID_CREDENTIAL_TYPES))
        raise ValueError(
            f"unknown credential_type {normalized_type!r}; expected one of: {allowed}"
        )
    record["credential_type"] = normalized_type
    for key in ("service", "provider", "destination", "purpose"):
        if isinstance(record.get(key), str):
            record[key] = record[key].strip()
    return record


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        raw_records = payload
    elif isinstance(payload, dict):
        raw_records = payload.get("credentials", [])
    else:
        raise ValueError("credential vault must be a JSON object or list")
    if not isinstance(raw_records, list):
        raise ValueError("credential vault 'credentials' must be a list")
    return [_normalize_record(item) for item in raw_records]


def load_credential_vault(universe_dir: str | Path) -> list[dict[str, Any]]:
    """Load and validate the per-universe vault.

    Missing vaults are treated as empty. Malformed vaults raise ValueError so a
    daemon cannot silently grant or lose authority due to a bad secret file.
    """
    path = credential_vault_path(universe_dir)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"credential vault is not valid JSON: {exc}") from exc
    return _records_from_payload(payload)


def write_credential_vault(
    universe_dir: str | Path,
    credentials: list[dict[str, Any]] | dict[str, Any],
) -> dict[str, Any]:
    """Validate and write a per-universe credential vault.

    Returns a non-secret summary suitable for logs/status surfaces.
    """
    universe = Path(universe_dir)
    universe.mkdir(parents=True, exist_ok=True)
    records = _records_from_payload(credentials)
    path = credential_vault_path(universe)
    tmp = path.with_name(f"{path.name}.tmp")
    payload = {"schema_version": 1, "credentials": records}
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _chmod_best_effort(tmp, 0o600)
    tmp.replace(path)
    _chmod_best_effort(path, 0o600)
    credential_types = sorted({str(r["credential_type"]) for r in records})
    services = sorted(
        {
            str(r.get("service") or r.get("provider") or "").strip()
            for r in records
            if str(r.get("service") or r.get("provider") or "").strip()
        }
    )
    return {
        "path": str(path),
        "credential_count": len(records),
        "credential_types": credential_types,
        "services": services,
    }


def _service(record: dict[str, Any]) -> str:
    return str(record.get("service") or record.get("provider") or "").strip().lower()


def _credential_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    """Identity of a credential record for upsert-by-identity.

    ``(credential_type, service, destination)`` — ``destination`` only
    distinguishes ``vcs`` records (a founder can bind multiple repos); for
    llm_api_key / llm_subscription / social the destination component is empty so
    one record per (type, service) is kept.
    """
    ctype = str(record.get("credential_type") or "").strip()
    dest = str(record.get("destination") or "").strip() if ctype == "vcs" else ""
    return (ctype, _service(record), dest)


def _vault_lock(universe_dir: str | Path) -> threading.Lock:
    """Return the process-wide lock for *universe_dir*'s vault file."""
    key = str(credential_vault_path(universe_dir).resolve())
    with _VAULT_LOCKS_GUARD:
        lock = _VAULT_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _VAULT_LOCKS[key] = lock
        return lock


def upsert_credential(
    universe_dir: str | Path,
    record: dict[str, Any],
) -> dict[str, Any]:
    """Atomically add-or-replace ONE credential, PRESERVING all other records.

    ``write_credential_vault`` is a replace-ALL writer — calling it with a single
    record WIPES a founder's other credentials (social / vcs). This upsert loads
    the existing vault, replaces only the record with the same
    :func:`_credential_identity`, appends if none matched, and writes the full
    set back (F2). The load→merge→write is held under a per-vault LOCK so two
    concurrent upserts cannot each read a stale set and clobber the other's write
    (C5) — both distinct records survive. Propagates :class:`ValueError` on a
    malformed existing vault so the caller can fail loud rather than clobber.
    """
    universe = Path(universe_dir)
    normalized = _normalize_record(record)
    identity = _credential_identity(normalized)
    with _vault_lock(universe):
        existing = load_credential_vault(universe)  # raises ValueError if malformed
        merged = [r for r in existing if _credential_identity(r) != identity]
        merged.append(normalized)
        return write_credential_vault(universe, merged)


def _purpose_matches(record: dict[str, Any], purpose: str) -> bool:
    expected = purpose.strip()
    record_purpose = record.get("purpose")
    if isinstance(record_purpose, str) and record_purpose.strip():
        return record_purpose.strip() == expected
    purposes = record.get("purposes")
    if isinstance(purposes, list):
        return expected in [str(item).strip() for item in purposes]
    return expected == "write"


def _secret_value(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    b64 = record.get("token_b64") or record.get("secret_b64")
    if isinstance(b64, str) and b64.strip():
        try:
            return base64.b64decode(b64.strip()).decode("utf-8").strip()
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"credential {keys[0]} base64 decode failed") from exc
    return ""


def resolve_github_token(
    universe_dir: str | Path | None,
    destination: str,
    *,
    purpose: str = "write",
) -> str:
    """Return a GitHub token from the per-universe vault, or an empty string."""
    if universe_dir is None:
        return ""
    wanted_destination = destination.strip()
    if not wanted_destination:
        return ""
    for record in load_credential_vault(universe_dir):
        if record.get("credential_type") != "vcs":
            continue
        if _service(record) != "github":
            continue
        if str(record.get("destination") or "").strip() != wanted_destination:
            continue
        if not _purpose_matches(record, purpose):
            continue
        return _secret_value(record, "token", "access_token")
    return ""


def _llm_records(universe_dir: str | Path | None, service: str) -> list[dict[str, Any]]:
    if universe_dir is None:
        return []
    service_key = service.strip().lower()
    return [
        record
        for record in load_credential_vault(universe_dir)
        if record.get("credential_type") == "llm_subscription"
        and _service(record) == service_key
    ]


def _codex_home_from_record(record: dict[str, Any], universe_dir: Path) -> Path | None:
    for key in ("codex_home", "home", "auth_home", "path"):
        resolved = _as_path(record.get(key), universe_dir)
        if resolved is not None:
            return resolved
    auth_path = _as_path(record.get("auth_json_path"), universe_dir)
    if auth_path is not None:
        return auth_path.parent
    return None


def resolve_codex_home(universe_dir: str | Path | None) -> Path | None:
    """Return the configured CODEX_HOME path for this universe, if any."""
    if universe_dir is None:
        return None
    universe = Path(universe_dir)
    for record in _llm_records(universe, "codex"):
        home = _codex_home_from_record(record, universe)
        if home is not None:
            return home
    materialized = universe / CREDENTIAL_ARTIFACT_DIR / "codex"
    if (materialized / "auth.json").is_file():
        return materialized
    return None


def ensure_codex_home_from_vault(universe_dir: str | Path | None) -> Path | None:
    """Materialize any vault-backed Codex auth bundle and return CODEX_HOME."""
    if universe_dir is None:
        return None
    universe = Path(universe_dir)
    for record in _llm_records(universe, "codex"):
        home = _codex_home_from_record(record, universe) or _secret_artifact_dir(universe, "codex")
        home.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(home, 0o700)
        auth_b64 = record.get("auth_json_b64")
        auth_file = home / "auth.json"
        if isinstance(auth_b64, str) and auth_b64.strip() and not auth_file.exists():
            tmp = auth_file.with_name("auth.json.tmp")
            tmp.write_bytes(base64.b64decode(auth_b64.strip()))
            _chmod_best_effort(tmp, 0o600)
            tmp.replace(auth_file)
            _chmod_best_effort(auth_file, 0o600)
        config_file = home / "config.toml"
        if auth_file.exists() and not config_file.exists():
            config_file.write_text(
                'cli_auth_credentials_store = "file"\n',
                encoding="utf-8",
            )
            _chmod_best_effort(config_file, 0o600)
        return home
    return resolve_codex_home(universe)


def codex_subscription_auth_available(universe_dir: str | Path | None) -> bool:
    """Return True when the vault can provide or points at Codex auth."""
    home = ensure_codex_home_from_vault(universe_dir)
    return bool(home and (home / "auth.json").is_file())


def _claude_config_dir_from_record(record: dict[str, Any], universe_dir: Path) -> Path | None:
    for key in ("claude_config_dir", "config_dir", "path"):
        resolved = _as_path(record.get(key), universe_dir)
        if resolved is not None:
            return resolved
    for key in ("claude_home", "home", "auth_home"):
        home = _as_path(record.get(key), universe_dir)
        if home is not None:
            return home / ".claude"
    return None


def resolve_claude_config_dir(universe_dir: str | Path | None) -> Path | None:
    """Return the CLAUDE_CONFIG_DIR path for this universe, if any."""
    if universe_dir is None:
        return None
    universe = Path(universe_dir)
    for record in _llm_records(universe, "claude"):
        config_dir = _claude_config_dir_from_record(record, universe)
        if config_dir is not None:
            return config_dir
    materialized = universe / CREDENTIAL_ARTIFACT_DIR / "claude"
    if materialized.is_dir():
        return materialized
    return None


def ensure_claude_config_dir_from_vault(universe_dir: str | Path | None) -> Path | None:
    """Create the configured Claude config directory and return it."""
    if universe_dir is None:
        return None
    universe = Path(universe_dir)
    for record in _llm_records(universe, "claude"):
        config_dir = _claude_config_dir_from_record(record, universe)
        if config_dir is None:
            config_dir = _secret_artifact_dir(universe, "claude")
        config_dir.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(config_dir, 0o700)
        return config_dir
    return resolve_claude_config_dir(universe)


def resolve_claude_home(universe_dir: str | Path | None) -> Path | None:
    """Deprecated compatibility: return CLAUDE_CONFIG_DIR's parent."""
    config_dir = resolve_claude_config_dir(universe_dir)
    return config_dir.parent if config_dir is not None else None


def ensure_claude_home_from_vault(universe_dir: str | Path | None) -> Path | None:
    """Deprecated compatibility: create CLAUDE_CONFIG_DIR and return parent."""
    config_dir = ensure_claude_config_dir_from_vault(universe_dir)
    return config_dir.parent if config_dir is not None else None


def resolve_claude_oauth_token(universe_dir: str | Path | None) -> str:
    """Return a Claude subscription OAuth token from the vault, if present."""
    for record in _llm_records(universe_dir, "claude"):
        return _secret_value(record, "oauth_token", "claude_code_oauth_token")
    return ""


def claude_subscription_auth_available(universe_dir: str | Path | None) -> bool:
    """Return True when the vault provides a Claude subscription auth route."""
    if resolve_claude_oauth_token(universe_dir):
        return True
    config_dir = ensure_claude_config_dir_from_vault(universe_dir)
    return bool(config_dir and config_dir.is_dir())


def supported_llm_api_key_services() -> frozenset[str]:
    """Services a BYO ``llm_api_key`` deposit may target.

    Only these reach a CLI-subprocess provider via the vault env overlay; a
    deposit for any other service would never inject and the founder's engine
    would silently not run (validate at deposit time — Hard Rule #8)."""
    return frozenset(_LLM_API_KEY_ENV_BY_SERVICE)


# Only these env vars are overlaid per-universe onto the CLI subprocess by
# ``provider_auth_env_overrides`` (codex → OPENAI_API_KEY, claude-code →
# ANTHROPIC_API_KEY). A BYO key for any OTHER service maps only to a
# process-global HTTP provider (gemini/groq/xai), so it is NOT
# per-universe-consumable today.
_PER_UNIVERSE_BYO_ENV_VARS = frozenset({"ANTHROPIC_API_KEY", "OPENAI_API_KEY"})


def per_universe_byo_services() -> frozenset[str]:
    """BYO ``llm_api_key`` services whose key actually flows to a per-universe
    CLI subprocess today (via :func:`provider_auth_env_overrides`).

    gemini / groq / xai keys map only to process-global HTTP providers, so
    binding one per-universe would fake capacity the daemon cannot consume
    (Hard Rule #8). Until per-universe HTTP-provider instantiation is wired,
    only the CLI-subprocess services (anthropic/claude/claude-code,
    openai/codex) are per-universe-consumable."""
    return frozenset(
        svc
        for svc, env in _LLM_API_KEY_ENV_BY_SERVICE.items()
        if env in _PER_UNIVERSE_BYO_ENV_VARS
    )


def resolve_llm_api_key(
    universe_dir: str | Path | None, env_var: str
) -> str:
    """Return a deposited BYO API key whose ``service`` maps to *env_var*, or ''.

    Scans ``llm_api_key`` vault records; a record matches when its ``service``
    resolves (via ``_LLM_API_KEY_ENV_BY_SERVICE``) to the requested provider env
    var. This is the founder's BYO-engine path — the deposited key is injected
    into the CLI subprocess env so ``claude -p`` / ``codex exec`` authenticate
    with the founder's own key instead of the platform's subscription.
    """
    if universe_dir is None:
        return ""
    for record in load_credential_vault(universe_dir):
        if record.get("credential_type") != "llm_api_key":
            continue
        service = _service(record)
        if _LLM_API_KEY_ENV_BY_SERVICE.get(service) != env_var:
            continue
        return _secret_value(record, "api_key", "key", "token")
    return ""


def _byo_injection_enabled() -> bool:
    """True iff a founder BYO key may be injected into a CLI subprocess.

    Gated on the executable-BYO prerequisite (:func:`engine_binding.
    byo_execution_enabled` — KMS-attested, DEFAULT False). When False (this
    deploy) NO BYO key is injected — even a LEGACY ``llm_api_key`` row written by
    the old ungated set_engine — so "BYO path dark" is TRUE for legacy vaults too
    (C2). Lazy import avoids a credential_vault ↔ engine_binding cycle.
    """
    try:
        from tinyassets.engine_binding import byo_execution_enabled

        return byo_execution_enabled()
    except Exception:  # noqa: BLE001 — a resolution problem must not enable BYO
        return False


def provider_auth_env_overrides(
    universe_dir: str | Path | None,
    provider_name: str,
) -> dict[str, str]:
    """Return subprocess env overrides for a CLI-subprocess provider.

    A founder BYO key is injected ONLY when (a) executable BYO is enabled
    (:func:`_byo_injection_enabled`, DARK by default) and (b) the provider is a
    BYO-EXECUTABLE provider — **claude-code only** today (Codex BYO needs unmet
    sandboxing, so a codex key is NEVER injected; C2). Otherwise the overlay is
    the platform/legacy first-party subscription path. The key is overlaid AFTER
    ``subprocess_env_without_api_keys`` strips process-global keys, so a
    per-universe key never leaks across universes.
    """
    provider = provider_name.strip()
    if provider == "claude-code":
        overrides: dict[str, str] = {}
        # BYO-key lane FIRST — but ONLY when executable BYO is enabled. Return
        # BYO-only; the caller scrubs CLAUDE_CONFIG_DIR / CLAUDE_CODE_OAUTH_TOKEN
        # so it can never fall through to platform auth.
        if _byo_injection_enabled():
            api_key = resolve_llm_api_key(universe_dir, "ANTHROPIC_API_KEY")
            if api_key:
                overrides["ANTHROPIC_API_KEY"] = api_key
                return overrides
        # No executable BYO key — legacy / host subscription bundle.
        claude_config_dir = ensure_claude_config_dir_from_vault(universe_dir)
        if claude_config_dir:
            overrides["CLAUDE_CONFIG_DIR"] = str(claude_config_dir)
        oauth_token = resolve_claude_oauth_token(universe_dir)
        if oauth_token:
            overrides["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token
        return overrides
    if provider == "codex":
        # Codex BYO is NOT executable (C2) — a codex/OpenAI BYO key is NEVER
        # injected (that would run judge/extract codex calls on the founder's
        # key). Only the platform/legacy first-party CODEX_HOME subscription.
        overrides = {}
        codex_home = ensure_codex_home_from_vault(universe_dir)
        if codex_home:
            overrides["CODEX_HOME"] = str(codex_home)
        return overrides
    return {}


def resolve_universe_from_env(env: dict[str, str] | None = None) -> Path | None:
    """Resolve the active universe path from env, if one is explicitly bound."""
    source = os.environ if env is None else env
    value = source.get("TINYASSETS_UNIVERSE", "").strip()
    return Path(value) if value else None


#: BYO-EXECUTABLE providers → their BYO env var + the global subscription auth
#: vars to SCRUB from a child env when the BYO lane is chosen (so a BYO spawn can
#: never inherit the platform-global subscription login — Hard Rule #8). Only
#: claude-code is BYO-executable (Codex BYO needs unmet sandboxing, C2).
_PROVIDER_BYO_ENV_VAR: dict[str, str] = {
    "claude-code": "ANTHROPIC_API_KEY",
}
_PROVIDER_GLOBAL_AUTH_SCRUB: dict[str, tuple[str, ...]] = {
    "claude-code": ("CLAUDE_CONFIG_DIR", "CLAUDE_CODE_OAUTH_TOKEN"),
}


def provider_is_byo_bound(
    provider_name: str,
    *,
    env: dict[str, str] | None = None,
    universe_dir: str | Path | None = None,
) -> bool:
    """Return True iff the resolved universe holds an INJECTABLE BYO key for
    *provider* — i.e. executable BYO is enabled AND *provider* is BYO-executable.

    A BYO-bound spawn must FAIL CLOSED on any materialization error rather than
    silently fall through to platform-global auth. A broken BYO secret
    (``resolve_llm_api_key`` raising) still counts as BYO-bound so the caller
    fails closed."""
    env_var = _PROVIDER_BYO_ENV_VAR.get(provider_name.strip())
    if not env_var:
        return False
    if not _byo_injection_enabled():
        return False  # BYO dark (C2/C4) — no BYO-bound spawn to fail closed on
    resolved = (
        Path(universe_dir)
        if universe_dir is not None
        else resolve_universe_from_env(env)
    )
    if resolved is None:
        return False
    try:
        return bool(resolve_llm_api_key(resolved, env_var))
    except ValueError:
        return True  # a BYO record exists but its secret is broken → fail closed


def apply_provider_auth_env(
    env: dict[str, str],
    provider_name: str,
    *,
    universe_dir: str | Path | None = None,
) -> dict[str, str]:
    """Overlay per-universe auth settings onto *env*.

    When the BYO-key lane is chosen for a CLI-subprocess provider, SCRUB the
    inherited global subscription auth vars first so the child authenticates with
    the BYO key ONLY and can never fall through to the platform subscription
    (Codex F3). Propagates errors (ValueError malformed vault, RuntimeError
    isolation failure) so a BYO spawn fails closed instead of running on ambient
    platform auth.
    """
    resolved_universe = (
        Path(universe_dir)
        if universe_dir is not None
        else resolve_universe_from_env(env)
    )
    if resolved_universe is None:
        return env
    overrides = provider_auth_env_overrides(resolved_universe, provider_name)
    provider = provider_name.strip()
    byo_var = _PROVIDER_BYO_ENV_VAR.get(provider)
    if byo_var and byo_var in overrides:
        # BYO lane chosen — remove any inherited global subscription auth so the
        # key, not the platform login, authenticates the child.
        for var in _PROVIDER_GLOBAL_AUTH_SCRUB.get(provider, ()):
            env.pop(var, None)
    env.update(overrides)
    return env
