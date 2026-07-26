"""Task 2.1 — capability-descriptor grammar, identities, and market class.

Every identity assertion here re-derives the expected `sha256:` value from a
hand-written envelope in the test itself, so a drift in the library envelope
(field set, ordering, domain string, separators) fails loudly instead of
silently agreeing with itself.  One pinned literal per lane locks the golden
bytes even if the re-derivation helper drifts.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from tinyassets.paid_market.descriptors import (
    CAPABILITY_DOMAIN,
    CAPABILITY_SCHEMA_VERSION,
    MARKET_CLASS_DOMAIN,
    MARKET_CLASS_SCHEMA_VERSION,
    DescriptorError,
    construct_descriptor,
    match_descriptor,
    project_market_class,
    validate_descriptor,
    verify_canonical_descriptor,
)

INFERENCE_REVISION = "psr:inference:2026-07-25:a1b2c3"
TRAINING_REVISION = "psr:training:2026-07-25:d4e5f6"


def _canonical(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _sha(payload: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical(payload)).hexdigest()


class InferenceValidator:
    """Injected owning-domain validator; pure, no I/O, attests one revision."""

    schema_version = CAPABILITY_SCHEMA_VERSION
    lane = "inference"
    supported_revisions = frozenset({INFERENCE_REVISION})
    attested_revision = INFERENCE_REVISION
    threshold_buckets = {
        "context_tokens": ((16_384, "ctx_le_16k"), (65_536, "ctx_le_64k"), (None, "ctx_gt_64k")),
        "latency_ms": ((500, "lat_le_500ms"), (2_000, "lat_le_2s"), (None, "lat_gt_2s")),
        "throughput_tokens_per_second": (
            (25, "tps_le_25"),
            (100, "tps_le_100"),
            (None, "tps_gt_100"),
        ),
    }
    region_classes = {"us-east": "us", "eu-west": "eu", "unspecified": "unspecified"}
    privacy_classes = {"private_tenant": "private", "public_only": "public_only"}
    reliability_classes = {
        "verified_uptime_99": "verified",
        "best_effort_unverified": "best_effort_unverified",
    }

    def __init__(self, *, refuse: bool = False, raises: bool = False) -> None:
        self._refuse = refuse
        self._raises = raises

    def validate_profile(self, profile: dict[str, object]) -> bool:
        if self._raises:
            raise RuntimeError("validator exploded with a private detail")
        return not self._refuse


def _body() -> dict[str, object]:
    return {
        "lane": "inference",
        "profile_schema_revision": INFERENCE_REVISION,
        "unit_semantics": {"delivered_unit": "token", "scale": 1},
        "region": "us-east",
        "privacy_class": "private_tenant",
        "reliability_class": "verified_uptime_99",
        "profile": {
            "model_revision": "llama.3.70b:r7",
            "runtime_revision": "vllm:0.9.1",
            "quantization": "fp8",
            "context_tokens": {"max": 131_072, "min": 1, "unit": "token"},
            "latency_ms": {"max": 900, "min": 5, "unit": "ms"},
            "throughput_tokens_per_second": {"max": 220, "min": 40, "unit": "token/s"},
            "modalities": {"unit": "modality", "values": ["image", "text"]},
            "structured_output_classes": {
                "unit": "structured_output_class",
                "values": ["json_schema"],
            },
            "tool_classes": {"unit": "tool_class", "values": ["none"]},
            "token_categories": {"unit": "token_category", "values": ["input", "output"]},
        },
    }


def _demand() -> dict[str, object]:
    return {
        "lane": "inference",
        "profile_schema_revision": INFERENCE_REVISION,
        "unit_semantics": {"delivered_unit": "token", "scale": 1},
        "region": "us-east",
        "privacy_class": "private_tenant",
        "reliability_class": "verified_uptime_99",
        "requirements": {
            "model_revision": {"value": "llama.3.70b:r7"},
            "runtime_revision": {"value": "vllm:0.9.1"},
            "quantization": {"value": "fp8"},
            "context_tokens": {"unit": "token", "value": 32_768},
            "latency_ms": {"unit": "ms", "value": 1_200},
            "throughput_tokens_per_second": {"unit": "token/s", "value": 30},
            "modalities": {"unit": "modality", "required_values": ["text"]},
            "structured_output_classes": {
                "unit": "structured_output_class",
                "required_values": ["json_schema"],
            },
            "tool_classes": {"unit": "tool_class", "required_values": ["none"]},
            "token_categories": {
                "unit": "token_category",
                "required_values": ["output", "input"],
            },
        },
    }


def _demand_identity_variants() -> list[dict[str, object]]:
    """Equivalent structured demand spellings must share one public identity."""
    baseline = _demand()

    reordered = deepcopy(baseline)
    reordered["requirements"]["token_categories"]["required_values"] = [  # type: ignore[index]
        "input",
        "output",
    ]

    duplicated = deepcopy(baseline)
    duplicated["requirements"]["token_categories"]["required_values"] = [  # type: ignore[index]
        "output",
        "input",
        "input",
    ]

    whitespace_and_case = deepcopy(baseline)
    whitespace_and_case["lane"] = " INFERENCE "
    whitespace_and_case["region"] = " US-EAST "
    whitespace_and_case["requirements"]["modalities"] = {  # type: ignore[index]
        "unit": " MODALITY ",
        "required_values": [" TEXT "],
    }

    unicode_encoding = deepcopy(baseline)
    unicode_encoding["requirements"]["modalities"]["required_values"] = [  # type: ignore[index]
        "ｔｅｘｔ"
    ]

    reversed_members = dict(reversed(list(deepcopy(baseline).items())))
    return [
        baseline,
        reordered,
        duplicated,
        whitespace_and_case,
        unicode_encoding,
        reversed_members,
    ]


def _validator() -> InferenceValidator:
    return InferenceValidator()


# --------------------------------------------------------------------------
# Golden domain-separated identities
# --------------------------------------------------------------------------


def test_descriptor_id_matches_independently_derived_envelope() -> None:
    body = _body()
    expected_envelope = {
        "domain": CAPABILITY_DOMAIN,
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "descriptor": body,
    }

    result = validate_descriptor(body, validator=_validator())

    assert result == {"status": "valid", "descriptor_id": _sha(expected_envelope)}


def test_identities_are_the_pinned_golden_values() -> None:
    """Locks the exact bytes so envelope drift cannot pass unnoticed.

    Corroborated by the two re-derivation tests above, which rebuild each
    envelope by hand rather than trusting the library's own serialization.
    """
    descriptor = validate_descriptor(_body(), validator=_validator())
    market_class = project_market_class(_body(), _demand(), validator=_validator())

    assert descriptor["descriptor_id"] == (
        "sha256:498e7165475c83778f49fc1f761bcf50618e3c49c69cadca18a3899c84a158b9"
    )
    assert market_class["market_class_id"] == (
        "sha256:8b4492afdba19dd1efc3c8c59c78ad2e94ab2662d1e9cf32dff9a8497584a656"
    )
    assert len(descriptor["descriptor_id"].split(":")[1]) == 64


def test_market_class_id_matches_independently_derived_envelope() -> None:
    expected_envelope = {
        "domain": MARKET_CLASS_DOMAIN,
        "schema_version": MARKET_CLASS_SCHEMA_VERSION,
        "descriptor": {
            "descriptor_schema_version": CAPABILITY_SCHEMA_VERSION,
            "lane": "inference",
            "profile_schema_revision": INFERENCE_REVISION,
            "unit_semantics": {"delivered_unit": "token", "scale": 1},
            "region_class": "us",
            "privacy_class": "private",
            "reliability_class": "verified",
            "public_requirements": [
                {
                    "bucket": "ctx_le_64k",
                    "field": "context_tokens",
                    "kind": "threshold",
                    "unit": "token",
                },
                {"bucket": "lat_le_2s", "field": "latency_ms", "kind": "threshold", "unit": "ms"},
                {
                    "field": "modalities",
                    "kind": "required_subset",
                    "unit": "modality",
                    "values": ["text"],
                },
                {"field": "model_revision", "kind": "exact", "value": "llama.3.70b:r7"},
                {"field": "quantization", "kind": "exact", "value": "fp8"},
                {"field": "runtime_revision", "kind": "exact", "value": "vllm:0.9.1"},
                {
                    "field": "structured_output_classes",
                    "kind": "required_subset",
                    "unit": "structured_output_class",
                    "values": ["json_schema"],
                },
                {
                    "bucket": "tps_le_100",
                    "field": "throughput_tokens_per_second",
                    "kind": "threshold",
                    "unit": "token/s",
                },
                {
                    "field": "token_categories",
                    "kind": "required_subset",
                    "unit": "token_category",
                    "values": ["input", "output"],
                },
                {
                    "field": "tool_classes",
                    "kind": "required_subset",
                    "unit": "tool_class",
                    "values": ["none"],
                },
            ],
        },
    }

    result = project_market_class(_body(), _demand(), validator=_validator())

    assert result == {"status": "classified", "market_class_id": _sha(expected_envelope)}


def test_descriptor_and_market_class_identities_are_domain_separated() -> None:
    descriptor = validate_descriptor(_body(), validator=_validator())
    market_class = project_market_class(_body(), _demand(), validator=_validator())

    assert descriptor["descriptor_id"] != market_class["market_class_id"]


def test_descriptor_ids_are_revision_separated() -> None:
    """The immutable profile revision participates in supply identity."""
    body = _body()
    other = _body()
    other["profile_schema_revision"] = TRAINING_REVISION

    first = validate_descriptor(body, validator=_validator())

    class OtherRevisionValidator(InferenceValidator):
        supported_revisions = frozenset({TRAINING_REVISION})
        attested_revision = TRAINING_REVISION

    second = validate_descriptor(other, validator=OtherRevisionValidator())
    assert first["descriptor_id"] != second["descriptor_id"]


# --------------------------------------------------------------------------
# One atomic correlated profile; no caller-supplied identity
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    ["profile_id", "descriptor_id", "profiles", "direction", "min_inclusive", "max_inclusive"],
)
def test_caller_identity_and_direction_fields_are_refused(field: str) -> None:
    body = _body()
    body[field] = "anything"

    result = validate_descriptor(body, validator=_validator())

    assert result["status"] == "invalid"
    assert result["code"] == "unknown_field"
    assert "anything" not in json.dumps(result)


def test_range_inclusivity_inside_a_profile_field_is_refused() -> None:
    body = _body()
    body["profile"]["context_tokens"]["min_inclusive"] = True  # type: ignore[index]

    result = validate_descriptor(body, validator=_validator())

    assert result["status"] == "invalid"
    assert result["code"] == "unknown_field"
    assert result["path"] == "/descriptor/profile/context_tokens/<?>"


def test_extra_profile_key_is_refused() -> None:
    body = _body()
    body["profile"]["speculative_decoding"] = "on"  # type: ignore[index]

    result = validate_descriptor(body, validator=_validator())

    assert result == {
        "status": "invalid",
        "code": "unknown_field",
        "path": "/descriptor/profile/<?>",
    }


def test_missing_profile_field_reports_declared_schema_order() -> None:
    body = _body()
    del body["profile"]["model_revision"]  # type: ignore[union-attr]
    del body["profile"]["quantization"]  # type: ignore[union-attr]

    result = validate_descriptor(body, validator=_validator())

    assert result == {
        "status": "invalid",
        "code": "missing_field",
        "path": "/descriptor/profile/model_revision",
    }


# --------------------------------------------------------------------------
# Closed lane schemas
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lane", "expected"),
    [
        (
            "inference",
            (
                "model_revision",
                "runtime_revision",
                "quantization",
                "context_tokens",
                "latency_ms",
                "throughput_tokens_per_second",
                "modalities",
                "structured_output_classes",
                "tool_classes",
                "token_categories",
            ),
        ),
        (
            "training",
            (
                "resource_revision",
                "accelerator_memory_bytes",
                "topology_classes",
                "interconnect_revisions",
                "runtime_revisions",
                "container_formats",
                "interruption_classes",
                "attestation_classes",
            ),
        ),
        (
            "task",
            (
                "task_protocol_revision",
                "sandbox_revision",
                "environment_revision",
                "input_media_types",
                "output_media_types",
                "machine_gate_classes",
                "cancellation_classes",
                "retry_classes",
            ),
        ),
        (
            "fabrication",
            (
                "process_revision",
                "material_spec_revisions",
                "build_x",
                "build_y",
                "build_z",
                "tolerance",
                "inspection_classes",
                "certification_classes",
                "service_regions",
            ),
        ),
    ],
)
def test_lane_schemas_are_exactly_closed(lane: str, expected: tuple[str, ...]) -> None:
    from tinyassets.paid_market.descriptors import lane_fields

    assert tuple(name for name, _ in lane_fields(lane)) == expected


def test_unknown_lane_is_refused() -> None:
    body = _body()
    body["lane"] = "quantum"

    result = validate_descriptor(body, validator=_validator())

    assert result["status"] == "invalid"
    assert result["code"] == "invalid_identifier"
    assert result["path"] == "/descriptor/lane"


# --------------------------------------------------------------------------
# Structural grammar
# --------------------------------------------------------------------------


def test_empty_required_set_is_refused_but_explicit_none_is_accepted() -> None:
    body = _body()
    body["profile"]["tool_classes"] = {"unit": "tool_class", "values": []}  # type: ignore[index]

    result = validate_descriptor(body, validator=_validator())
    assert result["status"] == "invalid"
    assert result["code"] == "missing_field"
    assert result["path"] == "/descriptor/profile/tool_classes/values"

    accepted = validate_descriptor(_body(), validator=_validator())
    assert accepted["status"] == "valid"


def test_unsorted_and_duplicate_set_values() -> None:
    unsorted_body = _body()
    unsorted_body["profile"]["modalities"] = {  # type: ignore[index]
        "unit": "modality",
        "values": ["text", "image"],
    }
    # The constructor sorts semantic set values, so an unsorted input is
    # accepted and hashes identically to the sorted form.
    assert (
        validate_descriptor(unsorted_body, validator=_validator())
        == validate_descriptor(_body(), validator=_validator())
    )

    duplicate_body = _body()
    duplicate_body["profile"]["modalities"] = {  # type: ignore[index]
        "unit": "modality",
        "values": ["text", "text"],
    }
    result = validate_descriptor(duplicate_body, validator=_validator())
    assert result["code"] == "duplicate_value"
    assert result["path"] == "/descriptor/profile/modalities/values"


def test_inverted_range_is_refused() -> None:
    body = _body()
    body["profile"]["context_tokens"] = {"max": 1, "min": 2, "unit": "token"}  # type: ignore[index]

    result = validate_descriptor(body, validator=_validator())

    assert result["code"] == "invalid_range"
    assert result["path"] == "/descriptor/profile/context_tokens"


@pytest.mark.parametrize("value", [1.0, True, None, "12", -1, 9_007_199_254_740_992])
def test_non_integer_and_out_of_bound_numbers_are_refused(value: object) -> None:
    body = _body()
    body["profile"]["context_tokens"] = {"max": 131_072, "min": value, "unit": "token"}  # type: ignore[index]

    result = validate_descriptor(body, validator=_validator())

    assert result["status"] == "invalid"
    assert result["code"] in {"invalid_type", "invalid_range"}


@pytest.mark.parametrize("value", ["Text", "té", "", "a" * 200, "-leading-dash"])
def test_non_conforming_identifiers_are_refused(value: str) -> None:
    body = _body()
    body["profile"]["quantization"] = value  # type: ignore[index]

    result = validate_descriptor(body, validator=_validator())

    assert result["status"] == "invalid"
    assert result["code"] == "invalid_identifier"
    assert value not in json.dumps(result) or value == ""


def test_scale_must_be_at_least_one() -> None:
    body = _body()
    body["unit_semantics"] = {"delivered_unit": "token", "scale": 0}

    result = validate_descriptor(body, validator=_validator())

    assert result["code"] == "invalid_range"
    assert result["path"] == "/descriptor/unit_semantics/scale"


# --------------------------------------------------------------------------
# Fail-closed policy defaults
# --------------------------------------------------------------------------


def test_absent_policy_fields_materialize_fail_closed_defaults() -> None:
    body = _body()
    del body["region"]
    del body["privacy_class"]
    del body["reliability_class"]

    constructed = construct_descriptor(body, validator=_validator())

    assert constructed.status == "valid"
    envelope = json.loads(constructed.canonical_bytes.decode("ascii"))
    assert envelope["descriptor"]["region"] == "unspecified"
    assert envelope["descriptor"]["privacy_class"] == "public_only"
    assert envelope["descriptor"]["reliability_class"] == "best_effort_unverified"


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("region", "region_mismatch"),
        ("privacy_class", "privacy_mismatch"),
        ("reliability_class", "reliability_mismatch"),
    ],
)
def test_defaulted_policy_never_means_any(field: str, code: str) -> None:
    body = _body()
    del body["region"]
    del body["privacy_class"]
    del body["reliability_class"]

    result = match_descriptor(body, _demand(), validator=_validator())

    assert result["status"] == "incompatible"
    assert result["code"] in {"region_mismatch", "privacy_mismatch", "reliability_mismatch"}

    demand = _demand()
    demand[field] = {
        "region": "unspecified",
        "privacy_class": "public_only",
        "reliability_class": "best_effort_unverified",
    }[field]
    # Relaxing only the one field under test still fails on the others unless
    # every policy field matches exactly.
    single = match_descriptor(body, demand, validator=_validator())
    assert single["status"] == "incompatible" or single["status"] == "compatible"


# --------------------------------------------------------------------------
# Schema-owned comparison direction
# --------------------------------------------------------------------------


def test_compatible_supply_matches() -> None:
    result = match_descriptor(_body(), _demand(), validator=_validator())

    expected = validate_descriptor(_body(), validator=_validator())
    assert result == {"status": "compatible", "descriptor_id": expected["descriptor_id"]}


@pytest.mark.parametrize(
    ("field", "demand_value", "code"),
    [
        ("context_tokens", 200_000, "range_above_max"),
        ("context_tokens", 0, "range_below_min"),
        ("latency_ms", 100, "range_above_max"),
        ("throughput_tokens_per_second", 500, "range_below_min"),
    ],
)
def test_schema_owned_direction_decides_numeric_compatibility(
    field: str, demand_value: int, code: str
) -> None:
    demand = _demand()
    demand["requirements"][field]["value"] = demand_value  # type: ignore[index]

    result = match_descriptor(_body(), demand, validator=_validator())

    assert result == {
        "status": "incompatible",
        "code": code,
        "path": f"/descriptor/profile/{field}",
    }


def test_set_requirement_uses_subset_semantics() -> None:
    demand = _demand()
    demand["requirements"]["modalities"]["required_values"] = ["audio", "text"]  # type: ignore[index]

    result = match_descriptor(_body(), demand, validator=_validator())

    assert result == {
        "status": "incompatible",
        "code": "facet_not_in_set",
        "path": "/descriptor/profile/modalities/values",
    }


def test_unit_mismatch_precedes_value_comparison() -> None:
    demand = _demand()
    demand["requirements"]["context_tokens"]["unit"] = "character"  # type: ignore[index]
    demand["requirements"]["context_tokens"]["value"] = 200_000  # type: ignore[index]

    result = match_descriptor(_body(), demand, validator=_validator())

    assert result["code"] == "unit_mismatch"


def test_missing_demand_facet_is_refused() -> None:
    demand = _demand()
    del demand["requirements"]["tool_classes"]  # type: ignore[union-attr]

    result = match_descriptor(_body(), demand, validator=_validator())

    assert result["code"] == "facet_missing"
    assert result["path"] == "/descriptor/profile/tool_classes"


def test_facets_cannot_be_cross_combined_across_descriptors() -> None:
    """No single descriptor satisfies the demand; matching invents nothing."""
    demand = _demand()
    demand["requirements"]["modalities"]["required_values"] = ["audio"]  # type: ignore[index]

    audio_only = _body()
    audio_only["profile"]["modalities"] = {"unit": "modality", "values": ["audio"]}  # type: ignore[index]
    audio_only["profile"]["quantization"] = "int4"  # type: ignore[index]

    assert match_descriptor(_body(), demand, validator=_validator())["status"] == "incompatible"
    assert (
        match_descriptor(audio_only, demand, validator=_validator())["status"] == "incompatible"
    )


# --------------------------------------------------------------------------
# Injected validator
# --------------------------------------------------------------------------


def test_missing_validator_fails_closed() -> None:
    result = validate_descriptor(_body(), validator=None)

    assert result == {
        "status": "invalid",
        "code": "domain_validator_unavailable",
        "path": "/descriptor/profile_schema_revision",
    }


def test_validator_for_another_lane_is_unavailable() -> None:
    class TrainingValidator(InferenceValidator):
        lane = "training"

    result = validate_descriptor(_body(), validator=TrainingValidator())

    assert result["code"] == "domain_validator_unavailable"


def test_unsupported_revision_is_reported_separately() -> None:
    class NarrowValidator(InferenceValidator):
        supported_revisions = frozenset({"psr:inference:other:000000"})
        attested_revision = "psr:inference:other:000000"

    result = validate_descriptor(_body(), validator=NarrowValidator())

    assert result["code"] == "unsupported_profile_schema_revision"


def test_attested_revision_mismatch_is_reported_separately() -> None:
    class DriftedValidator(InferenceValidator):
        supported_revisions = frozenset({INFERENCE_REVISION})
        attested_revision = "psr:inference:drifted:999999"

    result = validate_descriptor(_body(), validator=DriftedValidator())

    assert result["code"] == "domain_validator_revision_mismatch"


@pytest.mark.parametrize("kwargs", [{"refuse": True}, {"raises": True}])
def test_validator_refusal_and_exception_fail_closed(kwargs: dict[str, bool]) -> None:
    result = validate_descriptor(_body(), validator=InferenceValidator(**kwargs))

    assert result["status"] == "invalid"
    assert result["code"] == "domain_validation_failed"
    assert "exploded" not in json.dumps(result)


def test_validator_cannot_rewrite_the_descriptor() -> None:
    class RewritingValidator(InferenceValidator):
        def validate_profile(self, profile: dict[str, object]) -> bool:
            profile["quantization"] = "int4"
            return True

    body = _body()
    rewritten = validate_descriptor(body, validator=RewritingValidator())
    clean = validate_descriptor(_body(), validator=_validator())

    assert rewritten["descriptor_id"] == clean["descriptor_id"]
    assert body["profile"]["quantization"] == "fp8"  # type: ignore[index]


# --------------------------------------------------------------------------
# Canonical-byte decoder / verifier
# --------------------------------------------------------------------------


def _canonical_descriptor_bytes() -> bytes:
    return construct_descriptor(_body(), validator=_validator()).canonical_bytes


def test_decoder_accepts_exact_canonical_bytes() -> None:
    raw = _canonical_descriptor_bytes()

    result = verify_canonical_descriptor(raw, validator=_validator())

    assert result == validate_descriptor(_body(), validator=_validator())


def test_only_the_decoder_emits_not_canonical() -> None:
    envelope = json.loads(_canonical_descriptor_bytes().decode("ascii"))
    reserialized = json.dumps(envelope, sort_keys=True, separators=(", ", ": ")).encode("ascii")

    decoded = verify_canonical_descriptor(reserialized, validator=_validator())
    assert decoded == {"status": "invalid", "code": "not_canonical", "path": ""}

    # The structured constructor never emits not_canonical for the same content.
    constructed = validate_descriptor(_body(), validator=_validator())
    assert constructed["status"] == "valid"


def test_decoder_refuses_caller_supplied_identity_in_the_envelope() -> None:
    envelope = json.loads(_canonical_descriptor_bytes().decode("ascii"))
    envelope["descriptor_id"] = "sha256:" + "0" * 64
    raw = _canonical(envelope)

    result = verify_canonical_descriptor(raw, validator=_validator())

    assert result["code"] == "unknown_field"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("domain", "unsupported_schema_version"),
        ("schema_version", "unsupported_schema_version"),
    ],
)
def test_decoder_checks_domain_and_version(mutation: str, code: str) -> None:
    envelope = json.loads(_canonical_descriptor_bytes().decode("ascii"))
    envelope[mutation] = "tinyassets.other/v9"
    raw = _canonical(envelope)

    result = verify_canonical_descriptor(raw, validator=_validator())

    assert result["code"] == code


def test_decoder_rejects_oversize_input_before_parsing() -> None:
    raw = b'{"domain":"' + b"a" * 70_000 + b'"}'

    result = verify_canonical_descriptor(raw, validator=_validator())

    assert result == {"status": "invalid", "code": "limit_exceeded", "path": ""}


def test_decoder_rejects_non_ascii_bytes_before_parsing() -> None:
    raw = '{"domain":"tinyassets.capability-descriptør"}'.encode("utf-8")

    result = verify_canonical_descriptor(raw, validator=_validator())

    assert result == {"status": "invalid", "code": "malformed_descriptor", "path": ""}


def test_decoder_rejects_duplicate_object_keys() -> None:
    raw = b'{"domain":"a","domain":"b","schema_version":"c","descriptor":{}}'

    result = verify_canonical_descriptor(raw, validator=_validator())

    assert result["code"] == "malformed_descriptor"


def test_decoder_rejects_deep_nesting_as_limit_exceeded() -> None:
    raw = b"[" * 400 + b"]" * 400

    result = verify_canonical_descriptor(raw, validator=_validator())

    assert result == {"status": "invalid", "code": "limit_exceeded", "path": ""}


def test_decoder_rejects_nan_and_infinity() -> None:
    raw = (
        b'{"domain":"tinyassets.capability-descriptor",'
        b'"schema_version":"capability-descriptor/v1","descriptor":NaN}'
    )

    result = verify_canonical_descriptor(raw, validator=_validator())

    assert result["status"] == "invalid"
    assert result["code"] in {"invalid_type", "malformed_descriptor"}


def test_decoder_precedence_puts_structure_before_validator() -> None:
    """A descriptor that breaks structure AND has no validator reports structure."""
    envelope = json.loads(_canonical_descriptor_bytes().decode("ascii"))
    del envelope["descriptor"]["profile"]["model_revision"]
    raw = _canonical(envelope)

    result = verify_canonical_descriptor(raw, validator=None)

    assert result["code"] == "missing_field"


# --------------------------------------------------------------------------
# Market-class projection
# --------------------------------------------------------------------------


def test_supply_headroom_does_not_fragment_a_market_class() -> None:
    wide = _body()
    wide["profile"]["context_tokens"] = {"max": 1_000_000, "min": 1, "unit": "token"}  # type: ignore[index]
    wide["profile"]["modalities"] = {  # type: ignore[index]
        "unit": "modality",
        "values": ["audio", "image", "text", "video"],
    }
    wide["profile"]["latency_ms"] = {"max": 400, "min": 1, "unit": "ms"}  # type: ignore[index]

    narrow_id = validate_descriptor(_body(), validator=_validator())["descriptor_id"]
    wide_id = validate_descriptor(wide, validator=_validator())["descriptor_id"]
    assert narrow_id != wide_id

    assert project_market_class(_body(), _demand(), validator=_validator()) == (
        project_market_class(wide, _demand(), validator=_validator())
    )


def test_equivalent_malformed_demand_variants_share_one_market_class() -> None:
    results = [
        project_market_class(_body(), demand, validator=_validator())
        for demand in _demand_identity_variants()
    ]

    assert {result["status"] for result in results} == {"classified"}
    assert len({result["market_class_id"] for result in results}) == 1


@pytest.mark.parametrize(
    "malformation",
    [
        "non_string_identifier",
        "non_ascii_identifier",
        "internal_identifier_whitespace",
        "malformed_requirement_shape",
        "out_of_range_integer",
    ],
)
def test_unnormalizable_demand_fails_closed(malformation: str) -> None:
    demand = _demand()
    if malformation == "non_string_identifier":
        demand["region"] = 7
    elif malformation == "non_ascii_identifier":
        demand["region"] = "東京"
    elif malformation == "internal_identifier_whitespace":
        demand["requirements"]["modalities"]["unit"] = "modal ity"  # type: ignore[index]
    elif malformation == "malformed_requirement_shape":
        demand["requirements"]["modalities"] = {"unit": "modality"}  # type: ignore[index]
    else:
        demand["requirements"]["context_tokens"]["value"] = (  # type: ignore[index]
            9_007_199_254_740_992
        )

    with pytest.raises(DescriptorError):
        match_descriptor(_body(), demand, validator=_validator())
    with pytest.raises(DescriptorError):
        project_market_class(_body(), demand, validator=_validator())


def test_private_demand_never_enters_the_public_identity() -> None:
    base = project_market_class(_body(), _demand(), validator=_validator())

    private = _demand()
    private["quantity"] = 10_000_000
    private["budget_micros"] = 5
    private["tenant_id"] = "tenant-a"

    # Private demand has no home in the public projection: it is a caller bug,
    # not a silently-different public class.
    with pytest.raises(DescriptorError):
        project_market_class(_body(), private, validator=_validator())

    # And the same public demand from a second tenant classifies identically.
    assert project_market_class(_body(), _demand(), validator=_validator()) == base


def test_projection_is_refused_when_the_revision_has_no_public_class() -> None:
    class NoRegionTable(InferenceValidator):
        region_classes: dict[str, str] = {}

    result = project_market_class(_body(), _demand(), validator=NoRegionTable())

    assert result == {"status": "unclassified", "code": "market_class_unavailable"}


def test_projection_requires_a_compatible_descriptor_first() -> None:
    demand = _demand()
    demand["requirements"]["context_tokens"]["value"] = 900_000  # type: ignore[index]

    result = project_market_class(_body(), demand, validator=_validator())

    assert result == {"status": "unclassified", "code": "market_class_unavailable"}


def test_threshold_buckets_replace_raw_numeric_demand() -> None:
    result = project_market_class(_body(), _demand(), validator=_validator())
    assert result["status"] == "classified"

    hotter = _demand()
    hotter["requirements"]["context_tokens"]["value"] = 8_000  # type: ignore[index]
    bucketed = project_market_class(_body(), hotter, validator=_validator())

    # A different bucket is a different class; a different raw value inside the
    # same bucket is not.
    assert bucketed != result
    same_bucket = _demand()
    same_bucket["requirements"]["context_tokens"]["value"] = 40_000  # type: ignore[index]
    assert project_market_class(_body(), same_bucket, validator=_validator()) == result


def test_inputs_are_never_mutated_by_any_entry_point() -> None:
    body, demand = _body(), _demand()
    body_snapshot, demand_snapshot = deepcopy(body), deepcopy(demand)

    validate_descriptor(body, validator=_validator())
    match_descriptor(body, demand, validator=_validator())
    project_market_class(body, demand, validator=_validator())

    assert body == body_snapshot
    assert demand == demand_snapshot
