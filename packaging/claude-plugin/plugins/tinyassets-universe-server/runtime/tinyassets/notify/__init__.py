"""Server-owned notification transports, and the contract they answer.

Shaped on ``app_outbound_adapter``: the caller hands over a destination the
*server* resolved and a body the server composed, and the transport supplies
its own credential. No caller-supplied credential, URL, token or provider
override reaches here, and nothing in a request's content can name a
destination.

A transport raises exactly two things, both bounded:

* :class:`TransportGone` -- the destination no longer exists (FCM
  ``UNREGISTERED``, web push ``404``/``410``). The device is retired; a
  registration that is gone must not be retried forever.
* :class:`TransportFailed` -- anything else, carrying a fixed CLASS and never
  provider text. Exception text is where a credential leaks (four channels of
  it, historically), so the message is constructed here from a closed set
  rather than forwarded.

Configuration is env-var only, read through the secret loader in production:

* ``TINYASSETS_FCM_SERVICE_ACCOUNT_JSON`` -- the Firebase service-account JSON
  (the credential). Absent -> no Android transport.
* ``TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY`` / ``..._VAPID_SUBJECT`` -- the
  self-issued web-push keypair. Absent -> no web transport.

With neither set, :func:`resolve_transports` returns ``{}`` and dispatch
reports ``no_transport``. It does not fabricate a receipt, and it does not fail
the request that was raised: a request is durable and readable in the rail on
its own, so push is additive to it.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Protocol

logger = logging.getLogger(__name__)

#: Outcome classes recorded against a delivery. A closed set: a transport may
#: not invent one, so the ledger stays greppable and carries no provider text.
OUTCOME_SENT = "sent"
OUTCOME_GONE = "gone"
OUTCOME_REFUSED = "refused"
OUTCOME_UNAVAILABLE = "unavailable"
OUTCOME_NO_TRANSPORT = "no_transport"

FAILURE_CLASSES = frozenset({OUTCOME_REFUSED, OUTCOME_UNAVAILABLE})


class TransportGone(Exception):
    """The destination is gone. The device is retired, not retried."""


class TransportFailed(Exception):
    """A bounded failure. ``cls`` is one of :data:`FAILURE_CLASSES`."""

    def __init__(self, cls: str = OUTCOME_UNAVAILABLE) -> None:
        self.cls = cls if cls in FAILURE_CLASSES else OUTCOME_UNAVAILABLE
        super().__init__(self.cls)


@dataclass(frozen=True)
class Notification:
    """What the server decided to say. Composed in ``owner_notifications``.

    ``title`` is server-derived (the universe's own name); ``body`` is the
    agent's words, already stripped and bounded; ``data`` is identifiers only.
    A ``silent`` notification is the data-only clear that takes a notification
    off the owner's other devices -- it has no title or body at all.
    """

    title: str
    body: str
    data: dict[str, str] = field(default_factory=dict)
    silent: bool = False


class Transport(Protocol):
    def __call__(self, device: dict, notification: Notification) -> str:
        """Send, and return :data:`OUTCOME_SENT`. Raise otherwise."""


def resolve_transports(
    *, env: dict[str, str] | None = None,
) -> dict[str, Transport]:
    """The transports this deployment has credentials for, by platform.

    Empty when nothing is configured -- which is a truthful "push is not set
    up", never a stand-in that reports a delivery nothing made.
    """
    source = dict(os.environ if env is None else env)
    transports: dict[str, Transport] = {}
    if (source.get("TINYASSETS_FCM_SERVICE_ACCOUNT_JSON") or "").strip():
        from tinyassets.notify.fcm import fcm_transport

        try:
            transports["android"] = fcm_transport(source)
        except ValueError:
            # A malformed credential is a configuration fault, not a delivery
            # fault: say so once, loudly, and leave the platform unconfigured
            # rather than raising into whatever raised the request.
            logger.error(
                "notify: TINYASSETS_FCM_SERVICE_ACCOUNT_JSON is not a usable "
                "service-account document; Android push stays off"
            )
    if (source.get("TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY") or "").strip():
        from tinyassets.notify.webpush import webpush_transport

        try:
            transports["web"] = webpush_transport(source)
        except ValueError:
            logger.error(
                "notify: TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY is not a usable "
                "key; web push stays off"
            )
    return transports


#: Test seam. A test installs a fake here rather than reaching into a module
#: global mid-call, because a switch read from the environment inside
#: production code is a tests-only branch shipping to users.
TransportFactory = Callable[[], dict[str, Transport]]


__all__ = [
    "FAILURE_CLASSES",
    "OUTCOME_GONE",
    "OUTCOME_NO_TRANSPORT",
    "OUTCOME_REFUSED",
    "OUTCOME_SENT",
    "OUTCOME_UNAVAILABLE",
    "Notification",
    "Transport",
    "TransportFactory",
    "TransportFailed",
    "TransportGone",
    "resolve_transports",
]
