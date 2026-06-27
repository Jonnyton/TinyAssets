"""One-shot / --watch helper: click the inline "Always allow" button Claude.ai
renders inside the chat transcript for per-tool permission approvals.

Claude.ai's newer permission UX is NOT a modal (no role=dialog / aria-modal).
It's an inline card with three buttons: "Always allow" (latches + approves),
an Enter-key one-shot allow, and Deny. `claude_chat.py dismiss-dialogs` only
scopes to dialog containers, so it can't see this and returns 0.

This helper is scoped: it looks for a <button> whose visible text equals
"Always allow" and whose ancestor contains the phrase "wants to use" or
"TinyAssets Server" (the permission-card text shell — matches the connector's
shipped display_name from packaging/conway/panel-metadata.json). It clicks
that button and only that button.

The detector logic has been folded into ``claude_chat.py`` itself
(``_dismiss_inline_permission_card``). This script remains as a
standalone watcher for situations where the host wants a dedicated
out-of-band clicker (e.g. a long-running user-sim session without an
active ``claude_chat.py ask``).

Usage:
    python scripts/always_allow_watch.py           # one-shot
    python scripts/always_allow_watch.py --watch   # every 10s
"""
from __future__ import annotations

import argparse
import io
import sys
import time

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True,
    )
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True,
    )

from playwright.sync_api import sync_playwright

CDP = "http://localhost:9222"


def _click_inline_always_allow(page) -> dict:
    # Find the permission card by its distinctive text, then click the
    # "Always allow" button inside it. Scoped to prevent random clicks.
    return page.evaluate(
        """
        () => {
          // Gate: ensure a permission card is present on the page. Only then
          // do we hunt for the "Always allow" button anywhere in the doc.
          const allText = document.body ? (document.body.innerText || '') : '';
          if (!/Claude wants to use/i.test(allText)) {
            return {found: false, reason: 'no permission card text on page'};
          }
          if (!/TinyAssets(?: Server)?/i.test(allText)) {
            return {found: false, reason: 'permission card not TinyAssets Server'};
          }
          const buttons = Array.from(document.querySelectorAll('button'));
          const btn = buttons.find(b => {
            const t = (b.innerText || '').trim();
            return /^always allow\\b/i.test(t) && b.offsetParent !== null;
          });
          if (!btn) {
            return {found: false, reason: 'no visible Always-allow button'};
          }
          btn.scrollIntoView({block: 'center'});
          btn.click();
          return {found: true, clicked: true, label: (btn.innerText||'').trim()};
        }
        """
    )


def _run_once(p) -> dict:
    browser = p.chromium.connect_over_cdp(CDP)
    try:
        page = None
        for ctx in browser.contexts:
            for pg in ctx.pages:
                if "claude.ai" in (pg.url or ""):
                    page = pg
                    break
            if page:
                break
        if page is None:
            return {"error": "no claude.ai tab"}
        return _click_inline_always_allow(page)
    finally:
        browser.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="store_true")
    args = ap.parse_args()
    with sync_playwright() as p:
        if not args.watch:
            r = _run_once(p)
            print(r)
            return 0 if r.get("clicked") else 1
        while True:
            try:
                r = _run_once(p)
                if r.get("clicked"):
                    print(r, flush=True)
            except Exception as e:
                print({"error": str(e)}, flush=True)
            time.sleep(10)


if __name__ == "__main__":
    sys.exit(main())
