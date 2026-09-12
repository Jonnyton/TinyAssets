"""Versioned owner preferences, never a provider grant or actual-model receipt."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from tinyassets.providers.model_policy import Charge, ModelPolicy, ModelRef

MAX_FALLBACKS = 1024
MAX_GENERATION = 2**63 - 1
MAX_POLICY_BYTES = 4 * 1024 * 1024


def exact_generation(value: object) -> int:
    if type(value) is not int or not 0 <= value <= MAX_GENERATION:
        raise ValueError("invalid preference generation")
    return value


def _identifier(value: object, limit: int, *, empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or (not value and not empty)
        or len(value) > limit
        or value != value.strip()
        or (value and not value.isprintable())
        or any(0xD800 <= ord(char) <= 0xDFFF for char in value)
    ):
        raise ValueError("invalid model preference identifier")
    return value


def _object(value: object, fields: set[str]) -> dict:
    if not isinstance(value, dict) or value.keys() != fields:
        raise ValueError("invalid model preference fields")
    return value


def _ref(value: object) -> ModelRef:
    doc = _object(value, {"provider_ref", "model_id"})
    return ModelRef(
        _identifier(doc["provider_ref"], 400),
        _identifier(doc["model_id"], 200, empty=True),
    )


def _ref_doc(ref: ModelRef | None) -> dict[str, str] | None:
    if ref is None:
        return None
    return {"provider_ref": ref.connection_id, "model_id": ref.model_id}


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate model preference field")
        result[key] = value
    return result


def strict_json(raw: bytes | str) -> object:
    """Bounded JSON, including duplicate-key rejection at every nesting level."""
    if not isinstance(raw, (bytes, str)):
        raise ValueError("invalid model preferences JSON")
    try:
        size = len(raw if isinstance(raw, bytes) else raw.encode("utf-8"))
        if size > MAX_POLICY_BYTES:
            raise ValueError("model preferences too large")
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        return json.loads(text, object_pairs_hook=_unique_object)
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("invalid model preferences JSON") from exc


@dataclass(frozen=True, slots=True)
class ModelPreferences:
    mode: Literal["automatic", "explicit"]
    saved_default: ModelRef | None
    fallbacks: tuple[ModelRef, ...]

    def __post_init__(self) -> None:
        if self.mode not in ("automatic", "explicit") or type(self.fallbacks) is not tuple:
            raise ValueError("invalid model preference mode or order")
        if len(self.fallbacks) > MAX_FALLBACKS:
            raise ValueError("too many model fallbacks")
        if self.mode == "automatic":
            if self.saved_default is not None or self.fallbacks:
                raise ValueError("automatic preferences cannot contain an explicit order")
        elif self.saved_default is None:
            raise ValueError("explicit preferences require a default")
        refs = (() if self.saved_default is None else (self.saved_default,)) + self.fallbacks
        for ref in refs:
            if type(ref) is not ModelRef:
                raise ValueError("invalid model reference")
            _identifier(ref.connection_id, 400)
            _identifier(ref.model_id, 200, empty=True)
        if len(set(refs)) != len(refs):
            raise ValueError("duplicate model preference reference")

    @classmethod
    def from_document(cls, value: object) -> ModelPreferences:
        doc = _object(value, {"version", "mode", "saved_default", "fallbacks"})
        if type(doc["version"]) is not int or doc["version"] != 1:
            raise ValueError("unsupported model preference version")
        if not isinstance(doc["fallbacks"], list) or len(doc["fallbacks"]) > MAX_FALLBACKS:
            raise ValueError("invalid model fallback order")
        return cls(
            mode=doc["mode"],
            saved_default=None if doc["saved_default"] is None else _ref(doc["saved_default"]),
            fallbacks=tuple(_ref(ref) for ref in doc["fallbacks"]),
        )

    def document(self) -> dict:
        return {
            "version": 1,
            "mode": self.mode,
            "saved_default": _ref_doc(self.saved_default),
            "fallbacks": [_ref_doc(ref) for ref in self.fallbacks],
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.document(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )


def parse_preference_write(raw: bytes) -> tuple[int, ModelPreferences]:
    doc = _object(strict_json(raw), {"expected_generation", "policy"})
    return exact_generation(doc["expected_generation"]), ModelPreferences.from_document(
        doc["policy"]
    )


def capture_preference_policy(
    *, saved: ModelPreferences | None, observed_generation: int,
    current: ModelPreferences | None = None, ranking_source: str | None = None,
    cost_caps: tuple[Charge, ...] | None = None,
) -> tuple[ModelPolicy, str] | None:
    """Convert validated choices to one advisory plan, without reading or saving.

    The authenticated caller supplies observed storage state and trusted ranking/
    cost bounds. This neither discovers models nor grants execution authority.
    None preserves the legacy path when no choice exists. Current automatic is
    an override too: it clears the saved primary and tail for this turn only.
    """
    exact_generation(observed_generation)
    for value in (saved, current):
        if value is not None and type(value) is not ModelPreferences:
            raise ValueError("invalid model preferences")
    if (saved is None) != (observed_generation == 0):
        raise ValueError("preference generation does not match saved state")
    if saved is None and current is None:
        return None
    chosen = current if current is not None else saved
    return ModelPolicy(
        generation=observed_generation, mode=chosen.mode, fallbacks=chosen.fallbacks,
        current_selection=None if current is None else current.saved_default,
        saved_default=chosen.saved_default if current is None else None,
        ranking_source=ranking_source, cost_caps=cost_caps,
    ), "current" if current is not None else "saved"
