"""Per-universe credential vault helpers.

The vault stores credentials that are scoped to one universe directory. Public
state and run evidence should reference only summaries; resolver helpers return
secret values only to daemon-side effectors/providers that need them.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

VAULT_FILENAME = ".credential-vault.json"
CREDENTIAL_ARTIFACT_DIR = ".credentials"
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


# NOTE: an add-or-replace `upsert_credential` primitive was removed in Phase-1
# (round 10, F4). It had NO production caller (hosted BYO deposit is refused
# through the chat until Phase 2) and its claimed atomicity was FALSE across
# processes (process-local lock + a shared fixed ``.tmp`` name → lost writes +
# Windows PermissionError under concurrency). A real multiprocess-safe atomic
# vault (OS-level lock + unique temp files + a transactional backend) lands with
# the Phase-2 out-of-chat deposit flow. A false atomicity claim on dead code is
# worse than its absence.


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


class RetiredSubscriptionLaneError(RuntimeError):
    """A per-universe vault holds a legacy ``llm_subscription`` record.

    Founder subscription custody is a RETIRED, BLOCKED lane (2026-07-02 custody
    research §0/§4): the platform must NOT custody + drive a founder's personal
    subscription token (Anthropic/OpenAI ToS). The host's OWN subscription auth is
    exclusively PROCESS-GLOBAL first-party (Option E) — it never flows through the
    per-universe vault. A legacy per-universe ``llm_subscription`` record is
    therefore never injected into a spawn; it is rejected here (fail loud, Hard
    Rule #8) so the record is migrated/removed rather than silently skipped
    (round-12 #1). Carries the offending service so the operator can locate it.
    """

    def __init__(self, service: str, universe_dir: str) -> None:
        self.service = service
        self.universe_dir = universe_dir
        super().__init__(
            f"per-universe llm_subscription record (service={service!r}) at "
            f"{universe_dir} is a RETIRED credential lane — the platform never "
            "custodies subscription tokens (host auth is process-global). Remove "
            "or migrate the record; bind a sanctioned engine via "
            "write_graph target=engine (BYO key / self-hosted / market / "
            "host-your-own-device)."
        )


def _llm_subscription_records(universe_dir: str | Path | None) -> list[dict[str, Any]]:
    """Return ANY legacy ``llm_subscription`` records in the universe vault.

    The subscription-custody lane is retired (:class:`RetiredSubscriptionLaneError`):
    these records are never a spawn auth source. This helper exists ONLY to DETECT
    a legacy record so the spawn path can fail loud instead of silently consuming
    it. Propagates ``ValueError`` (malformed vault) to the caller.
    """
    if universe_dir is None:
        return []
    return [
        record
        for record in load_credential_vault(universe_dir)
        if record.get("credential_type") == "llm_subscription"
    ]


def _reject_retired_subscription_records(universe_dir: str | Path | None) -> None:
    """Raise :class:`RetiredSubscriptionLaneError` if a legacy subscription record
    is present in the universe vault (round-12 #1: quarantine, not silent skip)."""
    for record in _llm_subscription_records(universe_dir):
        raise RetiredSubscriptionLaneError(
            _service(record) or "unknown", str(universe_dir),
        )


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


def _byo_lane_selected(universe_dir: str | Path | None) -> bool:
    """True iff the universe's declared engine lane is the BYO-key lane (round-13
    #2). Gates BOTH the overlay and the byo-bound decision so a universe switched
    AWAY from BYO (market/host_daemon/self_hosted) never gets its retained vault
    key injected. Fails CLOSED (no injection) on any resolution error. Lazy import
    avoids a credential_vault <-> engine_binding cycle."""
    if universe_dir is None:
        return False
    try:
        from tinyassets.engine_binding import byo_lane_selected

        return byo_lane_selected(universe_dir)
    except Exception:  # noqa: BLE001 — a resolution problem must not enable BYO
        return False


def _byo_isolated_config_dir(universe_dir: str | Path | None) -> Path | None:
    """Return an EMPTY, per-universe CLAUDE_CONFIG_DIR for a BYO claude-code spawn.

    Round-12 #2: scrubbing ``CLAUDE_CONFIG_DIR`` alone would let claude-code fall
    back to the host's ``~/.claude`` (which may hold the host's OWN subscription
    OAuth) — the BYO child could then authenticate as the platform instead of with
    the founder's key. Pointing ``CLAUDE_CONFIG_DIR`` at an isolated EMPTY dir
    (bare mode) forecloses that: no cached OAuth is present, so ``ANTHROPIC_API_KEY``
    (the BYO key) is the only credential the child can use.
    """
    if universe_dir is None:
        return None
    iso = Path(universe_dir) / CREDENTIAL_ARTIFACT_DIR / "claude-byo-isolated"
    iso.mkdir(parents=True, exist_ok=True)
    _chmod_best_effort(iso.parent, 0o700)
    _chmod_best_effort(iso, 0o700)
    return iso


def provider_auth_env_overrides(
    universe_dir: str | Path | None,
    provider_name: str,
    *,
    byo_enabled: bool | None = None,
) -> dict[str, str]:
    """Return subprocess env overrides for a CLI-subprocess provider.

    ``byo_enabled`` is the caller's ONE authoritative attestation snapshot
    (round-11 #2 / round-12 #3 TOCTOU fix): when threaded, this function does NOT
    recompute ``_byo_injection_enabled()`` — so the byo-bound decision and the
    overlay can never disagree across a mid-call attestation flip. ``None``
    recomputes (for standalone callers).

    ONLY the sanctioned BYO ``llm_api_key`` lane produces overrides, and only when
    (a) executable BYO is enabled (:func:`_byo_injection_enabled`, DARK by default)
    and (b) the provider is BYO-EXECUTABLE — **claude-code only** today (Codex BYO
    needs unmet sandboxing, so a codex key is NEVER injected; C2). A per-universe
    ``llm_subscription`` record is a RETIRED lane and is REJECTED
    (:class:`RetiredSubscriptionLaneError`, round-12 #1) — it is never a spawn auth
    source; host subscription auth stays exclusively process-global. When the BYO
    key is chosen the overlay also pins an ISOLATED empty ``CLAUDE_CONFIG_DIR`` so
    the child can't fall back to the host's ``~/.claude`` OAuth (round-12 #2).
    """
    if byo_enabled is None:
        byo_enabled = _byo_injection_enabled()
    provider = provider_name.strip()
    # Round-12 #1: a legacy per-universe subscription record is NEVER consumed —
    # fail loud (quarantine) rather than silently inject or skip it.
    _reject_retired_subscription_records(universe_dir)
    if (
        provider == "claude-code"
        and byo_enabled
        and _byo_lane_selected(universe_dir)
    ):
        api_key = resolve_llm_api_key(universe_dir, "ANTHROPIC_API_KEY")
        if api_key:
            overrides: dict[str, str] = {"ANTHROPIC_API_KEY": api_key}
            iso = _byo_isolated_config_dir(universe_dir)
            if iso is not None:
                overrides["CLAUDE_CONFIG_DIR"] = str(iso)
            return overrides
    # No sanctioned per-universe lane selected (or the universe switched AWAY from
    # BYO — round-13 #2): the host's process-global first-party auth (inherited
    # env) stands. Codex + all non-BYO paths inject nothing here.
    return {}


def resolve_universe_from_env(env: dict[str, str] | None = None) -> Path | None:
    """Resolve the active universe path from env, if one is explicitly bound."""
    source = os.environ if env is None else env
    value = source.get("TINYASSETS_UNIVERSE", "").strip()
    return Path(value) if value else None


#: BYO-EXECUTABLE providers → their BYO env var. Only claude-code is
#: BYO-executable (Codex BYO needs unmet sandboxing, C2).
_PROVIDER_BYO_ENV_VAR: dict[str, str] = {
    "claude-code": "ANTHROPIC_API_KEY",
}

#: Round-12 #2 — POSITIVE auth allowlist for a BYO claude-code child. Claude Code
#: consults SEVERAL credential selectors at a HIGHER precedence than (or as an
#: alternative to) ``ANTHROPIC_API_KEY`` — a Bedrock/Vertex flag, cloud creds, an
#: OAuth token, an auth-token, a config dir with a cached login. A deny-list can't
#: anticipate them all, so when the BYO lane is chosen we strip EVERY auth selector
#: and let ONLY ``ANTHROPIC_API_KEY`` (the founder's BYO key) authenticate the
#: child. Named selectors + namespace prefixes (below) are both swept so an
#: undocumented future selector in those families can't leak.
#: Basis: code.claude.com/docs/en/authentication (auth precedence: Bedrock/Vertex,
#: ANTHROPIC_AUTH_TOKEN, cloud creds all outrank the API key).
_BYO_AUTH_SELECTOR_NAMES: frozenset[str] = frozenset({
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_BEDROCK_BASE_URL",
    "ANTHROPIC_VERTEX_BASE_URL",
    "ANTHROPIC_VERTEX_PROJECT_ID",
    "ANTHROPIC_CUSTOM_HEADERS",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_CONFIG_DIR",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_PROFILE",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
    "AWS_BEARER_TOKEN_BEDROCK",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT",
    "GCLOUD_PROJECT",
    "CLOUD_ML_REGION",
    "VERTEX_REGION",
})
#: Whole namespace families to sweep (every var whose name starts with one of
#: these is an auth selector for Bedrock/Vertex/AWS/GCP or a Claude OAuth
#: credential and must not survive). ``CLAUDE_CODE_OAUTH_`` sweeps the WHOLE OAuth
#: family — round-12 removed only ``CLAUDE_CODE_OAUTH_TOKEN`` by exact name, so
#: ``CLAUDE_CODE_OAUTH_REFRESH_TOKEN`` (and any future OAuth var) survived into a
#: BYO child (round-13 #1: don't rely on an exact-name denylist for OAuth creds).
_BYO_AUTH_SELECTOR_PREFIXES: tuple[str, ...] = (
    "AWS_", "CLAUDE_CODE_USE_", "CLAUDE_CODE_OAUTH_", "GOOGLE_", "GCLOUD_",
    "VERTEX_",
)


def scrub_byo_child_auth(env: dict[str, str]) -> None:
    """Positive-allowlist the AUTH surface of a BYO claude-code child in place.

    Removes EVERY credential selector except ``ANTHROPIC_API_KEY`` (which the
    caller sets to the founder's BYO key): the named higher-precedence selectors,
    the cloud-auth namespace families, and every ``ANTHROPIC_*`` other than
    ``ANTHROPIC_API_KEY``. After this, ``ANTHROPIC_API_KEY`` is the only auth the
    child can use (round-12 #2)."""
    for name in list(env):
        if name == "ANTHROPIC_API_KEY":
            continue
        if (
            name in _BYO_AUTH_SELECTOR_NAMES
            or name.startswith(_BYO_AUTH_SELECTOR_PREFIXES)
            or name.startswith("ANTHROPIC_")
        ):
            env.pop(name, None)


def provider_is_byo_bound(
    provider_name: str,
    *,
    env: dict[str, str] | None = None,
    universe_dir: str | Path | None = None,
    byo_enabled: bool | None = None,
) -> bool:
    """Return True iff the resolved universe holds an INJECTABLE BYO key for
    *provider* — i.e. executable BYO is enabled AND *provider* is BYO-executable.

    ``byo_enabled`` is the caller's ONE authoritative attestation snapshot
    (round-11 #2); ``None`` recomputes. A BYO-bound spawn must FAIL CLOSED on any
    materialization error rather than silently fall through to platform-global
    auth. A broken BYO secret (``resolve_llm_api_key`` raising) still counts as
    BYO-bound so the caller fails closed."""
    env_var = _PROVIDER_BYO_ENV_VAR.get(provider_name.strip())
    if not env_var:
        return False
    if byo_enabled is None:
        byo_enabled = _byo_injection_enabled()
    if not byo_enabled:
        return False  # BYO dark (C2/C4) — no BYO-bound spawn to fail closed on
    resolved = (
        Path(universe_dir)
        if universe_dir is not None
        else resolve_universe_from_env(env)
    )
    if resolved is None:
        return False
    # Round-13 #2: lane-aware. A universe switched AWAY from BYO (market/host/
    # self-hosted) is NOT byo-bound even if a stale key lingers in the vault —
    # otherwise the spawn would scrub+inject/harden for a non-BYO lane.
    if not _byo_lane_selected(resolved):
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
    byo_enabled: bool | None = None,
) -> dict[str, str]:
    """Overlay per-universe auth settings onto *env*.

    ``byo_enabled`` is the caller's ONE authoritative attestation snapshot
    (round-11 #2 TOCTOU fix) — threaded straight into
    :func:`provider_auth_env_overrides` so the byo-bound decision and the overlay
    can never disagree across a mid-call attestation flip.

    When the BYO-key lane is chosen for a CLI-subprocess provider, positive-
    allowlist the child's AUTH surface (:func:`scrub_byo_child_auth`, round-12 #2)
    so ONLY the BYO key authenticates it — every higher-precedence selector
    (Bedrock/Vertex flags, AWS/GCP creds, OAuth/auth tokens, config dir) is
    stripped before the key + isolated config are overlaid. Propagates errors
    (``ValueError`` malformed vault, :class:`RetiredSubscriptionLaneError` legacy
    record) so a BYO spawn fails closed instead of running on ambient platform
    auth.
    """
    resolved_universe = (
        Path(universe_dir)
        if universe_dir is not None
        else resolve_universe_from_env(env)
    )
    if resolved_universe is None:
        return env
    overrides = provider_auth_env_overrides(
        resolved_universe, provider_name, byo_enabled=byo_enabled,
    )
    provider = provider_name.strip()
    byo_var = _PROVIDER_BYO_ENV_VAR.get(provider)
    if byo_var and byo_var in overrides:
        # BYO lane chosen — positive-allowlist the auth surface so no ambient
        # higher-precedence selector can outrank / substitute for the BYO key.
        scrub_byo_child_auth(env)
    env.update(overrides)
    return env
