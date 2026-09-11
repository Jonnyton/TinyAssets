"""Frozen one-request transport from b7cd2a25 (before redirect deadline plumbing).

The leaf body is unchanged; existing pinned TLS/socket/read helpers are shared.
This oracle proves default leaf behavior, not a separate old daemon process.
"""
import socket
import time
import urllib.request
from typing import Any, Callable

from tinyassets.storage.outbound_connections import (
    ProxyRequestError,
    SsrfValidationError,
    _canonical_request_url,
    _CanonicalOutboundUrl,
    _looks_like_deadline_breach,
    _PinnedHTTPSHandler,
    _read_capped_body,
    _TotalDeadlineExceeded,
)


def _execute_pinned_https_request(
    *,
    method: str,
    canonical: _CanonicalOutboundUrl,
    pinned_address: str,
    headers: dict[str, str],
    body: bytes | None,
    ssl_context: Any,
    open_socket: Callable[..., socket.socket],
    timeout: float,
    max_total_seconds: float,
    max_body_bytes: int,
    max_header_count: int,
    max_header_bytes: int,
) -> dict[str, Any]:
    """Fire ONE request: no ambient proxies, no redirects, bounded response."""
    deadline = time.monotonic() + max_total_seconds
    url = _canonical_request_url(canonical)
    request = urllib.request.Request(url, data=body, method=method, headers=headers)

    opener = urllib.request.OpenerDirector()
    # Ambient/env proxies disabled (D3.5): an explicit empty proxy map, and the
    # opener is built by hand so no default env-proxy handler is ever installed.
    opener.add_handler(urllib.request.ProxyHandler({}))
    # No HTTPRedirectHandler and no HTTPErrorProcessor are added, so a 3xx is
    # returned as-is (never auto-followed) and non-2xx does not raise (D3.4).
    opener.add_handler(
        _PinnedHTTPSHandler(
            context=ssl_context,
            pinned_address=pinned_address,
            open_socket=open_socket,
            deadline=deadline,
        )
    )

    response = None
    deadline_exceeded = False
    try:
        # Cap connect + header phase at the smaller of the per-op timeout and the
        # remaining total budget; the socket-layer deadline (_DeadlineSocket)
        # additionally bounds the status-line + header parse against the total.
        response = opener.open(request, timeout=min(timeout, max_total_seconds))
    except _TotalDeadlineExceeded:
        deadline_exceeded = True
    except SsrfValidationError:
        raise
    except Exception as exc:
        # A deadline breach during the status-line/header parse surfaces as a
        # urllib-wrapped TimeoutError (opener.open does not re-wrap getresponse),
        # so the bare _TotalDeadlineExceeded above misses it — recognize it here
        # so every phase's breach is labeled as the deadline, not a generic fail.
        if _looks_like_deadline_breach(exc, deadline):
            deadline_exceeded = True
        else:
            response = None
    if deadline_exceeded:
        # Raised OUTSIDE the except block: a fixed, secret-free message with a
        # clean __context__.
        raise SsrfValidationError("outbound request exceeded the total deadline")
    if response is None:
        # Raised OUTSIDE the except block on purpose: `raise ... from None` still
        # leaves ``__context__`` populated (readable via ``exc.__context__`` — the
        # Authorization-echo leak class, where a URLError/BadStatusLine can quote
        # the reflected Authorization header). Raising here clears it.
        raise ProxyRequestError("outbound request failed at destination")

    # Collect the sanitized result (or a bound-violation reason) inside the
    # try, but raise only AFTER the block so no server-controlled exception can
    # ride out on ``__context__``.
    sanitized: dict[str, Any] | None = None
    bound_violation: str | None = None
    read_deadline_exceeded = False
    try:
        status = int(response.status)
        reason = str(getattr(response, "reason", "") or "")
        raw_headers = list(response.getheaders())
        if len(raw_headers) > max_header_count:
            bound_violation = "outbound response has too many headers"
        elif sum(len(str(k)) + len(str(v)) for k, v in raw_headers) > max_header_bytes:
            bound_violation = "outbound response headers exceed the bound"
        else:
            declared = response.getheader("Content-Length")
            declared_ok = True
            if declared is not None:
                try:
                    declared_ok = int(declared) <= max_body_bytes
                except (TypeError, ValueError):
                    declared_ok = True
            if not declared_ok:
                bound_violation = "outbound response exceeds the size bound"
            else:
                body_bytes = _read_capped_body(response, max_body_bytes)
                if body_bytes is None:
                    bound_violation = "outbound response exceeds the size bound"
                else:
                    sanitized = {
                        "status": status,
                        "reason": reason,
                        "headers": {
                            str(name).lower(): str(value)
                            for name, value in raw_headers
                        },
                        "body": body_bytes.decode("utf-8", errors="replace"),
                    }
    except _TotalDeadlineExceeded:
        read_deadline_exceeded = True
    except Exception as exc:
        # A deadline breach during the body / chunked-trailer read can also surface
        # as a TimeoutError from the tightened socket timeout — label it as the
        # deadline (fail-closed) rather than a generic destination failure, exactly
        # as the header-phase handler does.
        if _looks_like_deadline_breach(exc, deadline):
            read_deadline_exceeded = True
        else:
            sanitized = None
            bound_violation = None
    finally:
        try:
            response.close()
        except Exception:
            pass

    if read_deadline_exceeded:
        raise SsrfValidationError("outbound request exceeded the total deadline")
    if bound_violation is not None:
        raise SsrfValidationError(bound_violation)
    if sanitized is None:
        raise ProxyRequestError("outbound request failed at destination")
    return sanitized
