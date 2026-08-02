from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from tinyassets.execution_subject import (
    ExecutionSubject,
    ExecutionSubjectKind,
    agent_binding_automation_id,
)


def test_execution_subject_requires_typed_kind_reference_and_digest() -> None:
    subject = ExecutionSubject(
        kind=ExecutionSubjectKind.BRANCH_VERSION,
        ref="branch-example@abc12345",
        digest=f"sha256:{'a' * 64}",
    )

    assert subject.kind is ExecutionSubjectKind.BRANCH_VERSION
    assert subject.to_dict() == {
        "kind": "branch_version",
        "ref": "branch-example@abc12345",
        "digest": f"sha256:{'a' * 64}",
    }
    assert ExecutionSubject.from_dict(subject.to_dict()) == subject


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("kind", "branch_version"),
        ("ref", ""),
        ("digest", f"sha256:{'A' * 64}"),
    ),
)
def test_execution_subject_rejects_untyped_or_noncanonical_fields(
    field: str,
    value: object,
) -> None:
    values: dict[str, object] = {
        "kind": ExecutionSubjectKind.BRANCH_VERSION,
        "ref": "branch-example@abc12345",
        "digest": f"sha256:{'a' * 64}",
    }
    values[field] = value

    with pytest.raises(ValueError, match=field):
        ExecutionSubject(**values)  # type: ignore[arg-type]


def test_agent_binding_automation_id_is_reserved_stable_and_alias_free() -> None:
    with ThreadPoolExecutor(max_workers=8) as pool:
        identifiers = tuple(
            pool.map(
                lambda _index: agent_binding_automation_id("agent_binding_alice"),
                range(8),
            )
        )

    assert len(set(identifiers)) == 1
    assert identifiers[0].startswith("automation_agent_")
    assert "agent_binding_alice" not in identifiers[0]
    assert agent_binding_automation_id("agent_binding_bob") != identifiers[0]
