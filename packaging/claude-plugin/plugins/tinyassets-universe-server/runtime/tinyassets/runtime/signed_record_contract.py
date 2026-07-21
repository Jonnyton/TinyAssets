"""Immutable field contracts for domain-separated signed JSON records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol, TypeAlias

JSONValue: TypeAlias = (
    None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
)


class FieldDisposition(StrEnum):
    ROW_BOUND = "row_bound"
    SPECIALIZED_VALIDATED = "specialized_validated"
    INERT = "inert"


@dataclass(frozen=True)
class SignedFieldRule:
    disposition: FieldDisposition
    json_types: tuple[type, ...]
    inert_reason: str | None = None

    def __post_init__(self) -> None:
        if type(self.disposition) is not FieldDisposition:
            raise TypeError("field disposition must be a FieldDisposition")
        if (
            type(self.json_types) is not tuple
            or not self.json_types
            or any(type(value_type) is not type for value_type in self.json_types)
            or len(set(self.json_types)) != len(self.json_types)
        ):
            raise TypeError("json_types must be a nonempty tuple of unique types")
        has_inert_reason = (
            type(self.inert_reason) is str and bool(self.inert_reason.strip())
        )
        if self.disposition is FieldDisposition.INERT:
            if not has_inert_reason:
                raise ValueError("INERT fields require a nonempty inert_reason")
        elif self.inert_reason is not None:
            raise ValueError("only INERT fields may declare inert_reason")


class SpecializedValidator(Protocol):
    def __call__(
        self,
        payload: Mapping[str, JSONValue],
        context: object,
    ) -> None: ...


@dataclass(frozen=True)
class SignedRecordContract:
    name: str
    domain_separator: bytes
    fields: Mapping[str, SignedFieldRule]
    specialized_validator: SpecializedValidator | None

    def __post_init__(self) -> None:
        if type(self.name) is not str or not self.name.strip():
            raise ValueError("signed record contract name must be nonempty")
        if type(self.domain_separator) is not bytes or not self.domain_separator:
            raise ValueError("signed record domain separator must be nonempty bytes")
        if not isinstance(self.fields, Mapping) or not self.fields:
            raise ValueError("signed record contract must classify at least one field")
        copied_fields = dict(self.fields)
        if any(type(name) is not str or not name for name in copied_fields):
            raise ValueError("signed record field names must be nonempty strings")
        if any(
            not isinstance(rule, SignedFieldRule)
            for rule in copied_fields.values()
        ):
            raise TypeError("signed record fields must contain SignedFieldRule values")
        has_specialized = any(
            rule.disposition is FieldDisposition.SPECIALIZED_VALIDATED
            for rule in copied_fields.values()
        )
        if has_specialized != (self.specialized_validator is not None):
            raise ValueError(
                "specialized validator is required iff specialized fields exist"
            )
        if self.specialized_validator is not None and not callable(
            self.specialized_validator
        ):
            raise TypeError("specialized validator must be callable")
        object.__setattr__(self, "fields", MappingProxyType(copied_fields))

    @property
    def row_bound_fields(self) -> frozenset[str]:
        return frozenset(
            name
            for name, rule in self.fields.items()
            if rule.disposition is FieldDisposition.ROW_BOUND
        )


class SignedRecordContractRegistry:
    """Build a frozen source-defined domain contract registry."""

    @staticmethod
    def freeze(
        *contracts: SignedRecordContract,
    ) -> Mapping[bytes, SignedRecordContract]:
        registry: dict[bytes, SignedRecordContract] = {}
        for contract in contracts:
            if not isinstance(contract, SignedRecordContract):
                raise TypeError("registry entries must be SignedRecordContract values")
            if contract.domain_separator in registry:
                raise ValueError(
                    f"duplicate domain separator {contract.domain_separator!r}"
                )
            registry[contract.domain_separator] = contract
        return MappingProxyType(registry)
