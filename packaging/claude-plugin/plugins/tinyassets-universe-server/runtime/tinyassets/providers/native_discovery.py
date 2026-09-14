"""Owned native metadata lifecycle; advisory only, never launch authority.

The caller checks the accepted member before and after this IO. This boundary
additionally pins the current deposited credential owner/generation, copies it
for one metadata process, and removes the copy on every exit. No SQL transaction
or assignment admission lock may be held by the caller across enumeration.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tinyassets.credential_vault import (
    LLMCredentialCustodyReference,
    cleanup_llm_credential_snapshot,
    current_llm_subscription_custody,
    snapshot_llm_subscription_credential,
)
from tinyassets.exceptions import ProviderError
from tinyassets.providers.native_catalogue import NativeCatalogue
from tinyassets.storage.provider_work_authority import SQLiteProviderWorkAuthorityStore


def _custody(base, universe, owner, service):
    with SQLiteProviderWorkAuthorityStore(base).connection() as conn:
        conn.execute("BEGIN")
        return current_llm_subscription_custody(
            conn, universe_dir=universe, owner_user_id=owner,
            universe_id=universe.name, service=service,
        )


@dataclass(frozen=True, slots=True)
class NativeDiscoverySnapshot:
    provider: str
    owner_id: str
    universe: Path
    custody: LLMCredentialCustodyReference = field(repr=False)
    observed_at: datetime
    completed_at: datetime
    catalogue: NativeCatalogue

    def assert_current(self):
        now = datetime.now(timezone.utc)
        if (now < self.completed_at or now - self.observed_at > timedelta(minutes=5)
                or _custody(self.universe.parent, self.universe, self.owner_id,
                            self.custody.service) != self.custody):
            raise ProviderError("native model discovery expired or source changed")


async def refresh_native_catalogue(
    provider, *, universe_dir, owner_user_id, expected_custody,
):
    """Discover through the registered executor, with exact current custody.

    Unknown enumeration is None, not a synthesized complete catalogue. The
    service identifier is executor registration metadata, not a release table.
    A supplied custody object grants nothing: compare it to the current store
    before copying credentials and again after the subprocess has finished.
    """
    snapshot = None
    try:
        universe = Path(universe_dir).resolve(strict=True)
        if (type(expected_custody) is not LLMCredentialCustodyReference
                or expected_custody.owner_user_id != owner_user_id
                or expected_custody.universe_id != universe.name
                or not provider.native_credential_service
                or provider.native_credential_service != expected_custody.service
                or _custody(universe.parent, universe, owner_user_id,
                            expected_custody.service) != expected_custody):
            raise PermissionError("native discovery custody mismatch")
        observed = datetime.now(timezone.utc)
        snapshot = snapshot_llm_subscription_credential(
            universe_dir=universe, custody=expected_custody,
        )
        catalogue = await provider.enumerate_models(
            universe_dir=universe, credential_snapshot_dir=snapshot.directory,
        )
        if catalogue is None:
            return None
        if type(catalogue) is not NativeCatalogue:
            raise ValueError("executor returned invalid native metadata")
        completed = datetime.now(timezone.utc)
        if not observed <= catalogue.observed_at <= completed:
            raise ValueError("executor returned cached or future native metadata")
        result = NativeDiscoverySnapshot(
            provider.name, owner_user_id, universe, expected_custody,
            observed, completed, catalogue,
        )
        result.assert_current()
        return result
    except (OSError, ValueError, PermissionError, ProviderError):
        raise ProviderError("owned native model discovery unavailable") from None
    finally:
        cleanup_llm_credential_snapshot(snapshot)
