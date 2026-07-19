"""Host-pool registration — tray startup flow.

Wave 1 per Track D: on tray startup, create a ``host_pool`` row with
the daemon's declared capabilities + visibility. Returns the new
``host_id`` which the caller holds for the session (heartbeat +
deregistration target).

The control plane derives row ownership from the authenticated daemon. The
client never submits or logs a caller-asserted owner identity.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from tinyassets.host_pool.client import HostPoolClient, HostPoolRow, _UrllibClient
from tinyassets.runtime.daemon_auth import AccessToken, DaemonSigner

logger = logging.getLogger(__name__)


class _EnrollmentHttpClient(Protocol):
    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout: float,
    ) -> tuple[int, str]: ...


class DaemonEnrollmentError(Exception):
    """Typed enrollment transport/control-plane failure."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        request_id: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.retryable = retryable
        self.request_id = request_id
        self.details = details or {}


@dataclass(frozen=True)
class EnrollmentVerificationHandoff:
    enrollment_id: str
    verification_code: str


@dataclass(frozen=True)
class EnrolledDaemon:
    daemon_id: str
    owner_user_id: str
    key_thumbprint: str
    credential_epoch: int


class DaemonEnrollmentClient:
    """Client for owner-approved daemon enrollment and token exchange."""

    def __init__(
        self,
        control_plane_url: str,
        *,
        http: _EnrollmentHttpClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not isinstance(control_plane_url, str) or not control_plane_url.startswith("https://"):
            raise DaemonEnrollmentError(
                0,
                "CONTROL_PLANE_URL_INVALID",
                "control_plane_url must use HTTPS",
            )
        self._base = control_plane_url.rstrip("/")
        self._http = http or _UrllibClient()
        self._timeout = timeout

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        status, text = self._http.request(
            "POST",
            f"{self._base}{path}",
            {"Content-Type": "application/json", "Accept": "application/json"},
            body,
            self._timeout,
        )
        try:
            response = json.loads(text) if text else {}
        except json.JSONDecodeError as exc:
            raise DaemonEnrollmentError(
                status,
                "INVALID_RESPONSE",
                "Invalid control-plane JSON",
            ) from exc
        if status < 200 or status >= 300:
            error = response.get("error", {}) if isinstance(response, dict) else {}
            raise DaemonEnrollmentError(
                status,
                str(error.get("code", "CONTROL_PLANE_ERROR")),
                str(error.get("message", "Control-plane request failed")),
                retryable=error.get("retryable") is True,
                request_id=str(error.get("request_id", "")),
                details=error.get("details") if isinstance(error.get("details"), dict) else {},
            )
        if not isinstance(response, dict):
            raise DaemonEnrollmentError(status, "INVALID_RESPONSE", "Expected a JSON object")
        return response

    def begin(self, signer: DaemonSigner) -> EnrollmentVerificationHandoff:
        response = self._post(
            "/v1/daemon-enrollments",
            signer.identity.as_enrollment_payload(),
        )
        try:
            return EnrollmentVerificationHandoff(
                enrollment_id=str(response["enrollment_id"]),
                verification_code=str(response["verification_code"]),
            )
        except KeyError as exc:
            raise DaemonEnrollmentError(
                0,
                "INVALID_RESPONSE",
                "Enrollment handoff is incomplete",
            ) from exc

    def complete(self, enrollment_id: str) -> EnrolledDaemon:
        if not enrollment_id:
            raise DaemonEnrollmentError(0, "ENROLLMENT_ID_REQUIRED", "enrollment_id is required")
        response = self._post(f"/v1/daemon-enrollments/{enrollment_id}:complete", {})
        try:
            return EnrolledDaemon(
                daemon_id=str(response["daemon_id"]),
                owner_user_id=str(response["owner_user_id"]),
                key_thumbprint=str(response["key_thumbprint"]),
                credential_epoch=int(response["credential_epoch"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DaemonEnrollmentError(
                0,
                "INVALID_RESPONSE",
                "Enrollment result is incomplete",
            ) from exc

    def issue_access_token(self, signer: DaemonSigner, daemon_id: str) -> AccessToken:
        challenge_response = self._post(
            "/v1/daemon-access-tokens/challenge",
            {"daemon_id": daemon_id},
        )
        try:
            challenge = str(challenge_response["challenge"])
        except KeyError as exc:
            raise DaemonEnrollmentError(
                0,
                "INVALID_RESPONSE",
                "Challenge response is incomplete",
            ) from exc
        token_response = self._post(
            "/v1/daemon-access-tokens",
            {
                "daemon_id": daemon_id,
                "challenge": challenge,
                "signature": signer.sign_challenge(daemon_id, challenge),
            },
        )
        try:
            token = AccessToken(
                value=str(token_response["access_token"]),
                daemon_id=str(token_response["daemon_id"]),
                key_thumbprint=str(token_response["key_thumbprint"]),
                credential_epoch=int(token_response["credential_epoch"]),
                expires_at=float(token_response["expires_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DaemonEnrollmentError(
                0,
                "INVALID_RESPONSE",
                "Access-token response is incomplete",
            ) from exc
        if token_response.get("token_type") != "Bearer":
            raise DaemonEnrollmentError(0, "INVALID_RESPONSE", "Access-token type must be Bearer")
        if token.daemon_id != daemon_id or token.key_thumbprint != signer.identity.key_thumbprint:
            raise DaemonEnrollmentError(
                0,
                "TOKEN_BINDING_MISMATCH",
                "Access token binding is invalid",
            )
        if token.credential_epoch < 1:
            raise DaemonEnrollmentError(0, "TOKEN_BINDING_MISMATCH", "Credential epoch is invalid")
        return token


@dataclass
class Registration:
    """What a caller gets back from ``register_daemon``.

    ``row`` is the authoritative row state (insertion OR pre-existing).
    ``created`` tells the caller whether this invocation inserted a new
    row (True) or reused an existing one (False). Useful for log lines.
    """

    row: HostPoolRow
    created: bool


def register_daemon(
    client: HostPoolClient,
    *,
    provider: str,
    capability_id: str,
    visibility: str = "self",
    price_floor: float | None = None,
    max_concurrent: int = 1,
    always_active: bool = False,
    # Capability-row auto-provisioning (per Track A §7 OPEN resolution).
    capability_node_type: str | None = None,
    capability_llm_model: str | None = None,
    capability_description: str | None = None,
) -> Registration:
    """Ensure the daemon is registered. Return its host_pool row.

    Behavior:
        1. Ensure the capability row exists (insert-if-missing). If the
           caller didn't pass node_type + llm_model, we derive them by
           splitting ``capability_id`` on the first ``:`` — matches the
           shape ``<node_type>:<llm_model>`` Track A uses as canonical.
        2. Insert a new ``host_pool`` row. Returns it.

    We do NOT look up pre-existing rows by owner+capability then skip
    insert — schema has no unique on (owner, capability), so multiple
    rows per (user, capability) are legal (e.g. two daemons on the same
    box with different max_concurrent). Callers that want singleton
    semantics should track the host_id themselves between runs.
    """
    node_type = capability_node_type
    llm_model = capability_llm_model
    if node_type is None or llm_model is None:
        # Split ``node_type:llm_model`` — matches canonical capability_id
        # shape. Fall back to the whole capability_id as node_type if
        # there's no colon (defensive; callers should supply explicit
        # values when capability_id doesn't parse).
        if ":" in capability_id:
            default_node, default_llm = capability_id.split(":", 1)
        else:
            default_node, default_llm = capability_id, "unknown"
        node_type = node_type or default_node
        llm_model = llm_model or default_llm

    client.ensure_capability(
        capability_id,
        node_type=node_type,
        llm_model=llm_model,
        description=capability_description,
    )

    row = client.register(
        provider=provider,
        capability_id=capability_id,
        visibility=visibility,
        price_floor=price_floor,
        max_concurrent=max_concurrent,
        always_active=always_active,
    )
    logger.info(
        "host_pool: registered host_id=%s owner=%s capability=%s visibility=%s",
        row.host_id,
        row.owner_user_id,
        capability_id,
        visibility,
    )
    return Registration(row=row, created=True)
