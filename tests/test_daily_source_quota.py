"""Provider error envelopes: daily quota is evidence, never guessed from 429."""

import json
from datetime import UTC, datetime

import pytest

from tinyassets.providers.daily_quota import DAILY_QUOTA, daily_detail, daily_quota_signal
from tinyassets.providers.model_capacity import free_sibling_retry

NOW = datetime(2026, 9, 30, 12, tzinfo=UTC)
RESET = int(NOW.timestamp() + 43200) * 1000


@pytest.mark.parametrize("body,headers,delay", [
    ({"error": {"code": 429, "message": "Rate limit exceeded: free-models-per-day. "
               "Add 10 credits to unlock 1000 free model requests per day",
               "metadata": {"headers": {"X-RateLimit-Reset": str(RESET)}}}}, {}, 43200),
    ({"error": {"code": "free-models-per-day-high-balance"}}, {}, None),
    ({"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
            {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
             "quotaMetric":
                 "generativelanguage.googleapis.com/generate_content_free_tier_requests"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "20s"}]}},
     {"retry-after": "20"}, None),
    ({"error": {"type": "tokens", "code": "rate_limit_exceeded",
                "message": "Rate limit reached for model on tokens per day (TPD): Limit 200000"}},
     {"x-ratelimit-reset-requests": "2h3m4.5s"}, None),
    ({"error": {"type": "rate_limit_error", "code": "rate_limit_exceeded",
                "message": "Rate limit exceeded"}},
     {"x-ratelimit-remaining-tokens-day": "0", "x-ratelimit-reset-tokens-day": "7200"}, 7200),
    ({"object": "error", "type": "rate_limited", "code": "1300",
      "message": "Daily token limit exceeded"}, {}, None),
    # The reverse of the minute counterexample below (gpt-6-astra, round 2):
    # the DAY is what ran out; the minute window is only a balance.
    ({"error": {"message": "Daily token limit exceeded. Requests per minute remaining: 49."}},
     {}, None),
    # A shorter-window word inside an identifier is not a window.
    ({"error": {"message": "Daily token limit exceeded for model supermin."}}, {}, None),
    ({"error": {"message": "Daily request limit reached, 0 remaining."}}, {}, None),
    # No space after the full stop still ends the sentence (astra round 3).
    ({"error": {"message": "Daily token limit exceeded.Requests per minute remaining: 49."}},
     {}, None),
    ({"error": {"message": "Rate limit reached for model `m` in organization `o` on "
                           "tokens per day (TPD): Limit 200000, Used 199999, Requested "
                           "500. Please try again in 1m23s."}}, {}, None),
])
def test_explicit_daily_shapes(body, headers, delay):
    signal = daily_quota_signal(429, headers, json.dumps(body), now=NOW)
    assert (signal.scope, signal.failure_class, signal.retry_after_s) == (
        "account", DAILY_QUOTA, delay,
    )
    assert not free_sibling_retry(scope=signal.scope, failure_class=signal.failure_class)


@pytest.mark.parametrize("body", [
    {"error": {"code": 429, "message": "Rate limit exceeded: free-models-per-minute"}},
    {"error": {"status": "RESOURCE_EXHAUSTED", "details": [{"violations": [
        {"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]}]}},
    {"error": {"message": "Rate limit reached on tokens per minute (TPM)"}},
    {"error": {"message": "Rate limit exceeded"}},
    # Mistral documents minute/second and monthly limits, not a unique daily
    # error code. Its real generic envelope must NOT be mislabeled as daily.
    {"object": "error", "message": "Rate limit exceeded", "type": "rate_limited",
     "param": None, "code": "1300", "raw_status_code": 429},
    {"error": {"details": [{"violations": 7}]}},
    # A minute refusal that merely MENTIONS the day's budget (gpt-6-astra
    # counterexample, 2026-09-30): read as daily, it cooled the whole source
    # and dropped a sibling model that would have answered.
    {"error": {"message": "Requests per minute exceeded. Daily quota remaining: 49. "
                          "Retry in 20 seconds."}},
    # A long gap must not cut the qualifier off the balance (astra round 3).
    {"error": {"message": "Requests per minute exceeded. Daily quota " + " " * 4096
                          + "remaining: 49."}},
    # A decimal is not a sentence end.
    {"error": {"message": "Limit 1.5 per minute exceeded. Daily quota remaining: 3."}},
])
def test_ambiguous_and_per_minute_shapes_are_not_daily(body):
    assert daily_quota_signal(429, {"retry-after": "120"}, json.dumps(body)) is None


def test_request_headers_need_declared_daily_semantics():
    headers = {"x-ratelimit-remaining-requests": "0", "x-ratelimit-reset-requests": "2h3m4.5s"}
    assert daily_quota_signal(429, headers, "{}") is None
    signal = daily_quota_signal(429, headers, "{}", daily_request_headers=True)
    assert signal.retry_after_s == 7384.5


def test_installed_shapes_can_describe_new_error_fields_and_headers(monkeypatch):
    from tinyassets.providers import daily_quota

    monkeypatch.setattr(daily_quota, "_SHAPES", {
        **daily_quota._SHAPES,
        "fact_paths": [["limits", "*", "period"]],
        "nested_headers_path": ["response", "headers"],
        "daily_windows": [{"remaining": "daily-left", "reset": "daily-reset"}],
    })
    body = {"error": {"limits": [{"period": "daily"}], "response": {
        "headers": {"daily-left": "0", "daily-reset": "2h"},
    }}}
    signal = daily_quota_signal(429, {}, json.dumps(body), now=NOW)
    assert (signal.scope, signal.failure_class, signal.retry_after_s) == (
        "account", DAILY_QUOTA, 7200,
    )
    # Unconfigured nested fields must not turn an ambiguous refusal into daily evidence.
    assert daily_quota_signal(429, {}, '{"error":{"message":"daily"}}') is None


def test_documented_midnight_reset_ignores_short_generic_retry_after():
    signal = daily_quota_signal(429, {"retry-after": "20"},
        '{"error":{"message":"Requests per day quota exceeded"}}', now=NOW,
        daily_reset_timezone="America/Los_Angeles")
    assert signal.retry_after_s == 19 * 3600


def test_daily_notice_survives_skipped_source_and_retained_history():
    from tinyassets.conversation_failure import failure_notice, normalize_turn_failure
    from tinyassets.exceptions import AllProvidersExhaustedError
    from tinyassets.providers.diagnostics import ProviderAttemptDiagnostic
    from tinyassets.universe_server import _served_failure_record

    signal = daily_quota_signal(429, {"X-RateLimit-Reset": str(RESET)},
                                '{"error":{"message":"free-models-per-day"}}', now=NOW)
    detail = daily_detail(signal, billing_url="https://openrouter.ai/settings/credits", now=NOW)
    for status in ("failed", "skipped"):
        exc = AllProvidersExhaustedError("exhausted", attempts=[ProviderAttemptDiagnostic(
            provider="api_key_http:one", status=status, skip_class="quota_or_cooldown",
            failure_class=DAILY_QUOTA, capacity_scope="account", detail=detail,
            cooldown_remaining_s=120,
        )])
        record = _served_failure_record(exc)
        text = failure_notice(normalize_turn_failure(record))
        assert record.code == DAILY_QUOTA
        assert "daily quota" in text and "another free source" in text and "add credit" in text
        assert "2026-10-01 00:00 UTC" in text and "https://openrouter.ai/settings/credits" in text
        assert "minutes" not in text and "Waiting on" not in text


def test_source_cooldown_cannot_be_shortened_by_abandon_cleanup(monkeypatch):
    from tinyassets.providers.quota import QuotaTracker

    clock = [100.0]
    monkeypatch.setattr("tinyassets.providers.quota.time.monotonic", lambda: clock[0])
    quota = QuotaTracker()
    quota.cooldown("owned-source", 43200, daily_detail="Daily quota exhausted")
    quota.cooldown("owned-source", 120)
    assert quota.cooldown_remaining("owned-source") == 43200
    assert quota.daily_detail("owned-source")
    assert quota.available("another-owner-source")
    clock[0] += 43201
    assert quota.available("owned-source") and not quota.daily_detail("owned-source")
