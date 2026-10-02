"""Installed connection-card data; all sources use api_key_http / openai_chat.

Verified 2026-09-30. No key, account tier or runtime vendor adapter lives here.
Models are an agent-capable allowlist intersected with the owner's /models
response at connection time, not an invented catalogue or a claim of access.
"""

import json
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

# Endpoint, keys, free eligibility and model docs:
# https://ai.google.dev/gemini-api/docs/openai
# https://ai.google.dev/gemini-api/docs/api-key
# https://ai.google.dev/gemini-api/docs/pricing
# https://console.groq.com/docs/openai
# https://console.groq.com/docs/quickstart
# https://console.groq.com/docs/rate-limits
# https://inference-docs.cerebras.ai/resources/openai
# https://inference-docs.cerebras.ai/api-reference/models/list-models
# https://inference-docs.cerebras.ai/support/rate-limits
# https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key
# https://docs.mistral.ai/api/endpoint/models
# https://docs.mistral.ai/admin/billing-usage/usage-limits
_SOURCES = json.loads(Path(__file__).with_name("free_source_presets.json").read_text("utf-8"))


def source_cards():
    return deepcopy(list(_SOURCES))


def source_preset(source_id):
    return next((row for row in source_cards() if row["id"] == source_id), None)


# TEMPORARY until feat/connect-free-ai lands: same signature
def daily_cap_for_host(host):
    """Read connect-screen's installed daily caps, never acquisition metadata."""
    source = next((row for row in _SOURCES if urlsplit(row["base_url"]).netloc == host), {})
    cap = source.get("daily_cap")
    if cap:
        return {
            "requests_per_day": cap.get("requests_per_day"),
            "credit_requests_per_day": None,
            "reset_timezone": cap.get("reset_timezone"),
            "name": source["name"],
            "credit_url": source.get("billing_url", ""),
        }
    offers = json.loads(Path(__file__).with_name("daily_cap_offers.json").read_text("utf-8"))
    offer = offers.get(host)
    if offer is None:
        return None
    return {
        "requests_per_day": offer["free_requests_per_day"],
        "credit_requests_per_day": offer.get("credit_requests_per_day"),
        "reset_timezone": offer["reset_timezone"],
        "name": offer["name"],
        "credit_url": offer.get("credit_url", ""),
    }


def source_for_host(host):
    source = next((row for row in _SOURCES if urlsplit(row["base_url"]).netloc == host), None)
    if source is not None:
        return deepcopy(source)
    presets = json.loads(Path(__file__).with_name("acquisition_presets.json").read_text("utf-8"))
    return next((row for row in presets.values()
                 if urlsplit(row["inference_url"]).netloc == host), {})


def billing_url_for_host(host):
    # Existing hosted acquisition presets also supply recovery links as data.
    source = source_for_host(host)
    if source:
        return source["billing_url"]
    presets = json.loads(Path(__file__).with_name("acquisition_presets.json").read_text("utf-8"))
    return next((row.get("billing_url", row["manage_url"]) for row in presets.values()
                 if urlsplit(row["inference_url"]).netloc == host), "")


def discovered_agent_models(preset, payload):
    """Bound supported chat/tool ids by the authenticated catalogue's membership.

    These APIs don't all report tools/context in /models. The preset allowlist
    establishes tool support; 32768 is a conservative local admission bound.
    No catalogue price is fabricated and no fetched URL or code is executed.
    """
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError("model catalogue is unavailable")
    ids = {row.get("id") for row in rows if isinstance(row, dict)
           and isinstance(row.get("id"), str) and row.get("active", True) is not False}
    models = [{"id": mid, "tools": True, "context": 32768}
              for mid in preset["models"] if mid in ids]
    if not models:
        raise ValueError("this key offers no supported agent model; check its model access")
    return models
