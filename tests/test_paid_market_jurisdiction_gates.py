from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from tinyassets.paid_market.instruments import LegalReview, jurisdiction_gate

NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)


def _review(**changes: object) -> LegalReview:
    values: dict[str, object] = {
        "review_id": "legal-review-1",
        "jurisdiction": "US",
        "policy_version": "jurisdiction-v1",
        "reviewer_kind": "specialist_counsel",
        "issued_at": NOW - timedelta(days=1),
        "valid_until": NOW + timedelta(days=30),
        "covered_products": frozenset({"forward", "training", "hardware"}),
        "findings_digest": "sha256:legal-findings",
        "includes_forward_contract_analysis": True,
        "includes_export_control_analysis": True,
        "includes_money_rules_analysis": True,
    }
    values.update(changes)
    return LegalReview(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("product", ["forward", "training", "hardware"])
def test_missing_review_keeps_sensitive_route_dark(product: str) -> None:
    result = jurisdiction_gate(product, "US", now=NOW, review=None)

    assert result.status == "dark"
    assert result.reason == "legal_review_missing"
    assert result.is_legal_approval is False
    assert result.advertisable is False
    assert result.executable is False


@pytest.mark.parametrize(
    ("review", "reason"),
    [
        (_review(valid_until=NOW), "legal_review_stale"),
        (_review(jurisdiction="EU"), "jurisdiction_mismatch"),
        (_review(reviewer_kind="automated_policy"), "specialist_review_required"),
        (
            _review(covered_products=frozenset({"forward"})),
            "product_not_reviewed",
        ),
        (
            _review(includes_forward_contract_analysis=False),
            "forward_analysis_missing",
        ),
        (
            _review(includes_export_control_analysis=False),
            "export_control_analysis_missing",
        ),
        (
            _review(includes_money_rules_analysis=False),
            "money_rules_analysis_missing",
        ),
    ],
)
def test_stale_mismatched_or_incomplete_review_fails_closed(
    review: LegalReview, reason: str
) -> None:
    product = "training" if reason == "product_not_reviewed" else "forward"
    result = jurisdiction_gate(product, "US", now=NOW, review=review)

    assert result.status == "dark"
    assert result.reason == reason
    assert result.is_legal_approval is False


@pytest.mark.parametrize("product", ["forward", "training", "hardware"])
def test_current_specialist_review_binds_policy_but_is_not_legal_approval(
    product: str,
) -> None:
    result = jurisdiction_gate(product, "US", now=NOW, review=_review())

    assert result.status == "eligible"
    assert result.review_id == "legal-review-1"
    assert result.policy_version == "jurisdiction-v1"
    assert result.is_legal_approval is False
    assert result.advertisable is True
    assert result.executable is True
    assert "not legal approval" in result.caveat.lower()


def test_automated_label_cannot_be_presented_as_specialist_approval() -> None:
    automated = replace(_review(), reviewer_kind="automated_policy")
    result = jurisdiction_gate("hardware", "US", now=NOW, review=automated)

    assert result.status == "dark"
    assert result.is_legal_approval is False
    assert result.advertisable is False
