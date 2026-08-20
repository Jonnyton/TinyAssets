"""Single-call outbound channels expressed as general ``http`` connections.

Channel-agnostic-outbound tracks 2 + 5: instead of a bespoke module per channel,
Slack ``chat.postMessage`` and X/Twitter ``POST /2/tweets`` each become a request
that the general credential-blind SSRF-hardened driver
(``storage/outbound_connections``) sends through a vault ``http`` credential + an
``OutboundEndpoint`` allowlist. Auth is applied INSIDE the broker child from the
connection's bundle (Bearer bot token for Slack; OAuth 1.0a signature for X) —
this module is credential-blind and only shapes the request.

The migration ORACLES are ``effectors/slack_transport.py`` and
``effectors/twitter_post.py``; the request builders here reproduce their
BYTE-IDENTICAL normalized wire request (endpoint, method, body, non-auth headers),
proven by the differential tests in ``tests/test_outbound_channel_migration.py``.
The oracles stay in place, each behind a per-channel readiness flag, until parity
is proven and the universe is atomically cut over — never two credential paths
live.
"""

from __future__ import annotations

import json
from typing import Any

# --- Slack ------------------------------------------------------------------ #
SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
#: The connection allowlist entry a Slack ``http`` connection must carry.
SLACK_ALLOWED_ENDPOINT: dict[str, Any] = {
    "host": "slack.com",
    "path_template": "/api/chat.postMessage",
    "methods": ["POST"],
}
#: Per-channel readiness flag: until truthy, Slack keeps posting through the
#: legacy ``slack_transport`` effector (no dual credential path).
SLACK_VIA_CONNECTION_FLAG = "TINYASSETS_SLACK_OUTBOUND_VIA_CONNECTION"

# --- X / Twitter ------------------------------------------------------------ #
TWITTER_TWEETS_URL = "https://api.x.com/2/tweets"
TWITTER_ALLOWED_ENDPOINT: dict[str, Any] = {
    "host": "api.x.com",
    "path_template": "/2/tweets",
    "methods": ["POST"],
}
TWITTER_VIA_CONNECTION_FLAG = "TINYASSETS_TWITTER_OUTBOUND_VIA_CONNECTION"


def slack_http_request(*, channel: str, text: str, thread_ts: str = "") -> dict[str, Any]:
    """The Slack ``chat.postMessage`` call as an ``http``-connection request.

    Byte-identical to ``slack_transport._post``: the body is ``json.dumps(payload)``
    with the stdlib's DEFAULT separators (``", "`` / ``": "``). The general driver's
    dict-body auto-encoding uses COMPACT separators, so we pass a pre-encoded string
    to reproduce Slack's spaced form exactly, and set ``Content-Type`` explicitly.
    The Bearer bot token is applied in the broker child (``auth_scheme="bearer"``).
    """
    payload: dict[str, Any] = {"channel": channel, "text": text}
    if isinstance(thread_ts, str) and thread_ts.strip():
        payload["thread_ts"] = thread_ts.strip()
    return {
        "url": SLACK_POST_MESSAGE_URL,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(payload),
    }


def twitter_http_request(
    *, text: str, reply_to_tweet_id: str = "", quote_tweet_id: str = ""
) -> dict[str, Any]:
    """The X/Twitter ``POST /2/tweets`` call as an ``http``-connection request.

    Byte-identical to ``twitter_post._post_tweet``: COMPACT JSON body and the same
    ``Accept``/``Content-Type``/``User-Agent`` headers. The OAuth 1.0a
    ``Authorization`` is signed in the broker child from the ``oauth1a`` bundle —
    never here (the adapter never sees the four OAuth secrets).
    """
    body: dict[str, Any] = {"text": text}
    if reply_to_tweet_id:
        body["reply"] = {"in_reply_to_tweet_id": reply_to_tweet_id}
    if quote_tweet_id:
        body["quote_tweet_id"] = quote_tweet_id
    return {
        "url": TWITTER_TWEETS_URL,
        "headers": {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "tinyassets-twitter-post-effector/1.0",
        },
        "body": json.dumps(body, separators=(",", ":")),
    }
