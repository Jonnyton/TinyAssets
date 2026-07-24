from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from urllib.error import HTTPError

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "do_api_request.py"


def _load_module():
    assert SCRIPT.exists(), "bounded DigitalOcean request helper is missing"
    spec = importlib.util.spec_from_file_location("do_api_request", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RecordingBody(io.BytesIO):
    def __init__(self, value: bytes):
        super().__init__(value)
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return super().read(size)


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.body


def test_failure_diagnostic_is_fixed_cap_normalized_and_credential_redacted():
    helper = _load_module()
    token = "do-secret-token"
    raw = (
        b'{"id":"unauthorized","message":"Bearer attacker-value '
        + token.encode()
        + b'\\n'
        + (b"x" * 10_000)
        + b'"}'
    )

    diagnostic = helper.sanitize_failure_body(raw, token)

    assert len(diagnostic) <= helper.MAX_DIAGNOSTIC_CHARS == 300
    assert token not in diagnostic
    assert "attacker-value" not in diagnostic
    assert "\n" not in diagnostic
    assert "\r" not in diagnostic
    assert "unauthorized" in diagnostic


def test_http_failure_reads_at_most_4096_bytes_and_never_returns_raw_body():
    helper = _load_module()
    token = "do-secret-token"
    body = _RecordingBody(
        b'{"id":"forbidden","message":"Bearer do-secret-token"}'
        + (b"z" * 10_000)
    )
    http_error = HTTPError(
        "https://api.digitalocean.com/v2/droplets",
        403,
        "Forbidden",
        hdrs=None,
        fp=body,
    )

    def opener(_request, *, timeout):
        assert timeout == helper.REQUEST_TIMEOUT_SECONDS
        raise http_error

    with pytest.raises(helper.DigitalOceanRequestError) as exc:
        helper.api_request(
            method="POST",
            url="https://api.digitalocean.com/v2/droplets",
            token=token,
            data=b"{}",
            opener=opener,
        )

    assert body.read_sizes == [helper.MAX_ERROR_BYTES]
    assert helper.MAX_ERROR_BYTES == 4096
    assert exc.value.status == 403
    assert len(exc.value.diagnostic) <= 300
    assert token not in str(exc.value)
    assert "Bearer" not in str(exc.value)


def test_request_rejects_non_digitalocean_url_before_opening():
    helper = _load_module()
    opened = False

    def opener(_request, *, timeout):
        assert timeout == helper.REQUEST_TIMEOUT_SECONDS
        nonlocal opened
        opened = True
        return _Response(b"{}")

    with pytest.raises(ValueError, match="DigitalOcean API v2"):
        helper.api_request(
            method="GET",
            url="https://example.com/steal",
            token="secret",
            opener=opener,
        )

    assert opened is False


def test_success_returns_body_and_sends_bearer_token_without_logging_it():
    helper = _load_module()
    captured = {}

    def opener(request, *, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response(b'{"droplet":{"id":123}}')

    result = helper.api_request(
        method="POST",
        url="https://api.digitalocean.com/v2/droplets",
        token="secret-token",
        data=b'{"name":"drill"}',
        opener=opener,
    )

    assert result == b'{"droplet":{"id":123}}'
    request = captured["request"]
    assert request.full_url == "https://api.digitalocean.com/v2/droplets"
    assert request.get_method() == "POST"
    assert request.headers["Authorization"] == "Bearer secret-token"
    assert captured["timeout"] == helper.REQUEST_TIMEOUT_SECONDS == 30
