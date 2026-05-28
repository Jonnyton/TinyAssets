"""Tag-matrix filtering for knowledge and retrieval rows.

The tag matrix is a refinement layer above hard memory scope. Scope decides
which universe/user/branch a caller may see; tags decide which eligible
documents are relevant to the current universe/domain/shape/commons query.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from workflow.memory.scoping import MemoryScope

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommonsPromotionRecord:
    """INV-5 promotion evidence for a private-canon shape entering commons."""

    source_universe: str
    shape_tag: str
    promoter_identity: str
    declassification_reason: str
    resolver_decision: str
    timestamp: str

    def is_complete(self) -> bool:
        return all(
            str(value).strip()
            for value in (
                self.source_universe,
                self.shape_tag,
                self.promoter_identity,
                self.declassification_reason,
                self.resolver_decision,
                self.timestamp,
            )
        )


@dataclass(frozen=True)
class KnowledgeTags:
    """Tag-matrix labels attached to one knowledge/retrieval row."""

    universes: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    shapes: tuple[str, ...] = ()
    general: bool = False
    commons: bool = False
    private_canon: bool = False
    promotion_record: CommonsPromotionRecord | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "universes", _normalize_values(self.universes))
        object.__setattr__(self, "domains", _normalize_values(self.domains))
        object.__setattr__(self, "shapes", _normalize_values(self.shapes))

    @property
    def is_tagged(self) -> bool:
        return bool(
            self.universes
            or self.domains
            or self.shapes
            or self.general
            or self.commons
            or self.private_canon
        )

    def commons_promotion_complete(self) -> bool:
        if not (self.commons and self.private_canon):
            return True
        return (
            self.promotion_record is not None
            and self.promotion_record.is_complete()
        )

    def as_row_metadata(self) -> dict[str, Any]:
        """Serialize tags into flat row metadata columns."""
        return {
            "tag_universes": json.dumps(list(self.universes)),
            "tag_domains": json.dumps(list(self.domains)),
            "tag_shapes": json.dumps(list(self.shapes)),
            "tag_general": int(self.general),
            "tag_commons": int(self.commons),
            "tag_private_canon": int(self.private_canon),
            "promotion_record": (
                json.dumps(self.promotion_record.__dict__)
                if self.promotion_record is not None
                else ""
            ),
        }


@dataclass(frozen=True)
class TagMatrixQuery:
    """Tag filter requested by a retrieval caller."""

    domain_tags: tuple[str, ...] = ()
    shape_tags: tuple[str, ...] = ()
    include_general: bool = True
    include_commons: bool = True
    include_untagged: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "domain_tags", _normalize_values(self.domain_tags)
        )
        object.__setattr__(
            self, "shape_tags", _normalize_values(self.shape_tags)
        )


def knowledge_tags_from_mapping(value: Any) -> KnowledgeTags:
    """Build ``KnowledgeTags`` from flat or nested row metadata."""
    if isinstance(value, KnowledgeTags):
        return value
    if value is None:
        return KnowledgeTags()

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return KnowledgeTags()
    if not isinstance(value, dict):
        return KnowledgeTags()

    nested = value.get("tag_matrix")
    if isinstance(nested, dict):
        value = {**value, **nested}

    record = _promotion_record_from_value(
        value.get("promotion_record")
        or value.get("commons_promotion_record")
    )
    return KnowledgeTags(
        universes=_read_values(value, "tag_universes", "universes"),
        domains=_read_values(value, "tag_domains", "domains"),
        shapes=_read_values(value, "tag_shapes", "shapes"),
        general=_read_bool(value, "tag_general", "general"),
        commons=_read_bool(value, "tag_commons", "commons"),
        private_canon=_read_bool(value, "tag_private_canon", "private_canon"),
        promotion_record=record,
    )


def knowledge_tags_from_row(row: Any) -> KnowledgeTags:
    """Extract tag metadata from a dict/dataclass/object row."""
    if isinstance(row, str):
        return KnowledgeTags()
    if isinstance(row, dict):
        return knowledge_tags_from_mapping(row)

    data: dict[str, Any] = {}
    for key in (
        "tag_matrix",
        "tag_universes",
        "tag_domains",
        "tag_shapes",
        "tag_general",
        "tag_commons",
        "tag_private_canon",
        "promotion_record",
        "commons_promotion_record",
    ):
        if hasattr(row, key):
            data[key] = getattr(row, key)
    return knowledge_tags_from_mapping(data)


def row_visible_for_tag_matrix(
    row: Any,
    *,
    scope: MemoryScope,
    query: TagMatrixQuery,
) -> bool:
    """Return True when a row's tags are visible for ``scope`` and ``query``."""
    tags = knowledge_tags_from_row(row)
    if not tags.is_tagged:
        return query.include_untagged

    if not tags.commons_promotion_complete():
        logger.warning(
            "tag_matrix.inv5_block: dropped row without complete "
            "commons promotion record (scope=%s, tags=%s)",
            scope.compose_predicate(),
            tags,
        )
        return False

    if tags.universes and scope.universe_id not in tags.universes:
        if not (tags.general or (tags.commons and query.include_commons)):
            return False

    if tags.general and not query.include_general:
        return False
    if tags.commons and not query.include_commons:
        return False

    if query.domain_tags:
        if tags.domains:
            if not _intersects(tags.domains, query.domain_tags) and not tags.general:
                return False
        elif not tags.general:
            return False

    if query.shape_tags:
        if tags.shapes:
            if not _intersects(tags.shapes, query.shape_tags) and not tags.general:
                return False
        elif not tags.general:
            return False

    return True


def filter_rows_by_tag_matrix(
    rows: Iterable[Any],
    *,
    scope: MemoryScope,
    query: TagMatrixQuery | None,
) -> list[Any]:
    """Filter rows by tag matrix after hard scope filtering."""
    if query is None:
        return list(rows)
    return [
        row
        for row in rows
        if row_visible_for_tag_matrix(row, scope=scope, query=query)
    ]


def _normalize_values(values: Iterable[Any] | None) -> tuple[str, ...]:
    if isinstance(values, str):
        values = (values,)
    output: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return tuple(output)


def _intersects(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    return bool(set(left) & set(right))


def _read_values(data: dict[str, Any], *keys: str) -> tuple[str, ...]:
    for key in keys:
        if key not in data:
            continue
        value = data[key]
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return ()
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                decoded = [part.strip() for part in stripped.split(",")]
            value = decoded
        if isinstance(value, Iterable) and not isinstance(value, (bytes, str)):
            return _normalize_values(value)
        return _normalize_values([value])
    return ()


def _read_bool(data: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        if key not in data:
            continue
        value = data[key]
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _promotion_record_from_value(value: Any) -> CommonsPromotionRecord | None:
    if isinstance(value, CommonsPromotionRecord):
        return value
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, dict):
        return None
    return CommonsPromotionRecord(
        source_universe=str(value.get("source_universe", "") or ""),
        shape_tag=str(value.get("shape_tag", "") or ""),
        promoter_identity=str(value.get("promoter_identity", "") or ""),
        declassification_reason=str(
            value.get("declassification_reason", "") or ""
        ),
        resolver_decision=str(value.get("resolver_decision", "") or ""),
        timestamp=str(value.get("timestamp", "") or ""),
    )
