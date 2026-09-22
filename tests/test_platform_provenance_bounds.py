"""Regression proofs for the record-only startup observation's real bounds."""

from __future__ import annotations

import io
import json
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from tinyassets import platform_runtime_provenance as prov


def test_total_metadata_budget_bounds_a_slow_body() -> None:
    release = threading.Event()

    class SlowResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, _size):
            release.wait(0.3)
            return b"123"

    class SlowOpener:
        def open(self, _request, timeout):
            return SlowResponse()

    try:
        started = time.monotonic()
        result = prov.read_metadata_instance_id(opener=SlowOpener(), timeout=0.03)
        elapsed = time.monotonic() - started
        assert result.reason == "metadata_timeout"
        assert elapsed < 0.2
    finally:
        release.set()


def test_new_process_cannot_inherit_parent_observation(monkeypatch) -> None:
    monkeypatch.setattr(os, "getpid", lambda: 101)
    calls = []

    def resolve():
        calls.append(1)
        return prov.RuntimeProvenance(prov.NOT_CLOUD, "fixture", False, False)

    observation = prov.ProcessProvenanceObservation(resolve)
    observation.observe()
    monkeypatch.setattr(os, "getpid", lambda: 202)
    observation.observe()
    assert len(calls) == 2


def test_expected_identity_read_is_bounded_even_when_stat_is_stale(monkeypatch) -> None:
    payload = json.dumps({
        "schema": prov.EXPECTED_INSTANCE_SCHEMA,
        "version": 1,
        "expected_instance_id": "123",
        "extra": "x" * (prov.MAX_EXPECTED_STATE_BYTES + 1),
    })

    class ChangedFile:
        def is_file(self):
            return True

        def stat(self):
            return SimpleNamespace(st_size=1)

        def read_text(self, **_kwargs):
            return payload

        def open(self, *_args, **_kwargs):
            return io.BytesIO(payload.encode())

    monkeypatch.setattr(prov, "expected_instance_state_path", lambda _: ChangedFile())
    result = prov.read_expected_instance_id(data_root=Path("unused"))
    assert result.reason == "expected_identity_state_too_large"


def test_boolean_is_not_a_state_schema_version(tmp_path: Path) -> None:
    (tmp_path / prov.EXPECTED_INSTANCE_FILENAME).write_text(json.dumps({
        "schema": prov.EXPECTED_INSTANCE_SCHEMA,
        "version": True,
        "expected_instance_id": "123",
    }), encoding="utf-8")
    result = prov.read_expected_instance_id(data_root=tmp_path)
    assert result.reason == "expected_identity_version_unsupported"
