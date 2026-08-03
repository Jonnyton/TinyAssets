from __future__ import annotations

import base64
from pathlib import Path

import pytest

from scripts.validate_host_runtime_hmac_pair import validate_pair


def _encoded(byte: bytes) -> str:
    return base64.b64encode(byte * 48).decode("ascii")


def _write(path: Path, key: str, value: str) -> None:
    path.write_text(f"{key}={value}\n", encoding="utf-8")


def test_validate_pair_accepts_distinct_canonical_keys(tmp_path: Path):
    request = tmp_path / "request.env"
    agent = tmp_path / "agent.env"
    _write(request, "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY", _encoded(b"r"))
    _write(agent, "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY", _encoded(b"a"))

    validate_pair(request, agent, enforce_metadata=False)


@pytest.mark.parametrize("defect", ["same", "short", "duplicate", "newline"])
def test_validate_pair_rejects_unsafe_host_state(tmp_path: Path, defect: str):
    request = tmp_path / "request.env"
    agent = tmp_path / "agent.env"
    request_value = _encoded(b"r")
    agent_value = _encoded(b"a")
    _write(request, "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY", request_value)
    _write(agent, "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY", agent_value)

    if defect == "same":
        _write(agent, "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY", request_value)
    elif defect == "short":
        _write(request, "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY", _encoded(b"r")[:20])
    elif defect == "duplicate":
        request.write_text(
            request.read_text(encoding="utf-8")
            + f"TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY={request_value}\n",
            encoding="utf-8",
        )
    else:
        request.write_text(
            f"TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY={request_value}\nINJECTED=1\n",
            encoding="utf-8",
        )

    with pytest.raises(ValueError):
        validate_pair(request, agent, enforce_metadata=False)
