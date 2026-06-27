"""Book-close node -- book graph; terminal node after all chapters done or stuck recovery."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def book_close(state: dict[str, Any]) -> dict[str, Any]:
    """Close out a completed book.

    When a MemoryManager is available, runs final promotion gates
    to promote any remaining facts accumulated during the book.

    Parameters
    ----------
    state : BookState
        Must contain ``book_number`` and ``chapters_completed``.

    Returns
    -------
    dict
        Partial state with:
        - ``book_summary``: summary of the completed book.
    """
    from tinyassets import runtime_singletons as runtime

    mgr = runtime.memory_manager
    if mgr is not None:
        try:
            result = mgr.run_promotion_gates()
            logger.info(
                "Book close: promoted %d facts, %d style rules",
                len(result.promoted_facts),
                len(result.promoted_style_rules),
            )
        except Exception as e:
            logger.warning("Book close promotion failed: %s", e)

    # Promote book-level promises to series level
    tracker = runtime.promise_tracker
    if tracker is not None:
        try:
            promises = state.get("extracted_promises", [])
            book_number = state.get("book_number", 1)
            promoted = tracker.promote_from_book(promises, book=book_number)
            logger.info(
                "Book close: promoted %d promises to series level",
                promoted,
            )
        except Exception as e:
            logger.warning("Series promise promotion failed: %s", e)

    return {
        "book_summary": (
            f"Book {state['book_number']} completed with "
            f"{state['chapters_completed']} chapters."
        ),
    }
