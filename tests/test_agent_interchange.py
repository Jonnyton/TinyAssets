from __future__ import annotations

import base64
import copy
import hashlib
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
                "source_path": "/modules/identity",
                "target_path": "/components/identity",
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


def _export_adapter(portable: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "agent-interchange-adapter/v1",
        "adapter_ref": "commons:foreign-agent-export",
        "adapter_version": "1.0.0",
        "target_media_type": "application/vnd.example.agent+json",
        "rules": [
            {
                "op": "copy",
                "source_path": f"/{key}",
                "target_path": f"/agent/{key}",
                "classification": "preserved",
            }
            for key in sorted(portable)
        ],
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


@pytest.mark.parametrize(
    "dishonest_rule",
    [
        {
            "op": "omit",
            "source_path": "/extra",
            "classification": "preserved",
        },
        {
            "op": "copy",
            "source_path": "/extra",
            "target_path": "/components/extension/config/source",
            "classification": "unsupported",
        },
        {
            "op": "constant",
            "source_path": "/extra",
            "target_path": "/description",
            "value": "pretend this covered the source",
            "classification": "preserved",
        },
    ],
)
def test_declarative_rule_operation_cannot_lie_about_loss(
    dishonest_rule: dict[str, object],
) -> None:
    from tinyassets.agent_interchange import (
        InterchangeValidationError,
        convert_declarative_json,
    )

    adapter = _adapter()
    adapter["rules"] = [
        dishonest_rule if rule.get("source_path") == "/extra" else rule
        for rule in adapter["rules"]  # type: ignore[index]
    ]

    with pytest.raises(InterchangeValidationError, match="rule.*canonical grammar"):
        convert_declarative_json(_source(), adapter)


@pytest.mark.parametrize("target_path", ["/name", "/components/imported_extension"])
def test_declarative_target_writes_cannot_overlap(target_path: str) -> None:
    from tinyassets.agent_interchange import (
        InterchangeValidationError,
        convert_declarative_json,
    )

    adapter = _adapter()
    adapter["rules"] = [
        {**rule, "target_path": target_path}
        if rule.get("source_path") == "/extra"
        else rule
        for rule in adapter["rules"]  # type: ignore[index]
    ]

    with pytest.raises(InterchangeValidationError, match="target paths overlap"):
        convert_declarative_json(_source(), adapter)


@pytest.mark.parametrize(
    "credentials",
    [
        {"token": "ghp_sensitive_value_1234567890"},
        {"channel_secret": "low-entropy-secret"},
        {"innocent_label": "Bearer authority-value"},
    ],
)
def test_credential_paths_and_values_cannot_be_namespace_preserved(
    credentials: dict[str, str],
) -> None:
    from tinyassets.agent_interchange import (
        InterchangeValidationError,
        convert_declarative_json,
    )

    source = _source()
    source["credentials"] = credentials
    adapter = _adapter()
    adapter["rules"] = [
        {
            "op": "namespace_preserve",
            "source_path": "/credentials",
            "target_path": "/components/imported_extension/config/credentials",
            "classification": "preserved",
        }
        if rule.get("source_path") == "/credentials/api_key"
        else rule
        for rule in adapter["rules"]  # type: ignore[index]
    ]

    with pytest.raises(InterchangeValidationError, match="secret|private"):
        convert_declarative_json(source, adapter)


def test_token_shaped_value_under_benign_key_is_omitted() -> None:
    from tinyassets.agent_interchange import (
        InterchangeValidationError,
        convert_declarative_json,
    )

    source = _source()
    source["extra"] = {"future_flag": "Bearer authority-value"}

    with pytest.raises(InterchangeValidationError, match="secret inventory path"):
        convert_declarative_json(source, _adapter())


def test_credential_shaped_object_key_cannot_enter_import_inventory() -> None:
    from tinyassets.agent_interchange import (
        InterchangeValidationError,
        convert_declarative_json,
    )

    source = _source()
    source["extra"] = {"ghp_abcdefghijklmnop": "safe-looking-value"}

    with pytest.raises(InterchangeValidationError, match="credential-shaped.*path"):
        convert_declarative_json(source, _adapter())


def test_adapter_constant_cannot_inject_credential_shaped_value() -> None:
    from tinyassets.agent_interchange import (
        InterchangeValidationError,
        convert_declarative_json,
    )

    adapter = _adapter()
    adapter["rules"] = [
        {
            "op": "constant",
            "target_path": "/description",
            "value": "Bearer authority-value",
        }
        if rule.get("target_path") == "/description"
        else rule
        for rule in adapter["rules"]  # type: ignore[index]
    ]

    with pytest.raises(InterchangeValidationError, match="secret|credential"):
        convert_declarative_json(_source(), adapter)


def test_foreign_export_requires_credential_paths_to_be_omitted() -> None:
    from tinyassets.agent_interchange import (
        InterchangeValidationError,
        _convert_declarative_export,
    )

    source = {
        "schema_version": 1,
        "name": "Legacy unsafe definition",
        "description": "",
        "tags": [],
        "components": {
            "provider": {
                "kind": "provider",
                "config": {"token": "ghp_sensitive_value_1234567890"},
            }
        },
        "lineage": {},
        "external_origins": [],
    }
    adapter = _export_adapter(source)

    with pytest.raises(InterchangeValidationError, match="secret inventory path"):
        _convert_declarative_export(source, adapter)


def test_foreign_export_secret_omission_cannot_be_called_unsupported() -> None:
    from tinyassets.agent_interchange import (
        InterchangeValidationError,
        _convert_declarative_export,
    )

    source = {
        "schema_version": 1,
        "name": "Legacy unsafe definition",
        "description": "",
        "tags": [],
        "components": {
            "identity": {
                "kind": "soul",
                "config": {"token": "ghp_sensitive_value_1234567890"},
            }
        },
        "lineage": {},
        "external_origins": [],
    }
    adapter = _export_adapter(source)
    adapter["rules"] = [
        rule
        for rule in adapter["rules"]  # type: ignore[index]
        if rule.get("source_path") != "/components"  # type: ignore[union-attr]
    ] + [
        {
            "op": "copy",
            "source_path": "/components/identity/kind",
            "target_path": "/agent/components/identity/kind",
            "classification": "preserved",
        },
        {
            "op": "omit",
            "source_path": "/components/identity/config/token",
            "classification": "unsupported",
            "reason_code": "unsupported",
        },
    ]

    with pytest.raises(InterchangeValidationError, match="secret inventory path"):
        _convert_declarative_export(source, adapter)


def test_public_payload_parser_rejects_duplicate_object_keys() -> None:
    from tinyassets.api.custom_agents import _payload
    from tinyassets.custom_agents import AgentValidationError

    with pytest.raises(AgentValidationError, match="duplicate object key.*source_json"):
        _payload('{"source_json":{},"source_json":{},"adapter":{}}')


def _opaque_terminal_response() -> dict[str, object]:
    return {
        "schema_version": "agent-interchange-adapter/v1",
        "status": "requires_runtime",
        "adapter_ref": "commons:opaque-agent-adapter",
        "adapter_version": "1.0.0",
        "adapter_digest_algorithm": "sha256",
        "adapter_digest": "a" * 64,
        "source_inventory": [],
        "report": {
            "schema_version": 1,
            "direction": "import",
            "inventory_verification": "unverified",
            "exhaustive": False,
            "lossless": False,
            "items": [],
        },
        "error_code": "requires_engine_os",
    }


def test_adapter_request_has_one_exact_bounded_source_shape() -> None:
    from tinyassets.agent_interchange import (
        InterchangeValidationError,
        validate_adapter_request,
    )

    request = {
        "schema_version": "agent-interchange-adapter/v1",
        "direction": "import",
        "source_json": {"nested": {"value": 1}},
        "source_media_type": "application/json",
        "target_media_type": "application/vnd.tinyassets.agent+json",
        "source_inventory": ["/nested/value"],
    }
    assert validate_adapter_request(request)["source_inventory"] == ["/nested/value"]

    duplicate = json.dumps(request, separators=(",", ":")).replace(
        '"direction":"import"',
        '"direction":"import","direction":"export"',
    )
    with pytest.raises(InterchangeValidationError, match="duplicate object key"):
        validate_adapter_request(duplicate)

    incomplete = copy.deepcopy(request)
    incomplete["source_inventory"] = []
    with pytest.raises(InterchangeValidationError, match="independently enumerated"):
        validate_adapter_request(incomplete)

    locator = {
        "schema_version": "agent-interchange-adapter/v1",
        "direction": "import",
        "source_locator": "https://example.invalid/agent",
        "source_media_type": "application/octet-stream",
        "target_media_type": "application/vnd.tinyassets.agent+json",
    }
    with pytest.raises(InterchangeValidationError, match="governed runtime"):
        validate_adapter_request(locator)

    request_with_authority = copy.deepcopy(request)
    request_with_authority["api_key"] = "must-not-reach-an-adapter"
    with pytest.raises(InterchangeValidationError, match="request fields"):
        validate_adapter_request(request_with_authority)


def test_opaque_adapter_response_stays_unverified_and_cannot_smuggle_output() -> None:
    from tinyassets.agent_interchange import (
        InterchangeValidationError,
        validate_adapter_response,
    )

    response = _opaque_terminal_response()
    assert validate_adapter_response(response, direction="import")["status"] == (
        "requires_runtime"
    )

    smuggled = copy.deepcopy(response)
    smuggled["output_base64"] = "e30="
    with pytest.raises(InterchangeValidationError, match="forbids.*output"):
        validate_adapter_response(smuggled, direction="import")

    response_extra = copy.deepcopy(response)
    response_extra["credentials"] = {"token": "must-not-persist"}
    with pytest.raises(InterchangeValidationError, match="response fields"):
        validate_adapter_response(response_extra, direction="import")

    report_extra = copy.deepcopy(response)
    report_extra["report"]["runtime_state"] = {"conversation": "private"}  # type: ignore[index]
    with pytest.raises(InterchangeValidationError, match="report fields"):
        validate_adapter_response(report_extra, direction="import")


def test_adapter_response_cannot_echo_credentials_in_report_paths_or_details() -> None:
    from tinyassets.agent_interchange import (
        InterchangeValidationError,
        validate_adapter_response,
    )

    path_leak = _opaque_terminal_response()
    path_leak["source_inventory"] = ["/ghp_abcdefghijklmnop"]
    path_leak["report"] = {
        "schema_version": 1,
        "direction": "import",
        "inventory_verification": "core_json",
        "exhaustive": True,
        "lossless": False,
        "items": [
            {
                "source_path": "/ghp_abcdefghijklmnop",
                "classification": "unsupported",
                "reason_code": "unsupported",
            }
        ],
    }
    with pytest.raises(InterchangeValidationError, match="credential-shaped.*path"):
        validate_adapter_response(path_leak, direction="import")

    detail_leak = _opaque_terminal_response()
    detail_leak["source_inventory"] = ["/x"]
    detail_leak["report"] = {
        "schema_version": 1,
        "direction": "import",
        "inventory_verification": "core_json",
        "exhaustive": True,
        "lossless": False,
        "items": [
            {
                "source_path": "/x",
                "classification": "unsupported",
                "reason_code": "unsupported",
                "detail": "credential ghp_abcdefghijklmnop",
            }
        ],
    }
    with pytest.raises(InterchangeValidationError, match="detail.*secret|credential"):
        validate_adapter_response(detail_leak, direction="import")

    metadata_leak = _opaque_terminal_response()
    metadata_leak["adapter_ref"] = "ghp_abcdefghijklmnop"
    with pytest.raises(InterchangeValidationError, match="secret|credential"):
        validate_adapter_response(metadata_leak, direction="import")


def test_adapter_response_rejects_duplicate_inventory_and_overlong_paths() -> None:
    from tinyassets.agent_interchange import (
        InterchangeValidationError,
        validate_adapter_response,
    )

    duplicate = _opaque_terminal_response()
    duplicate["source_inventory"] = ["/x", "/x"]
    duplicate["report"]["items"] = [  # type: ignore[index]
        {
            "source_path": "/x",
            "classification": "requires_runtime",
            "reason_code": "requires_runtime",
        }
    ]
    with pytest.raises(InterchangeValidationError, match="inventory.*unique"):
        validate_adapter_response(duplicate, direction="import")

    overlong = _opaque_terminal_response()
    overlong["source_inventory"] = ["/" + ("x" * 512)]
    with pytest.raises(InterchangeValidationError, match="512"):
        validate_adapter_response(overlong, direction="import")

    invalid_escape = _opaque_terminal_response()
    invalid_escape["source_inventory"] = ["/bad~2escape"]
    with pytest.raises(InterchangeValidationError, match="RFC 6901"):
        validate_adapter_response(invalid_escape, direction="import")


def test_untrusted_adapter_cannot_self_attest_preservation() -> None:
    from tinyassets.agent_interchange import (
        InterchangeValidationError,
        validate_adapter_response,
    )

    response = _opaque_terminal_response()
    response["status"] = "converted"
    response.pop("error_code")
    response["output_base64"] = "e30="
    response["source_inventory"] = ["/identity"]
    response["report"] = {
        "schema_version": 1,
        "direction": "import",
        "inventory_verification": "core_json",
        "exhaustive": True,
        "lossless": False,
        "items": [
            {
                "source_path": "/identity",
                "target_path": "/components/identity",
                "classification": "preserved",
                "reason_code": "preserved",
            }
        ],
    }

    with pytest.raises(InterchangeValidationError, match="preservation proof"):
        validate_adapter_response(response, direction="import")
    assert validate_adapter_response(
        response,
        direction="import",
        trusted_preservation=True,
    )["status"] == "converted"


def test_interchange_size_depth_rule_and_base64_bounds_fail_closed() -> None:
    from tinyassets.agent_interchange import (
        InterchangeValidationError,
        convert_declarative_json,
        validate_adapter_response,
    )

    deep: dict[str, object] = {}
    cursor = deep
    for _ in range(33):
        nested: dict[str, object] = {}
        cursor["nested"] = nested
        cursor = nested
    with pytest.raises(InterchangeValidationError, match="nesting"):
        convert_declarative_json(deep, _adapter())

    oversized = _source()
    oversized["extra"] = {"blob": "x" * (1024 * 1024)}
    with pytest.raises(InterchangeValidationError, match="source exceeds"):
        convert_declarative_json(oversized, _adapter())

    non_finite = _source()
    non_finite["extra"] = {"score": float("nan")}
    with pytest.raises(InterchangeValidationError, match="JSON-compatible"):
        convert_declarative_json(non_finite, _adapter())

    oversized_mapping = _adapter()
    oversized_mapping["padding"] = "x" * (128 * 1024)
    with pytest.raises(InterchangeValidationError, match="adapter mapping exceeds"):
        convert_declarative_json(_source(), oversized_mapping)

    too_many_rules = _adapter()
    too_many_rules["rules"] = [
        {"op": "constant", "target_path": f"/x/{index}", "value": index}
        for index in range(513)
    ]
    with pytest.raises(InterchangeValidationError, match="at most 512"):
        convert_declarative_json(_source(), too_many_rules)

    converted = _opaque_terminal_response()
    converted["status"] = "converted"
    converted.pop("error_code")
    converted["output_base64"] = "e30"
    with pytest.raises(InterchangeValidationError, match="base64"):
        validate_adapter_response(converted, direction="import")

    converted["output_base64"] = "A" * 1_398_105
    with pytest.raises(InterchangeValidationError, match="encoded bound"):
        validate_adapter_response(converted, direction="import")


def test_response_candidate_report_detail_digest_and_envelope_bounds_fail_closed() -> None:
    from tinyassets.agent_interchange import (
        InterchangeValidationError,
        validate_adapter_response,
    )

    candidate = _opaque_terminal_response()
    candidate["status"] = "converted"
    candidate.pop("error_code")
    candidate["candidate_json"] = {
        "schema_version": 1,
        "name": "Too many components",
        "description": "",
        "tags": [],
        "components": {
            f"component_{index}": {"kind": "test", "config": {}}
            for index in range(65)
        },
    }
    with pytest.raises(InterchangeValidationError, match="at most 64"):
        validate_adapter_response(candidate, direction="import")

    candidate["candidate_json"] = {
        "schema_version": 1,
        "name": "Oversized candidate",
        "description": "",
        "tags": [],
        "components": {
            "identity": {
                "kind": "test",
                "config": {"extension": "x" * (256 * 1024)},
            }
        },
    }
    with pytest.raises(InterchangeValidationError, match="canonical candidate exceeds"):
        validate_adapter_response(candidate, direction="import")

    detail = _opaque_terminal_response()
    detail["source_inventory"] = ["/x"]
    detail["report"] = {
        "schema_version": 1,
        "direction": "import",
        "inventory_verification": "core_json",
        "exhaustive": True,
        "lossless": False,
        "items": [
            {
                "source_path": "/x",
                "classification": "requires_runtime",
                "reason_code": "requires_runtime",
                "detail": "x" * 257,
            }
        ],
    }
    with pytest.raises(InterchangeValidationError, match="detail exceeds 256"):
        validate_adapter_response(detail, direction="import")

    too_many = _opaque_terminal_response()
    too_many["source_inventory"] = [f"/x{index}" for index in range(4097)]
    with pytest.raises(InterchangeValidationError, match="at most 4096"):
        validate_adapter_response(too_many, direction="import")

    digest = _opaque_terminal_response()
    digest["adapter_digest"] = "A" * 64
    with pytest.raises(InterchangeValidationError, match="digest"):
        validate_adapter_response(digest, direction="import")

    envelope = _opaque_terminal_response()
    envelope["unexpected_padding"] = "x" * (2 * 1024 * 1024)
    with pytest.raises(InterchangeValidationError, match="adapter response exceeds"):
        validate_adapter_response(envelope, direction="import")


def test_adapter_output_cannot_bypass_canonical_agent_validation() -> None:
    from tinyassets.agent_interchange import InterchangeValidationError, convert_declarative_json

    adapter = _adapter()
    adapter["rules"] = [
        {"op": "omit", "source_path": "", "classification": "unsupported"},
        {"op": "constant", "target_path": "/schema_version", "value": 1},
        {"op": "constant", "target_path": "/name", "value": "Unsafe"},
        {"op": "constant", "target_path": "/description", "value": "Unsafe"},
        {"op": "constant", "target_path": "/tags", "value": []},
        {
            "op": "constant",
            "target_path": "/components",
            "value": {
                "provider": {
                    "kind": "provider",
                    "config": {"api_key": "must-never-publish"},
                }
            },
        },
    ]
    with pytest.raises(InterchangeValidationError, match="secret|private"):
        convert_declarative_json({}, adapter)


def test_private_stage_scrubs_secrets_preserves_unknowns_and_expires(
    tmp_path,
    monkeypatch,
    caplog,
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
    raw_digest = hashlib.sha256(
        json.dumps(_source(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    persisted = b"".join(path.read_bytes() for path in tmp_path.glob(".tinyassets.db*"))

    assert "guess-me" not in encoded
    assert b"guess-me" not in persisted
    assert raw_digest not in encoded
    assert raw_digest.encode("ascii") not in persisted
    assert "guess-me" not in caplog.text
    assert raw_digest not in caplog.text
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


def test_expired_publish_and_later_writes_prune_stage_and_idempotency(
    tmp_path,
    monkeypatch,
) -> None:
    import sqlite3

    from tinyassets.agent_interchange import (
        InterchangeNotFoundError,
        publish_import_stage,
        stage_import,
    )
    from tinyassets.storage import db_path

    monkeypatch.setenv(
        "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY",
        "test-agent-interchange-key-at-least-32-bytes",
    )
    expired = stage_import(
        tmp_path,
        actor_id="alice",
        source_json=_source("Will expire"),
        adapter=_adapter(),
        idempotency_key="expired-stage",
        now=100.0,
    )

    with pytest.raises(InterchangeNotFoundError, match="unavailable"):
        publish_import_stage(
            tmp_path,
            actor_id="alice",
            stage_id=expired["stage_id"],
            idempotency_key="expired-publish",
            now=100.0 + 86_401,
        )

    with sqlite3.connect(db_path(tmp_path)) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM agent_import_stages WHERE stage_id = ?",
            (expired["stage_id"],),
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM agent_interchange_idempotency WHERE resource_id = ?",
            (expired["stage_id"],),
        ).fetchone()[0] == 0

    stale = stage_import(
        tmp_path,
        actor_id="alice",
        source_json=_source("Never read"),
        adapter=_adapter(),
        idempotency_key="stale-stage",
        now=200.0,
    )
    stage_import(
        tmp_path,
        actor_id="bob",
        source_json=_source("Later write"),
        adapter=_adapter(),
        idempotency_key="later-stage",
        now=200.0 + 86_401,
    )
    with sqlite3.connect(db_path(tmp_path)) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM agent_import_stages WHERE stage_id = ?",
            (stale["stage_id"],),
        ).fetchone()[0] == 0


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
        _sha256,
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

    malformed = copy.deepcopy(first["receipt"])
    malformed["adapter_digest_algorithm"] = "sha1"
    malformed["receipt_digest"] = "0" * 64
    with pytest.raises(InterchangeValidationError, match="algorithm"):
        verify_conversion_receipt(malformed)

    ambiguous = copy.deepcopy(first["receipt"])
    ambiguous["source_commitment"] = "must-not-be-durable"
    with pytest.raises(InterchangeValidationError, match="fields"):
        verify_conversion_receipt(ambiguous)

    credential_metadata = copy.deepcopy(first["receipt"])
    credential_metadata["adapter_ref"] = "ghp_abcdefghijklmnop"
    credential_metadata["receipt_digest"] = _sha256(
        {
            key: value
            for key, value in credential_metadata.items()
            if key != "receipt_digest"
        }
    )
    with pytest.raises(InterchangeValidationError, match="secret|credential"):
        verify_conversion_receipt(credential_metadata)


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


def test_identical_receipt_digest_links_every_published_stage(tmp_path, monkeypatch) -> None:
    import sqlite3

    from tinyassets.agent_interchange import publish_import_stage, stage_import
    from tinyassets.storage import db_path

    monkeypatch.setenv(
        "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY",
        "test-agent-interchange-key-at-least-32-bytes",
    )
    stages = [
        stage_import(
            tmp_path,
            actor_id="alice",
            source_json=_source(),
            adapter=_adapter(),
            idempotency_key=f"collision-stage-{index}",
            now=500.0,
        )
        for index in range(2)
    ]
    assert stages[0]["receipt"]["receipt_digest"] == stages[1]["receipt"][
        "receipt_digest"
    ]
    for index, stage in enumerate(stages):
        publish_import_stage(
            tmp_path,
            actor_id="alice",
            stage_id=stage["stage_id"],
            idempotency_key=f"collision-publish-{index}",
            now=501.0,
        )

    with sqlite3.connect(db_path(tmp_path)) as conn:
        links = conn.execute(
            """
            SELECT stage_id, receipt_digest
            FROM agent_conversion_receipt_links
            ORDER BY stage_id
            """
        ).fetchall()
    assert {row[0] for row in links} == {stage["stage_id"] for stage in stages}
    assert len({row[1] for row in links}) == 1


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


def test_agent_api_authenticates_staging_hides_it_from_other_users_and_publishes(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.api import permissions
    from tinyassets.api.custom_agents import custom_agents

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY",
        "test-agent-interchange-key-at-least-32-bytes",
    )
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: False)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "anonymous")

    anonymous = custom_agents(
        action="stage_import",
        payload={"source_json": _source(), "adapter": _adapter()},
        idempotency_key="api-stage-one",
    )
    assert anonymous == {
        "error": "authentication_required",
        "resource": "agent_import_stage",
    }

    actor = {"id": "alice"}
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: actor["id"])
    opaque = custom_agents(
        action="stage_import",
        payload={
            "source_base64": base64.b64encode(b"opaque agent package").decode("ascii"),
            "adapter": {
                "schema_version": "agent-interchange-adapter/v1",
                "adapter_ref": "commons:engine-os-agent-package",
                "adapter_version": "1.0.0",
            },
        },
        idempotency_key="opaque-stage-one",
    )
    assert opaque["status"] == "requires_runtime"
    assert opaque["report"]["inventory_verification"] == "unverified"
    assert opaque["report"]["exhaustive"] is False
    assert opaque["report"]["lossless"] is False

    staged = custom_agents(
        action="stage_import",
        payload={"source_json": _source(), "adapter": _adapter()},
        idempotency_key="api-stage-one",
    )
    stage_id = staged["stage"]["stage_id"]
    assert staged["status"] == "staged"

    actor["id"] = "bob"
    hidden = custom_agents(action="get_import_stage", stage_id=stage_id)
    assert hidden == {"error": "not_found", "resource": "agent_import_stage"}

    actor["id"] = "alice"
    missing_stage = custom_agents(
        action="publish_stage",
        stage_id="agent_stage_missing",
        idempotency_key="missing-stage",
    )
    assert missing_stage == {
        "error": "not_found",
        "resource": "agent_import_stage",
    }
    visible = custom_agents(action="get_import_stage", stage_id=stage_id)
    assert visible["stage"]["stage_id"] == stage_id
    published = custom_agents(
        action="publish_stage",
        stage_id=stage_id,
        idempotency_key="api-publish-one",
    )
    assert published["status"] == "published"
    assert published["agent"]["name"] == "Imported operator"
    exported = custom_agents(
        action="convert_export",
        definition_id=published["agent"]["agent_definition_id"],
        payload={
            "adapter": _export_adapter(published["agent"]["portable_definition"]),
        },
        idempotency_key="api-export-one",
    )
    assert exported["status"] == "converted"


def test_foreign_export_is_adapter_driven_bounded_and_receipted(tmp_path) -> None:
    from tinyassets.agent_interchange import convert_export
    from tinyassets.custom_agents import publish_definition

    definition = publish_definition(
        tmp_path,
        author_id="alice",
        payload={
            "schema_version": 1,
            "name": "Portable coding agent",
            "description": "No format-specific platform preset.",
            "tags": ["coding"],
            "components": {
                "identity": {
                    "kind": "soul",
                    "config": {"instructions": "Review before changing code."},
                }
            },
        },
    )
    portable = definition["portable_definition"]

    exported = convert_export(
        tmp_path,
        actor_id="bob",
        definition_id=definition["agent_definition_id"],
        adapter=_export_adapter(portable),
        idempotency_key="foreign-export-one",
    )
    retry = convert_export(
        tmp_path,
        actor_id="bob",
        definition_id=definition["agent_definition_id"],
        adapter=_export_adapter(portable),
        idempotency_key="foreign-export-one",
    )
    decoded = json.loads(base64.b64decode(exported["output_base64"], validate=True))

    assert exported["status"] == "converted"
    assert exported["direction"] == "export"
    assert decoded == {"agent": portable}
    assert exported["report"]["exhaustive"] is True
    assert exported["report"]["lossless"] is False
    assert exported["receipt"]["output_kind"] == "foreign_bytes"
    assert retry["receipt"]["receipt_digest"] == exported["receipt"]["receipt_digest"]


def test_identical_export_receipt_digest_links_every_actor(tmp_path) -> None:
    import sqlite3

    from tinyassets.agent_interchange import convert_export
    from tinyassets.custom_agents import publish_definition
    from tinyassets.storage import db_path

    definition = publish_definition(
        tmp_path,
        author_id="author",
        payload={
            "schema_version": 1,
            "name": "Shared export source",
            "description": "",
            "tags": [],
            "components": {"identity": {"kind": "soul", "config": {}}},
        },
    )
    adapter = _export_adapter(definition["portable_definition"])
    exports = [
        convert_export(
            tmp_path,
            actor_id=actor,
            definition_id=definition["agent_definition_id"],
            adapter=adapter,
            idempotency_key=f"export-{actor}",
            now=700.0,
        )
        for actor in ("alice", "bob")
    ]
    assert exports[0]["receipt"]["receipt_digest"] == exports[1]["receipt"][
        "receipt_digest"
    ]

    with sqlite3.connect(db_path(tmp_path)) as conn:
        owners = conn.execute(
            """
            SELECT actor_id
            FROM agent_conversion_receipt_owners
            WHERE receipt_digest = ? AND operation = 'convert_export'
            ORDER BY actor_id
            """,
            (exports[0]["receipt"]["receipt_digest"],),
        ).fetchall()
    assert owners == [("alice",), ("bob",)]
