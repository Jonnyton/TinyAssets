"""Redirect permission identity; no network, grant or owner state is changed."""

import json
import runpy
from pathlib import Path

import pytest

from tinyassets.api.http_connection import _canonical_endpoint_set, _canonical_policy
from tinyassets.api.pending_requests import _granted_lines, _validated_endpoint_list
from tinyassets.storage.outbound_connections import (
    ConnectionLedger,
    OutboundEndpoint,
    SsrfValidationError,
    _parse_allowed_endpoints,
    _validate_endpoint,
)


def _endpoint(**changes):
    return {
        "host": "api.example.com", "path_template": "/download", "methods": ["GET"],
        **changes,
    }


def test_no_follow_omission_preserves_legacy_projection_and_identity():
    old = _validate_endpoint(_endpoint())
    explicit = _validate_endpoint(_endpoint(redirect_mode="none"))
    assert old == explicit
    assert old.redirect_mode == "none"
    assert "redirect_mode" not in old.as_dict()
    assert old.as_dict() == {
        "host": "api.example.com", "path_template": "/download", "methods": ["GET"],
        "param_patterns": {}, "allowed_query": [], "query_patterns": {}, "required_query": [],
    }
    assert _canonical_policy([_endpoint()]) == _canonical_policy([
        _endpoint(redirect_mode="none"),
    ])


def test_explicit_get_permission_survives_json_and_typed_round_trips():
    endpoint = _validate_endpoint(_endpoint(redirect_mode="public_https_get"))
    assert endpoint.redirect_mode == "public_https_get"
    assert endpoint.as_dict()["redirect_mode"] == "public_https_get"
    assert _validate_endpoint(endpoint) == endpoint
    assert _parse_allowed_endpoints(json.dumps([endpoint.as_dict()])) == (endpoint,)


@pytest.mark.parametrize("mode", [None, True, False, 0, 1, {}, [], "", "all", "NONE",
                                      "public_https_get ", " public_https_get"])
def test_unknown_or_coerced_redirect_permission_is_refused(mode):
    with pytest.raises(SsrfValidationError, match="redirect_mode"):
        _validate_endpoint(_endpoint(redirect_mode=mode))


@pytest.mark.parametrize("methods", [["POST"], ["GET", "POST"], ["PUT", "GET"]])
def test_redirect_authority_cannot_apply_to_mixed_or_mutating_endpoints(methods):
    with pytest.raises(SsrfValidationError, match="GET-only"):
        _validate_endpoint(_endpoint(methods=methods, redirect_mode="public_https_get"))


def test_redirect_permission_does_not_add_unsupported_http_verbs():
    with pytest.raises(SsrfValidationError, match="endpoint method is not permitted"):
        _validate_endpoint(_endpoint(methods=["HEAD"], redirect_mode="public_https_get"))


def test_typed_object_cannot_bypass_permission_validation():
    endpoint = OutboundEndpoint("api.example.com", "/download", ("POST",),
                                redirect_mode="public_https_get")
    with pytest.raises(SsrfValidationError, match="GET-only"):
        _validate_endpoint(endpoint)


def test_new_permission_changes_canonical_policy_and_endpoint_union():
    old = _validate_endpoint(_endpoint()).as_dict()
    opted = _validate_endpoint(_endpoint(redirect_mode="public_https_get")).as_dict()
    assert _canonical_policy([old]) != _canonical_policy([opted])
    assert len(_canonical_endpoint_set([old, opted])) == 2
    assert _canonical_policy([old, opted]) == _canonical_policy([opted, old])


def test_no_follow_keeps_existing_mutating_endpoint_behavior():
    endpoint = _validate_endpoint(_endpoint(methods=["POST", "GET"], redirect_mode="none"))
    assert endpoint.methods == ("POST", "GET")
    assert "redirect_mode" not in endpoint.as_dict()


@pytest.fixture(scope="module")
def legacy_policy():
    return runpy.run_path(str(Path(__file__).with_name("fixtures") / "legacy_download_policy.py"))


def test_frozen_legacy_reader_discards_unknown_permission(legacy_policy):
    opted = _validate_endpoint(_endpoint(redirect_mode="public_https_get"))
    old = legacy_policy["_parse_allowed_endpoints"](json.dumps([opted.as_dict()]))[0]
    assert not hasattr(old, "redirect_mode")
    assert old.as_dict() == _validate_endpoint(_endpoint()).as_dict()
    assert _parse_allowed_endpoints(json.dumps([old.as_dict()]))[0].redirect_mode == "none"


def test_request_normalization_preserves_explicit_permission_and_owner_explanation():
    endpoints = _validated_endpoint_list({
        "endpoints": [_endpoint(redirect_mode="public_https_get")],
    })
    assert endpoints[0]["redirect_mode"] == "public_https_get"
    assert _granted_lines({"endpoints": endpoints}) == [
        "GET api.example.com/download (may follow public HTTPS redirects "
        "without sharing this key with another origin)",
    ]


def test_request_no_follow_identity_and_sentence_remain_unchanged():
    old = _validated_endpoint_list({"endpoints": [_endpoint()]})
    explicit = _validated_endpoint_list({"endpoints": [_endpoint(redirect_mode="none")]})
    assert old == explicit
    assert _granted_lines({"endpoints": explicit}) == ["GET api.example.com/download"]


@pytest.mark.parametrize("mode", [None, "all", True, "public_https_get "])
def test_request_normalization_cannot_hide_invalid_permission(mode):
    with pytest.raises(SsrfValidationError, match="redirect_mode"):
        _validated_endpoint_list({"endpoints": [_endpoint(redirect_mode=mode)]})


@pytest.mark.parametrize("access_mode", ["exact", "full"])
def test_frozen_legacy_writer_loses_opt_in_without_broadening_other_policy(
    tmp_path, legacy_policy, access_mode,
):
    db_path = tmp_path / "rollback.db"
    current = ConnectionLedger(db_path)
    current.create_connection(
        connection_id="download", owner_user_id="owner", connection_class="outbound-mcp",
        scopes=("GET",), provider="http", destination="download",
        credential_ref="vault://http/download", connection_type="http", auth_scheme="bearer",
        allowed_endpoints=[_endpoint(redirect_mode="public_https_get")], access_mode=access_mode,
    )
    incarnation = current.incarnation("download")
    endpoints_json, scopes_json = current.policy_json("download")
    legacy = legacy_policy["LegacyConnectionLedger"](db_path)
    assert legacy.extend_http_connection_endpoints(
        connection_id="download", endpoints=json.loads(endpoints_json), scopes=("GET",),
        expected_endpoints_json=endpoints_json, expected_scopes_json=scopes_json,
    )
    restored = ConnectionLedger(db_path).get_connection("download")
    assert restored.allowed_endpoints[0].redirect_mode == "none"
    assert restored.access_mode == access_mode
    assert restored.scopes == ("GET",)
    assert current.incarnation("download") == incarnation
    # Reopening/upgrading the ledger cannot recover permission erased by rollback.
    assert "redirect_mode" not in current.policy_json("download")[0]
