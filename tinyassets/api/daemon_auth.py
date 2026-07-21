"""FastAPI dependency for exact daemon proof-of-possession authentication."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from tinyassets.api.daemon_enrollment import (
    AuthenticatedDaemon,
    DaemonApiError,
    DaemonEnrollmentService,
)
from tinyassets.runtime.daemon_auth import ACTION_AFFECTING_HEADERS


class DaemonRequestAuthDependency:
    """Authenticate the exact ASGI request target, headers, and body.

    S3 intentionally delivers this dependency independently of operation routes.
    The B2 operation endpoints in S4 must mount it rather than reconstructing or
    partially forwarding request data themselves.
    """

    def __init__(
        self,
        service: DaemonEnrollmentService,
        *,
        owner_resolver: Callable[[Request], str],
    ) -> None:
        self._service = service
        self._owner_resolver = owner_resolver

    async def __call__(self, request: Request) -> AuthenticatedDaemon:
        try:
            method = request.scope.get("method")
            if (
                not isinstance(method, str)
                or not method
                or method != method.upper()
                or not method.isascii()
            ):
                raise DaemonApiError(
                    400,
                    "MALFORMED_REQUEST",
                    "HTTP method must use canonical uppercase spelling",
                )
            raw_path = request.scope.get("raw_path")
            raw_query = request.scope.get("query_string")
            if not isinstance(raw_path, bytes) or not raw_path.startswith(b"/"):
                raise DaemonApiError(400, "MALFORMED_REQUEST", "Raw request path is required")
            if not isinstance(raw_query, bytes):
                raise DaemonApiError(400, "MALFORMED_REQUEST", "Raw query string is required")

            headers: dict[str, str] = {}
            for raw_name, raw_value in request.scope.get("headers", []):
                try:
                    name = raw_name.decode("ascii").lower()
                    value = raw_value.decode("latin-1")
                except (AttributeError, UnicodeDecodeError) as exc:
                    raise DaemonApiError(
                        401, "INVALID_AUTHENTICATION", "Authentication failed"
                    ) from exc
                if name in headers and name in ACTION_AFFECTING_HEADERS:
                    raise DaemonApiError(
                        401,
                        "INVALID_AUTHENTICATION",
                        "Duplicate action-affecting headers are forbidden",
                    )
                headers[name] = value

            owner_user_id: Any = self._owner_resolver(request)
            if inspect.isawaitable(owner_user_id):
                owner_user_id = await owner_user_id
            if not isinstance(owner_user_id, str) or not owner_user_id.strip():
                raise DaemonApiError(401, "INVALID_AUTHENTICATION", "Authentication failed")

            return self._service.verify_headers(
                method,
                raw_path.decode("latin-1"),
                raw_query.decode("latin-1"),
                headers,
                await request.body(),
                expected_owner_user_id=owner_user_id,
            )
        except DaemonApiError as exc:
            raise exc


async def _daemon_api_error_response(request: Request, exc: DaemonApiError) -> JSONResponse:
    del request
    return JSONResponse(exc.as_dict(), status_code=exc.status)


def install_daemon_request_auth(
    app: FastAPI,
    service: DaemonEnrollmentService,
    *,
    owner_resolver: Callable[[Request], str],
) -> DaemonRequestAuthDependency:
    """Install the standard error handler and return the S4 route dependency."""
    app.add_exception_handler(DaemonApiError, _daemon_api_error_response)
    return DaemonRequestAuthDependency(service, owner_resolver=owner_resolver)


__all__ = ["DaemonRequestAuthDependency", "install_daemon_request_auth"]
