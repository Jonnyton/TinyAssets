"""Server-owned Slack transport for founder-authorized app replies.

`app_outbound_adapter` is deliberately credential-blind: it owns idempotency,
locking and receipt shape, and takes an injected
``Transport = Callable[[ReplyDestination, str], AppTransportReceipt]``. Its
module docstring has said since it landed that "a later server-owned Slack
adapter supplies the injected callback". This is that callback.

Three properties this module exists to hold:

- **The credential never crosses the boundary.** The transport resolves its own
  bot token from the per-universe vault. No caller passes one in, and no caller
  can name one. This mirrors ``effectors/github_pr`` exactly.
- **Vault-bound universes never fall through to host env.** An empty vault means
  "this universe is not authorized", not "borrow the maintainer's token" — the
  ambient-credential failure the platform has already been bitten by.
- **The receipt carries no content.** ``AppTransportReceipt`` is an opaque
  server-owned reference; the Slack message ``ts`` is an identifier, not text.
  Reply bodies must not round-trip back through the boundary.

Stdlib only (``urllib``): no Slack SDK dependency for one POST.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from tinyassets.app_outbound_adapter import AppTransportReceipt
from tinyassets.app_reply_authority import ReplyDestination
from tinyassets.effectors.slack_errors import safe_error_code

#: Slack Web API endpoint for posting a message. Kept a module constant so
#: tests can point it at a local stub without monkeypatching urllib globally.
SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"

#: Slack rejects oversized posts; bound the body before we spend a round trip.
_MAX_BODY_BYTES = 40_000

_DEFAULT_TIMEOUT_SECONDS = 15.0


class SlackTransportError(RuntimeError):
    """The reply could not be delivered to Slack.

    Deliberately carries no message body and no credential — it is raised
    across the governed boundary, and `app_outbound_adapter` wraps it into
    `AppOutboundDeliveryError`.
    """


def resolve_slack_bot_token(
    universe_dir: str | Path | None,
    connection_id: str,
) -> str:
    """Return the Slack bot token for one connection, or an empty string.

    Vault-first, and a vault-bound universe never falls through to the process
    environment: an empty vault means this universe is not authorized, not
    "look at the host env". Never echoed into caller-visible evidence.
    """
    if universe_dir is None or not connection_id.strip():
        return ""
    from tinyassets.credential_vault import resolve_slack_token, vault_exists

    token = resolve_slack_token(universe_dir, connection_id.strip())
    if token or vault_exists(universe_dir):
        return token
    return ""


def _post(url: str, payload: dict[str, Any], token: str, timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 - fixed https Slack endpoint
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw = response.read()
    except urllib.error.HTTPError as exc:  # pragma: no cover - network shape
        raise SlackTransportError(f"slack transport http {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        # `from None`, not `from exc`: a URLError's message routinely quotes
        # the Authorization header, and chaining wrote the bot token into any
        # traceback. A cross-family review reproduced exactly that here.
        raise SlackTransportError("slack transport unreachable") from None
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001 - decode errors and hostile nesting alike
        raise SlackTransportError("slack transport returned malformed JSON") from None
    if not isinstance(decoded, dict):
        raise SlackTransportError("slack transport returned a non-object response")
    return decoded


def build_slack_transport(
    universe_dir: str | Path | None,
    *,
    url: str = SLACK_POST_MESSAGE_URL,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
):
    """Build the injected ``Transport`` callable for `app_outbound_adapter`.

    The returned callable takes ``(ReplyDestination, str)`` and returns an
    ``AppTransportReceipt`` whose ``provider_receipt_ref`` is the Slack message
    identifier — never the message text.
    """

    def _transport(
        destination: ReplyDestination,
        body: str,
        *,
        thread_ts: str = "",
    ) -> AppTransportReceipt:
        # `thread_ts` is keyword-only with a default so the two-positional-arg
        # `Transport` contract `app_outbound_adapter` calls remains exactly as
        # it was. Answering in the thread the question was asked in is the
        # difference between a conversation and a channel full of loose replies.
        if destination.provider != "slack":
            raise SlackTransportError("slack transport received a non-slack destination")
        text = body if isinstance(body, str) else ""
        if not text.strip():
            raise SlackTransportError("refusing to deliver an empty reply")
        if len(text.encode("utf-8")) > _MAX_BODY_BYTES:
            raise SlackTransportError("reply body exceeds the slack transport bound")

        token = resolve_slack_bot_token(universe_dir, destination.connection_id)
        if not token:
            # Fail closed. A missing credential must never degrade into
            # "deliver with whatever token happens to be around".
            raise SlackTransportError(
                "no requester-owned slack credential for this connection"
            )

        payload: dict[str, Any] = {"channel": destination.address, "text": text}
        if isinstance(thread_ts, str) and thread_ts.strip():
            payload["thread_ts"] = thread_ts.strip()
        decoded = _post(url, payload, token, timeout)
        if not decoded.get("ok"):
            # Slack reports failure in-band with HTTP 200. Surface the error
            # CODE only — never the echoed message payload Slack returns.
            code = safe_error_code(decoded.get("error"), default="unknown_error")
            raise SlackTransportError(f"slack rejected the reply: {code}")

        receipt_ref = str(decoded.get("ts") or "").strip()
        if not receipt_ref:
            raise SlackTransportError("slack accepted the reply without an identifier")
        channel = str(decoded.get("channel") or destination.address).strip()
        return AppTransportReceipt(provider_receipt_ref=f"slack:{channel}:{receipt_ref}")

    return _transport
