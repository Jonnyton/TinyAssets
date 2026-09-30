"""Installed connection-card data; all sources use api_key_http / openai_chat.

Verified 2026-09-30. No key, account tier or runtime vendor adapter lives here.
Models are an agent-capable allowlist intersected with the owner's /models
response at connection time, not an invented catalogue or a claim of access.
"""

from copy import deepcopy
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
_SOURCES = (
    {
        "id": "google_ai_studio", "name": "Google AI Studio",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "help_url": "https://aistudio.google.com/apikey",
        "billing_url": "https://aistudio.google.com/billing",
        "offer": ("Free tier on eligible Gemini models; project and model limits apply. "
                  "Daily requests reset at midnight Pacific."),
        "models": ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.1-flash-lite"],
        "daily_reset_timezone": "America/Los_Angeles",
    },
    {
        "id": "groq", "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "help_url": "https://console.groq.com/keys",
        "billing_url": "https://console.groq.com/settings/billing",
        "offer": ("Free plan, no credit card required. "
                  "Model-specific daily request and token limits apply."),
        "models": ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"],
        "daily_request_headers": True,
    },
    {
        "id": "cerebras", "name": "Cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "help_url": "https://cloud.cerebras.ai/platform/api-keys",
        "billing_url": "https://cloud.cerebras.ai",
        "offer": ("$5 trial credit expires after 30 days; a verified payment method is required. "
                  "No recurring free tier. Buy credit there only if you choose."),
        "models": ["gpt-oss-120b", "qwen-3.8-27b"],
    },
    {
        "id": "mistral", "name": "Mistral",
        "base_url": "https://api.mistral.ai/v1",
        "help_url": "https://console.mistral.ai/api-keys",
        "billing_url": "https://admin.mistral.ai/organization/billing",
        "offer": ("Free mode includes limited monthly usage, with no credit card required. "
                  "Current model limits appear in your account."),
        "models": ["mistral-small-latest"],
    },
)


def source_cards():
    return deepcopy(list(_SOURCES))


def source_preset(source_id):
    return next((row for row in source_cards() if row["id"] == source_id), None)


def source_for_host(host):
    return next((row for row in _SOURCES if urlsplit(row["base_url"]).netloc == host), {})


def billing_url_for_host(host):
    # Existing hosted acquisition presets also supply recovery links as data.
    import json
    from pathlib import Path

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
