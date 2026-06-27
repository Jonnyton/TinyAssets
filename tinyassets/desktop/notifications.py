"""Notification helpers for desktop events.

Provides a thin abstraction over platform-specific notification
mechanisms (pystray toast, win32 balloon, etc.).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NotificationManager:
    """Manages notifications through the tray icon or fallback logging.

    Parameters
    ----------
    tray : TrayApp | None
        System tray instance.  If None, notifications are logged only.
    """

    def __init__(self, tray: Any = None) -> None:
        self._tray = tray

    def chapter_complete(self, chapter: int, word_count: int = 0) -> None:
        """Notify that a chapter has been completed."""
        title = f"Chapter {chapter} Complete"
        msg = f"Words written: {word_count}" if word_count else ""
        self._send(title, msg)

    def book_complete(self, title: str, total_words: int = 0) -> None:
        """Notify that a book has been completed."""
        heading = f"Book Complete: {title}"
        msg = f"Total words: {total_words}" if total_words else ""
        self._send(heading, msg)

    def stuck_recovery(self, level: int) -> None:
        """Notify that stuck recovery has been initiated."""
        self._send(
            "Stuck Recovery",
            f"Recovery initiated at level {level}",
        )

    def error(self, message: str) -> None:
        """Notify about an error condition."""
        self._send("TinyAssets Error", message[:200])

    def _send(self, title: str, message: str) -> None:
        if self._tray is not None:
            try:
                self._tray.notify(title, message)
                return
            except Exception:
                logger.debug("Tray notification failed", exc_info=True)

        # Fallback: log the notification.
        logger.info("Notification: %s -- %s", title, message)
