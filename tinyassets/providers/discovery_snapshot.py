"""Fresh, advisory discovery through owned profiles; never inference authority."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tinyassets.api.helpers import _base_path
from tinyassets.providers.definition import ProviderDefinition, get_definition
from tinyassets.providers.discovery_http import (
    ModelDiscoveryUnavailable,
    read_http_discovery_document,
)
from tinyassets.providers.discovery_protocols import discovery_protocol
from tinyassets.providers.model_policy import ConnectionModels
from tinyassets.storage.outbound_connections import (
    ConnectionLedger,
    ModelDiscoveryCapability,
    _resource_from_row,
    _validate_connection_capability,
    _verb_within_scopes,
)


@dataclass(frozen=True, slots=True)
class DiscoverySnapshot:
    owner_id: str
    universe_id: str
    provider: str
    connection_id: str
    grant_id: str
    source_digest: str
    catalogue_url: str
    benchmark_url: str
    observed_at: datetime
    completed_at: datetime
    models: ConnectionModels
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Context:
    definition: ProviderDefinition
    profile: ModelDiscoveryCapability
    digest: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _context(base: Path, owner: str, uid: str, definition_id: str) -> _Context:
    from tinyassets.credential_vault import _connection_grant_record_digest

    try:
        if not owner or not uid or not definition_id:
            raise ValueError("missing discovery context")
        definition = get_definition(uid, definition_id)
        if (
            not owner
            or not uid
            or definition is None
            or definition.owner_user_id != owner
            or definition.access_method != "api_key_http"
        ):
            raise ModelDiscoveryUnavailable("source_revoked")
        ledger = ConnectionLedger(base / "outbound.db")
        with ledger._connect() as conn:
            conn.execute("BEGIN")
            grant = conn.execute(
                "SELECT * FROM outbound_connection_grants WHERE grant_id = ?",
                (definition.ref,),
            ).fetchone()
            if (
                grant is None
                or grant["revoked_at"] is not None
                or grant["owner_user_id"] != owner
                or grant["universe_id"] != uid
            ):
                raise ModelDiscoveryUnavailable("source_revoked")
            row = conn.execute(
                "SELECT * FROM outbound_connections WHERE connection_id = ?",
                (grant["connection_id"],),
            ).fetchone()
            if row is None:
                raise ModelDiscoveryUnavailable("source_revoked")
            resource = _resource_from_row(row)
            if (
                resource.revoked_at is not None
                or resource.owner_user_id != owner
                or resource.connection_type != "http"
            ):
                raise ModelDiscoveryUnavailable("source_revoked")
            if not _verb_within_scopes("GET", resource.scopes, resource.access_mode):
                raise ModelDiscoveryUnavailable("missing_discovery_scope")
            profile_row = conn.execute(
                "SELECT descriptor_json FROM connection_capabilities WHERE connection_id = ? "
                "AND capability_kind = 'model_discovery'",
                (resource.connection_id,),
            ).fetchone()
            if profile_row is None:
                raise ModelDiscoveryUnavailable("missing_discovery_scope")
            profile = _validate_connection_capability(
                resource.connection_id, "model_discovery", json.loads(profile_row[0])
            )
            if not isinstance(profile, ModelDiscoveryCapability):
                raise ValueError("wrong profile kind")
            if resource.auth_scheme != discovery_protocol(profile.protocol).auth_scheme:
                raise ModelDiscoveryUnavailable("protocol_mismatch")
            # Existing custody identity, not a new secret hash or permission.
            identity = _connection_grant_record_digest(
                grant_id=definition.ref,
                connection_id=resource.connection_id,
                credential_ref=resource.credential_ref,
                owner_user_id=owner,
                universe_id=uid,
            )
            material = {
                "definition_id": definition.id,
                "grant_identity": identity,
                "granted_at": grant["granted_at"],
                "view": resource.to_view().as_dict(),
                "profile": profile.descriptor(),
            }
            digest = hashlib.sha256(
                json.dumps(
                    material, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode()
            ).hexdigest()
            return _Context(definition, profile, digest)
    except (LookupError, OSError, TypeError, ValueError):
        raise ModelDiscoveryUnavailable("discovery_unavailable") from None


def refresh_model_discovery(
    *, owner_user_id: str, universe_id: str, definition_id: str
) -> DiscoverySnapshot:
    """Fetch current data; any later invocation still needs fresh authorization.

    Current explicit preferences, inference bindings and private workflows are
    untouched. Discovery grants no execution capability. Missing benchmark evidence
    leaves models unranked rather than making the catalogue disappear.
    """
    base = _base_path()
    before = _context(base, owner_user_id, universe_id, definition_id)
    profile = before.profile
    contract = discovery_protocol(profile.protocol)
    from tinyassets.providers.protocol_encoders import agent_codec_for

    def read(url: str):
        return read_http_discovery_document(
            db_path=base / "outbound.db",
            definition=before.definition,
            owner_user_id=owner_user_id,
            universe_id=universe_id,
            url=url,
        )

    # Include the catalogue request itself in the freshness window.
    observed_at = _now()
    payload = read(profile.catalogue_url)
    benchmarks = None
    warnings = ()
    if profile.benchmark_url:
        try:
            benchmarks = contract.benchmark_decoder(
                read(profile.benchmark_url), now=_now(), max_age=timedelta(days=1)
            )
        except Exception:
            warnings = ("benchmark_unavailable",)
    provider = f"api_key_http:{before.definition.id}"
    models = contract.model_decoder(
        payload,
        connection=ConnectionModels(
            connection_id=provider,
            provider_scope=profile.protocol,
            source_kind="http",
            freshness="fresh",
            owner_filtered=contract.account_filtered,
            # Local executor capability, never the remote catalogue's claim.
            executor_tools=agent_codec_for(contract.inference_protocol) is not None,
            models=(),
            authenticated_account_id=None,
        ),
        benchmarks=benchmarks,
    )
    after = _context(base, owner_user_id, universe_id, definition_id)
    completed_at = _now()
    if after.digest != before.digest or after.definition != before.definition:
        raise ModelDiscoveryUnavailable("source_revoked")
    if completed_at < observed_at or completed_at - observed_at > timedelta(minutes=5):
        raise ModelDiscoveryUnavailable("discovery_expired")
    return DiscoverySnapshot(
        owner_user_id,
        universe_id,
        provider,
        profile.connection_id,
        before.definition.ref,
        before.digest,
        profile.catalogue_url,
        profile.benchmark_url,
        observed_at,
        completed_at,
        models,
        warnings,
    )


_INFLIGHT: dict[tuple[asyncio.AbstractEventLoop, str, str, str, str], asyncio.Task] = {}


def assert_discovery_snapshot_current(snapshot: DiscoverySnapshot) -> None:
    """Recheck trusted refresh output at dispatch; this does not issue authority."""
    now = _now()
    if (
        now < snapshot.completed_at or now - snapshot.observed_at > timedelta(minutes=5)
        or snapshot.models.freshness != "fresh"
    ):
        raise ModelDiscoveryUnavailable("discovery_expired")
    current = _context(
        _base_path(), snapshot.owner_id, snapshot.universe_id,
        snapshot.provider.removeprefix("api_key_http:"),
    )
    if current.digest != snapshot.source_digest:
        raise ModelDiscoveryUnavailable("source_revoked")


async def refresh_model_discovery_async(
    *, owner_user_id: str, universe_id: str, definition_id: str
) -> DiscoverySnapshot:
    """Per-event-loop single-flight, no completed-result cache or blocking ingress.

    Cancelling a waiting caller does not cancel the broker worker or permit a
    replacement request before it settles. Separate server processes retain their
    own flights; neither this map nor a snapshot is an authority store.
    """
    loop = asyncio.get_running_loop()
    key = (loop, str(_base_path().resolve()), owner_user_id, universe_id, definition_id)
    task = _INFLIGHT.get(key)
    if task is None or task.done():
        task = asyncio.create_task(
            asyncio.to_thread(
                refresh_model_discovery,
                owner_user_id=owner_user_id,
                universe_id=universe_id,
                definition_id=definition_id,
            )
        )
        _INFLIGHT[key] = task

        def finished(done):
            if _INFLIGHT.get(key) is done:
                del _INFLIGHT[key]
            if not done.cancelled():
                done.exception()  # Retrieve failures even if every waiter cancelled.

        task.add_done_callback(finished)
    return await asyncio.shield(task)
