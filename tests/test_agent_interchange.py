from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest


def _adapter() -> dict[str, object]:
    return {
        "schema_version": "agent-interchange-adapter/v1",
        "adapter_ref": "commons:agent-package-conformance",
        "adapter_version": "1.0.0",
        "rules": [
            {"op": "constant", "target_path": "/schema_version", "value": 1},
            {
                "op": "copy",
                "source_path": "/profile/name",
                "target_path": "/name",
                "classification": "normalized",
            },
            {
                "op": "constant",
                "target_path": "/description",
                "value": "Imported through a declarative adapter",
            },
            {"op": "constant", "target_path": "/tags", "value": ["imported"]},
            {
                "op": "copy",
                "source_path": "/modules",
                "target_path": "/components",
                "classification": "preserved",
            },
            {
                "op": "namespace_preserve",
                "source_path": "/extra",
                "target_path": "/components/imported_extension/config/source",
                "classification": "preserved",
            },
            {
                "op": "constant",
                "target_path": "/components/imported_extension/kind",
                "value": "foreign.extension",
            },
            {
                "op": "omit",
                "source_path": "/credentials/api_key",
                "classification": "omitted_secret",
                "reason_code": "secret_field",
            },
        ],
    }


def _source(name: str = "Imported operator") -> dict[str, object]:
    return {
        "profile": {"name": name},
        "modules": {
            "identity": {
                "kind": "soul",
                "config": {"instructions": "Work carefully."},
            }
        },
        "credentials": {"api_key": "guess-me"},
        "extra": {"future_flag": True},
    }


def test_declarative_adapter_requires_complete_core_json_inventory() -> None:
    from tinyassets.agent_interchange import (
        InterchangeValidationError,
        convert_declarative_json,
    )

    adapter = _adapter()
    adapter["rules"] = [
        rule
        for rule in adapter["rules"]  # type: ignore[index]
        if rule.get("source_path") != "/extra"  # type: ignore[union-attr]
    ]

    with pytest.raises(InterchangeValidationError, match="inventory.*extra"):
        convert_declarative_json(_source(), adapter)


def test_private_stage_scrubs_secrets_preserves_unknowns_and_expires(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.agent_interchange import get_import_stage, stage_import

    monkeypatch.setenv(
        "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY",
        "test-agent-interchange-key-at-least-32-bytes",
    )
    stage = stage_import(
        tmp_path,
        actor_id="alice",
        source_json=_source(),
        adapter=_adapter(),
        idempotency_key="stage-one",
        now=100.0,
    )
    encoded = json.dumps(stage, sort_keys=True)

    assert "guess-me" not in encoded
    assert stage["source_commitment_algorithm"] == "hmac-sha256"
    assert stage["sanitized_source_digest_algorithm"] == "sha256"
    assert stage["candidate"]["components"]["imported_extension"]["config"] == {
        "source": {"future_flag": True}
    }
    assert {item["source_path"] for item in stage["report"]["items"]} == {
        "/credentials/api_key",
        "/extra/future_flag",
        "/modules/identity/config/instructions",
        "/modules/identity/kind",
        "/profile/name",
    }
    assert get_import_stage(tmp_path, actor_id="mallory", stage_id=stage["stage_id"]) is None
    assert get_import_stage(
        tmp_path,
        actor_id="alice",
        stage_id=stage["stage_id"],
        now=100.0 + 86_399,
    ) is not None
    assert get_import_stage(
        tmp_path,
        actor_id="alice",
        stage_id=stage["stage_id"],
        now=100.0 + 86_401,
    ) is None


def test_stage_idempotency_binds_actor_operation_source_and_adapter(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.agent_interchange import InterchangeConflictError, stage_import

    monkeypatch.setenv(
        "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY",
        "test-agent-interchange-key-at-least-32-bytes",
    )
    first = stage_import(
        tmp_path,
        actor_id="alice",
        source_json=_source(),
        adapter=_adapter(),
        idempotency_key="same-key",
    )
    retry = stage_import(
        tmp_path,
        actor_id="alice",
        source_json=_source(),
        adapter=_adapter(),
        idempotency_key="same-key",
    )
    assert retry["stage_id"] == first["stage_id"]

    with pytest.raises(InterchangeConflictError, match="different input"):
        stage_import(
            tmp_path,
            actor_id="alice",
            source_json=_source("Changed"),
            adapter=_adapter(),
            idempotency_key="same-key",
        )


def test_receipt_binds_adapter_version_and_detects_tampering(tmp_path, monkeypatch) -> None:
    from tinyassets.agent_interchange import (
        InterchangeValidationError,
        stage_import,
        verify_conversion_receipt,
    )

    monkeypatch.setenv(
        "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY",
        "test-agent-interchange-key-at-least-32-bytes",
    )
    first_adapter = _adapter()
    second_adapter = copy.deepcopy(first_adapter)
    second_adapter["adapter_version"] = "2.0.0"
    first = stage_import(
        tmp_path,
        actor_id="alice",
        source_json=_source(),
        adapter=first_adapter,
        idempotency_key="receipt-v1",
    )
    second = stage_import(
        tmp_path,
        actor_id="alice",
        source_json=_source(),
        adapter=second_adapter,
        idempotency_key="receipt-v2",
    )

    assert first["candidate"] == second["candidate"]
    assert first["receipt"]["adapter_digest"] != second["receipt"]["adapter_digest"]
    assert first["receipt"]["receipt_digest"] != second["receipt"]["receipt_digest"]
    assert verify_conversion_receipt(first["receipt"])

    tampered = copy.deepcopy(first["receipt"])
    tampered["report_digest"] = "0" * 64
    with pytest.raises(InterchangeValidationError, match="receipt digest"):
        verify_conversion_receipt(tampered)


def test_publish_stage_is_atomic_and_retry_safe(tmp_path, monkeypatch) -> None:
    import tinyassets.agent_interchange as interchange
    from tinyassets.custom_agents import list_definitions

    monkeypatch.setenv(
        "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY",
        "test-agent-interchange-key-at-least-32-bytes",
    )
    stage = interchange.stage_import(
        tmp_path,
        actor_id="alice",
        source_json=_source(),
        adapter=_adapter(),
        idempotency_key="stage-for-publish",
    )
    real_publish = interchange._publish_normalized

    def fail_publish(*args, **kwargs):
        raise RuntimeError("injected publication failure")

    monkeypatch.setattr(interchange, "_publish_normalized", fail_publish)
    with pytest.raises(RuntimeError, match="injected"):
        interchange.publish_import_stage(
            tmp_path,
            actor_id="alice",
            stage_id=stage["stage_id"],
            idempotency_key="publish-one",
        )
    assert list_definitions(tmp_path) == []
    assert interchange.get_import_stage(
        tmp_path,
        actor_id="alice",
        stage_id=stage["stage_id"],
    )["status"] == "staged"

    monkeypatch.setattr(interchange, "_publish_normalized", real_publish)
    published = interchange.publish_import_stage(
        tmp_path,
        actor_id="alice",
        stage_id=stage["stage_id"],
        idempotency_key="publish-one",
    )
    retry = interchange.publish_import_stage(
        tmp_path,
        actor_id="alice",
        stage_id=stage["stage_id"],
        idempotency_key="publish-one",
    )
    assert retry["agent_definition_id"] == published["agent_definition_id"]
    assert len(list_definitions(tmp_path)) == 1


def test_concurrent_identical_stage_import_creates_one_stage(tmp_path, monkeypatch) -> None:
    from tinyassets.agent_interchange import stage_import

    monkeypatch.setenv(
        "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY",
        "test-agent-interchange-key-at-least-32-bytes",
    )

    def stage_once(_: int) -> str:
        return stage_import(
            tmp_path,
            actor_id="alice",
            source_json=_source(),
            adapter=_adapter(),
            idempotency_key="concurrent-stage",
        )["stage_id"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        stage_ids = list(pool.map(stage_once, range(16)))
    assert len(set(stage_ids)) == 1
