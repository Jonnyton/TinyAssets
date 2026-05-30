"""Tool guardrails for filtering, pagination, and summarization.

Wraps tool calls with filtering (relevance, scope, recency), pagination,
and intelligent truncation to manage context size and signal quality.

Guardrails are composable: build pipelines that chain multiple filters
in sequence.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class PaginatedResult:
    """Result of paginated query.

    Attributes
    ----------
    items : list[Any]
        Items for the requested page.
    total : int
        Total number of items available.
    page : int
        Current page number (0-indexed).
    page_size : int
        Items per page.
    has_more : bool
        Whether there are more pages after this one.
    """

    items: list[Any]
    total: int
    page: int
    page_size: int
    has_more: bool


class FilterGuardrail:
    """Filters results by relevance, scope, and recency."""

    @staticmethod
    def filter_by_relevance(
        results: list[dict[str, Any]], query: str, max_results: int = 10
    ) -> list[dict[str, Any]]:
        """Filter results by keyword relevance to query.

        Uses simple keyword overlap scoring: counts how many query terms
        appear in each result.

        Parameters
        ----------
        results : list[dict[str, Any]]
            List of result dicts, each with a 'text' or 'content' key.
        query : str
            Query string to match against.
        max_results : int, optional
            Maximum results to return (default: 10).

        Returns
        -------
        list[dict[str, Any]]
            Filtered and ranked results.
        """
        if not results or not query:
            return results[:max_results]

        # Normalize query into keywords
        query_lower = query.lower()
        query_terms = set(
            term.lower()
            for term in re.findall(r"\w+", query)
            if len(term) > 2
        )

        if not query_terms:
            return results[:max_results]

        # Score each result
        scored = []
        for result in results:
            # Try to find text in result
            text = ""
            for key in ("text", "content", "summary", "description"):
                if key in result and result[key]:
                    text = str(result[key]).lower()
                    break

            if not text:
                score = 0.0
            else:
                # Count term matches
                matches = sum(
                    1 for term in query_terms
                    if re.search(r"\b" + re.escape(term) + r"\b", text)
                )
                score = matches / len(query_terms) if query_terms else 0.0
                # Phrase bonus: if the full normalized query appears verbatim,
                # break ties in favor of that result. Small enough not to
                # outrank a result that matches more individual terms.
                if score > 0 and query_lower in text:
                    score += 0.1

            scored.append((score, result))

        # Drop zero-score results so "filter by relevance" actually filters.
        scored = [(s, r) for s, r in scored if s > 0]

        # Sort by score descending, take top N
        scored.sort(key=lambda x: x[0], reverse=True)
        return [result for _, result in scored[:max_results]]

    @staticmethod
    def filter_by_scope(
        results: list[dict[str, Any]], scope: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Filter results to match scope.

        Removes results outside the current scope (wrong universe, branch,
        author, etc.).

        Parameters
        ----------
        results : list[dict[str, Any]]
            List of results with scope metadata.
        scope : dict[str, Any]
            Current scope (universe_id, branch_id, author_id, etc.).

        Returns
        -------
        list[dict[str, Any]]
            Filtered results matching scope.
        """
        if not scope:
            return results

        filtered = []
        for result in results:
            result_scope = result.get("scope", {})
            if not result_scope:
                # No scope info, include it
                filtered.append(result)
                continue

            # Check if result scope matches current scope
            match = True
            for key, value in scope.items():
                if key in result_scope and result_scope[key] != value:
                    match = False
                    break

            if match:
                filtered.append(result)

        return filtered

    @staticmethod
    def filter_by_recency(
        results: list[dict[str, Any]], max_age_hours: float | None = None
    ) -> list[dict[str, Any]]:
        """Filter results by age.

        Removes results older than max_age_hours.

        Parameters
        ----------
        results : list[dict[str, Any]]
            List of results with timestamp metadata.
        max_age_hours : float, optional
            Maximum age in hours. None = no filtering (default: None).

        Returns
        -------
        list[dict[str, Any]]
            Filtered results.
        """
        if max_age_hours is None or max_age_hours < 0:
            return results

        import time

        cutoff_time = time.time() - (max_age_hours * 3600)
        filtered = []

        for result in results:
            # Try to find timestamp
            timestamp = result.get("timestamp") or result.get("created_at")
            if not timestamp:
                # No timestamp, include it
                filtered.append(result)
                continue

            try:
                if isinstance(timestamp, str):
                    # Try to parse ISO format
                    import datetime

                    dt = datetime.datetime.fromisoformat(
                        timestamp.replace("Z", "+00:00")
                    )
                    ts = dt.timestamp()
                else:
                    ts = float(timestamp)

                if ts >= cutoff_time:
                    filtered.append(result)
            except (ValueError, TypeError):
                # Can't parse timestamp, include it
                filtered.append(result)

        return filtered


class PaginationGuardrail:
    """Paginates large result sets."""

    @staticmethod
    def paginate(
        results: list[Any], page_size: int = 20, page: int = 0
    ) -> PaginatedResult:
        """Paginate results.

        Parameters
        ----------
        results : list[Any]
            Full list of results.
        page_size : int, optional
            Items per page (default: 20).
        page : int, optional
            Page number, 0-indexed (default: 0).

        Returns
        -------
        PaginatedResult
            Paginated results with metadata.
        """
        if page_size < 1:
            page_size = 20
        if page < 0:
            page = 0

        total = len(results)
        start = page * page_size
        end = start + page_size

        items = results[start:end]
        has_more = end < total

        return PaginatedResult(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_more=has_more,
        )


class SummarizationGuardrail:
    """Intelligently truncates content to fit token budgets."""

    @staticmethod
    def summarize_if_large(
        content: str, max_tokens: int = 1000
    ) -> str:
        """Truncate content to fit token budget.

        Attempts to break at sentence boundaries.

        Parameters
        ----------
        content : str
            Content to truncate.
        max_tokens : int, optional
            Token budget (default: 1000).

        Returns
        -------
        str
            Truncated content with marker if needed.
        """
        if not content:
            return ""

        # Rough: 4 chars per token
        max_chars = max_tokens * 4

        if len(content) <= max_chars:
            return content

        logger.debug(
            "Truncating content: %d -> %d chars", len(content), max_chars
        )

        # Try to break at sentence boundary
        truncated = content[:max_chars]
        last_period = truncated.rfind(".")
        last_newline = truncated.rfind("\n")

        break_point = max(last_period, last_newline)
        if break_point > max_chars * 0.8:  # Found good break in last 20%
            return truncated[: break_point + 1] + " [truncated]"

        return truncated + " [truncated]"

    @staticmethod
    def summarize_list(
        items: list[str], max_total_tokens: int = 2000
    ) -> list[str]:
        """Proportionally truncate items to fit total token budget.

        Allocates token budget proportionally across items.

        Parameters
        ----------
        items : list[str]
            List of strings to summarize.
        max_total_tokens : int, optional
            Total token budget (default: 2000).

        Returns
        -------
        list[str]
            Truncated items.
        """
        if not items:
            return []

        if len(items) == 1:
            return [
                SummarizationGuardrail.summarize_if_large(
                    items[0], max_total_tokens
                )
            ]

        # Allocate budget evenly across items. ``summarize_if_large`` uses
        # 4 chars/token internally, but for list summarization the budget
        # must be enforced strictly across the whole list — otherwise N
        # items each under per_item_chars but summing over budget pass
        # through unchanged. Treat ``max_total_tokens`` as a strict char
        # budget and divide directly so the total output is bounded.
        per_item_chars = max(max_total_tokens // len(items), 1)
        # Convert back to tokens for summarize_if_large's chars/token math.
        per_item_tokens = max(per_item_chars // 4, 1)

        result = []
        for item in items:
            truncated = SummarizationGuardrail.summarize_if_large(
                item, per_item_tokens
            )
            # Hard cap: if summarize_if_large left the item alone (because
            # its 4x heuristic decided it fits), still enforce the strict
            # per-item char share so the aggregate output respects budget.
            if len(truncated) > per_item_chars:
                truncated = truncated[:per_item_chars] + " [truncated]"
            result.append(truncated)

        return result


class GuardrailPipelineError(RuntimeError):
    """Raised when a guardrail pipeline step fails."""

    def __init__(
        self, step: Callable[[Any], Any], step_index: int, cause: Exception
    ) -> None:
        """Capture the failing step and original exception."""
        step_name = getattr(step, "__name__", step.__class__.__name__)
        super().__init__(
            f"Guardrail pipeline step {step_index} ({step_name}) failed: {cause}"
        )
        self.step = step
        self.step_index = step_index
        self.__cause__ = cause


class GuardrailPipeline:
    """Chains multiple guardrails in sequence.

    Builds a pipeline of filtering, pagination, and summarization steps.
    """

    def __init__(self) -> None:
        """Initialize an empty pipeline."""
        self._steps: list[Callable[[Any], Any]] = []

    def add_step(self, guardrail_fn: Callable[[Any], Any]) -> GuardrailPipeline:
        """Add a step to the pipeline.

        Parameters
        ----------
        guardrail_fn : Callable
            Guardrail function that takes input and returns output.

        Returns
        -------
        GuardrailPipeline
            Self (for chaining).
        """
        self._steps.append(guardrail_fn)
        return self

    def apply(self, data: Any) -> Any:
        """Run all pipeline steps in order.

        Parameters
        ----------
        data : Any
            Input data to process.

        Returns
        -------
        Any
            Output from final pipeline step.
        """
        result = data
        for step_index, step in enumerate(self._steps):
            try:
                result = step(result)
            except Exception as e:
                logger.warning(
                    "Pipeline step %d failed; aborting guardrail pipeline",
                    step_index,
                    exc_info=e,
                )
                raise GuardrailPipelineError(step, step_index, e) from e

        return result


# Convenience builder for common patterns
def build_retrieval_pipeline(
    query: str | None = None,
    scope: dict[str, Any] | None = None,
    max_age_hours: float | None = None,
    max_results: int | None = None,
    page_size: int | None = None,
) -> GuardrailPipeline:
    """Build a common retrieval pipeline.

    Chains relevance, scope, recency, and pagination filters.

    Parameters
    ----------
    query : str, optional
        Query for relevance filtering (default: None, skip this step).
    scope : dict[str, Any], optional
        Scope for scope filtering (default: None, skip this step).
    max_age_hours : float, optional
        Max age for recency filtering (default: None, skip this step).
    max_results : int, optional
        Max results for relevance filtering (default: None, use default).
    page_size : int, optional
        Page size for pagination (default: None, skip pagination).

    Returns
    -------
    GuardrailPipeline
        Configured pipeline ready to apply.
    """
    pipeline = GuardrailPipeline()

    if query:
        pipeline.add_step(
            lambda data: FilterGuardrail.filter_by_relevance(
                data, query, max_results or 10
            )
        )

    if scope:
        pipeline.add_step(
            lambda data: FilterGuardrail.filter_by_scope(data, scope)
        )

    if max_age_hours is not None:
        pipeline.add_step(
            lambda data: FilterGuardrail.filter_by_recency(
                data, max_age_hours
            )
        )

    if page_size:
        pipeline.add_step(
            lambda data: PaginationGuardrail.paginate(
                data, page_size
            ).items
        )

    return pipeline
