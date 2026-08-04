"""Credential-blind, idempotent delivery of founder-authorized app replies.

This module is a dark boundary: it does not expose an MCP handle or choose a
transport. A later server-owned Slack adapter supplies the injected callback.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tinyassets.app_reply_authority import AppReplyAuthorization, ReplyDestination

_BODY_DOMAIN = b"app-reply/body/v1\0"
_RECEIPT_DOMAIN = b"app-reply/transport-receipt/v1\0"
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_BODY_BYTES = 64 * 1024
_MAX_RECEIPT_REF_BYTES = 512


class AppOutboundDeliveryError(PermissionError):
    """A reply could not be delivered through the governed app boundary."""


@dataclass(frozen=True, slots=True)
class AppTransportReceipt:
    """Opaque server-owned transport result; never contains response content."""

    provider_receipt_ref: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.provider_receipt_ref, str)
            or not self.provider_receipt_ref.strip()
            or self.provider_receipt_ref != self.provider_receipt_ref.strip()
        ):
            raise ValueError("provider_receipt_ref must be canonical text")
        if len(self.provider_receipt_ref.encode("utf-8")) > _MAX_RECEIPT_REF_BYTES:
            raise ValueError("provider_receipt_ref is too large")


@dataclass(frozen=True, slots=True)
class AppOutboundReceipt:
    idempotency_key: str
    authorization_digest: str
    response_digest: str
    destination: ReplyDestination
    transport_receipt_digest: str | None
    status: str
    failure_class: str | None
    replay: bool


Transport = Callable[[ReplyDestination, str], AppTransportReceipt]


class AppOutboundAdapter:
    """Deliver an authorized response through a server-owned transport."""

    def __init__(
        self,
        base_path: str | Path,
        transport: Transport,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not callable(transport):
            raise TypeError("transport must be a server-owned callable")
        self._path = Path(base_path) / "app_outbound_receipts.db"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._transport = transport
        self._clock = clock
        self._delivery_lock = threading.RLock()
        self._initialize()

    def deliver(
        self,
        authorization: AppReplyAuthorization,
        response: str,
    ) -> AppOutboundReceipt:
        with self._delivery_lock:
            if type(authorization) is not AppReplyAuthorization:
                raise AppOutboundDeliveryError("reply authorization is invalid")
            if not _DIGEST.fullmatch(authorization.authorization_digest):
                raise AppOutboundDeliveryError("authorization digest is invalid")
            response_digest = body_digest(response)
            if response_digest != authorization.response_digest:
                raise AppOutboundDeliveryError("response digest does not match authorization")
            key = f"app-reply:{authorization.authorization_digest}"
            row = self._reserve(key, authorization, response_digest)
            if row is not None:
                return self._receipt_from_row(row, replay=True)
            try:
                result = self._transport(authorization.destination, response)
                if type(result) is not AppTransportReceipt:
                    raise TypeError("transport returned an invalid receipt")
                receipt_digest = _receipt_digest(result.provider_receipt_ref)
            except Exception as exc:
                self._fail(key, authorization, response_digest, _failure_class(exc))
                raise AppOutboundDeliveryError("app reply delivery failed") from exc
            self._complete(key, authorization, response_digest, receipt_digest)
            return AppOutboundReceipt(
                idempotency_key=key,
                authorization_digest=authorization.authorization_digest,
                response_digest=response_digest,
                destination=authorization.destination,
                transport_receipt_digest=receipt_digest,
                status="succeeded",
                failure_class=None,
                replay=False,
            )

    def _initialize(self) -> None:
        with sqlite3.connect(self._path) as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS app_outbound_receipts (
                    idempotency_key TEXT PRIMARY KEY,
                    authorization_digest TEXT NOT NULL,
                    response_digest TEXT NOT NULL,
                    destination_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    transport_receipt_digest TEXT,
                    failure_class TEXT,
                    created_at REAL NOT NULL,
                    completed_at REAL
                )
                """
            )

    def _reserve(
        self,
        key: str,
        authorization: AppReplyAuthorization,
        response_digest: str,
    ) -> sqlite3.Row | None:
        destination_json = _destination_json(authorization.destination)
        with sqlite3.connect(self._path, timeout=30) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM app_outbound_receipts WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            if row is not None:
                if (
                    row["authorization_digest"] != authorization.authorization_digest
                    or row["response_digest"] != response_digest
                    or row["destination_json"] != destination_json
                ):
                    raise AppOutboundDeliveryError("idempotency key is bound to another reply")
                if row["status"] != "succeeded":
                    raise AppOutboundDeliveryError("previous app reply delivery failed")
                return row
            db.execute(
                """
                INSERT INTO app_outbound_receipts (
                    idempotency_key, authorization_digest, response_digest,
                    destination_json, status, created_at
                ) VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (
                    key,
                    authorization.authorization_digest,
                    response_digest,
                    destination_json,
                    self._clock(),
                ),
            )
            return None

    def _complete(
        self,
        key: str,
        authorization: AppReplyAuthorization,
        response_digest: str,
        receipt_digest: str,
    ) -> None:
        with sqlite3.connect(self._path) as db:
            updated = db.execute(
                """
                UPDATE app_outbound_receipts
                SET status = 'succeeded', transport_receipt_digest = ?, completed_at = ?
                WHERE idempotency_key = ? AND authorization_digest = ?
                  AND response_digest = ? AND status = 'pending'
                """,
                (
                    receipt_digest,
                    self._clock(),
                    key,
                    authorization.authorization_digest,
                    response_digest,
                ),
            ).rowcount
            if updated != 1:
                raise AppOutboundDeliveryError("app reply receipt could not be finalized")

    def _fail(
        self,
        key: str,
        authorization: AppReplyAuthorization,
        response_digest: str,
        failure_class: str,
    ) -> None:
        with sqlite3.connect(self._path) as db:
            db.execute(
                """
                UPDATE app_outbound_receipts
                SET status = 'failed', failure_class = ?, completed_at = ?
                WHERE idempotency_key = ? AND authorization_digest = ?
                  AND response_digest = ? AND status = 'pending'
                """,
                (
                    failure_class,
                    self._clock(),
                    key,
                    authorization.authorization_digest,
                    response_digest,
                ),
            )

    def _receipt_from_row(self, row: sqlite3.Row, *, replay: bool) -> AppOutboundReceipt:
        destination = _destination_from_json(row["destination_json"])
        return AppOutboundReceipt(
            idempotency_key=row["idempotency_key"],
            authorization_digest=row["authorization_digest"],
            response_digest=row["response_digest"],
            destination=destination,
            transport_receipt_digest=row["transport_receipt_digest"],
            status=row["status"],
            failure_class=row["failure_class"],
            replay=replay,
        )


def body_digest(response: str) -> str:
    if not isinstance(response, str) or not response.strip() or response != response.strip():
        raise AppOutboundDeliveryError("response must be canonical non-empty text")
    encoded = response.encode("utf-8")
    if len(encoded) > _MAX_BODY_BYTES:
        raise AppOutboundDeliveryError("response exceeds the delivery bound")
    return "sha256:" + hashlib.sha256(_BODY_DOMAIN + encoded).hexdigest()


def _receipt_digest(provider_receipt_ref: str) -> str:
    encoded = provider_receipt_ref.encode("utf-8")
    return "sha256:" + hashlib.sha256(_RECEIPT_DOMAIN + encoded).hexdigest()


def _failure_class(exc: BaseException) -> str:
    if isinstance(exc, (TypeError, ValueError)):
        return "invalid_transport_receipt"
    return "transport_failure"


def _destination_json(destination: ReplyDestination) -> str:
    return json.dumps(
        {
            "address": destination.address,
            "connection_id": destination.connection_id,
            "provider": destination.provider,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _destination_from_json(value: str) -> ReplyDestination:
    try:
        payload = json.loads(value)
        return ReplyDestination(
            provider=payload["provider"],
            connection_id=payload["connection_id"],
            address=payload["address"],
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppOutboundDeliveryError("stored destination is invalid") from exc


__all__ = [
    "AppOutboundAdapter",
    "AppOutboundDeliveryError",
    "AppOutboundReceipt",
    "AppTransportReceipt",
    "body_digest",
]
