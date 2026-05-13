"""Drive the real ChatGPT chat UI via Chrome DevTools Protocol.

Sibling of ``scripts/claude_chat.py``; targets ``chatgpt.com`` instead of
``claude.ai``. Reuses the same CDP-backed Chrome on port 9222 and the same
Chrome profile so a host running both can keep one Chrome window with
multiple chatbot tabs.

Setup (run ONCE by the human host, not by user-sim):

  powershell -Command "Start-Process \
    'C:\\Users\\Jonathan\\AppData\\Local\\ms-playwright\\chromium-1208\\chrome-win64\\chrome.exe' \
    -ArgumentList \
      '--user-data-dir=C:\\Users\\Jonathan\\.claude-ai-profile', \
      '--remote-debugging-port=9222', \
      '--no-first-run', \
      '--disable-blink-features=AutomationControlled', \
      'https://chatgpt.com/'"

Then log into chatgpt.com in that window, ensure Developer Mode is enabled,
ensure the Workflow connector is available in the composer, and keep the
window visible. The driver navigates the existing chatgpt tab; it does not
open new ones.

Usage:

    python scripts/chatgpt_chat.py ask "your prompt here"
    python scripts/chatgpt_chat.py read              # read last assistant message
    python scripts/chatgpt_chat.py new-chat          # navigate to chatgpt.com/
    python scripts/chatgpt_chat.py status            # is the CDP tab reachable?
    python scripts/chatgpt_chat.py dismiss-dialogs   # click any permission dialog
    python scripts/chatgpt_chat.py tabs              # report tab state

Every ``ask`` appends sent prompt + assistant response to
``output/chatgpt_chat_trace.md``. The notepad ``output/user_sim_session.md``
is shared with the claude.ai driver so the host sees both routes in one log.

Does NOT bypass the UI. Types into the same chat input a human would use.
Reads the same rendered text a human would see. No MCP calls.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import os
import subprocess
import sys
import time
from pathlib import Path

# Windows cp1252 chokes on em-dashes and unicode chatgpt emits. Force utf-8
# the same way scripts/claude_chat.py + scripts/worktree_status.py do.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True,
    )
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True,
    )

_PLAYWRIGHT_MISSING = "ERROR: playwright not installed. Run: pip install playwright"

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

CDP = "http://localhost:9222"
CHATGPT_HOST = "chatgpt.com"
NEW_CHAT_URL = "https://chatgpt.com/"
ROOT = Path(__file__).resolve().parent.parent
TRACE = ROOT / "output" / "chatgpt_chat_trace.md"
FAILURE_DIR = ROOT / "output" / "chatgpt_chat_failures"
NOTEPAD = ROOT / "output" / "user_sim_session.md"

CHROME_BIN = Path(
    os.environ.get(
        "WORKFLOW_CHROME_BIN",
        r"C:\Users\Jonathan\AppData\Local\ms-playwright\chromium-1208\chrome-win64\chrome.exe",
    )
)
CHROME_PROFILE = Path(
    os.environ.get(
        "WORKFLOW_CHROME_PROFILE",
        str(Path.home() / ".claude-ai-profile"),
    )
)

# Selectors — ChatGPT's DOM drifts; try multiple, use the first that works.
# Current shape (mid-2026): contenteditable composer with id "prompt-textarea";
# previously a real <textarea>. Keep both.
INPUT_SELECTORS = [
    'div#prompt-textarea[contenteditable="true"]',
    'textarea#prompt-textarea',
    '[data-testid="prompt-textarea"]',
    'div[contenteditable="true"][data-id]',
    'div.ProseMirror[contenteditable="true"]',
    'textarea',
]
SEND_BUTTON_SELECTORS = [
    'button[data-testid="send-button"]',
    'button[data-testid="composer-send-button"]',
    'button[aria-label*="Send" i]',
    'button[aria-label*="send prompt" i]',
    'button[type="submit"]',
]
STOP_BUTTON_SELECTORS = [
    'button[data-testid="stop-button"]',
    'button[aria-label*="Stop" i]',
    'button[aria-label*="stop generating" i]',
]
ASSISTANT_MSG_SELECTORS = [
    '[data-message-author-role="assistant"]',
    'div[data-testid^="conversation-turn"][data-message-author-role="assistant"]',
    'article[data-testid*="conversation-turn"] [data-message-author-role="assistant"]',
]


def _launch_chrome() -> None:
    """Launch the dedicated Chrome profile with CDP enabled. Non-blocking."""
    if not CHROME_BIN.exists():
        raise RuntimeError(
            f"Chrome binary not found at {CHROME_BIN}. "
            f"Set WORKFLOW_CHROME_BIN env var to override."
        )
    CHROME_PROFILE.mkdir(parents=True, exist_ok=True)
    args = [
        str(CHROME_BIN),
        f"--user-data-dir={CHROME_PROFILE}",
        "--remote-debugging-port=9222",
        "--no-first-run",
        "--disable-blink-features=AutomationControlled",
        NEW_CHAT_URL,
    ]
    creationflags = 0
    if sys.platform == "win32":
        creationflags = 0x00000008 | 0x00000200
    subprocess.Popen(
        args,
        creationflags=creationflags,
        close_fds=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _connect(auto_launch: bool = True, launch_wait_s: int = 20):
    if sync_playwright is None:
        raise RuntimeError(_PLAYWRIGHT_MISSING)
    pw = sync_playwright().start()
    try:
        return pw, pw.chromium.connect_over_cdp(CDP)
    except Exception:
        if not auto_launch:
            pw.stop()
            raise RuntimeError(f"Cannot connect to Chrome CDP at {CDP}.")

    print(f"Chrome CDP not up — launching {CHROME_BIN.name} ...", file=sys.stderr)
    try:
        _launch_chrome()
    except Exception as exc:
        pw.stop()
        raise RuntimeError(f"Auto-launch failed: {exc}") from exc

    deadline = time.monotonic() + launch_wait_s
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        time.sleep(1.0)
        try:
            return pw, pw.chromium.connect_over_cdp(CDP)
        except Exception as exc:
            last_exc = exc
    pw.stop()
    raise RuntimeError(
        f"Chrome launched but CDP still unreachable after {launch_wait_s}s ({last_exc})"
    )


def _find_chatgpt_page(browser):
    for ctx in browser.contexts:
        for p in ctx.pages:
            if CHATGPT_HOST in (getattr(p, "url", "") or ""):
                return p
    return None


def _enumerate_pages(browser):
    pages = []
    for ctx in browser.contexts:
        for p in ctx.pages:
            pages.append(p)
    return pages


def _enforce_chatgpt_tab_hygiene(browser) -> int:
    """Single-chatgpt-tab rule. Closes extra chatgpt.com tabs only.

    Does NOT touch tabs on other hosts (claude.ai, github.com, etc.) — the
    host may legitimately have multiple chatbot routes open simultaneously.
    Tab hygiene is per-route, not global, so the claude_chat.py driver and
    chatgpt_chat.py driver don't fight over each other's tabs.
    """
    chatgpt_pages = [
        p for p in _enumerate_pages(browser)
        if CHATGPT_HOST in (getattr(p, "url", "") or "")
    ]
    if len(chatgpt_pages) <= 1:
        return 0

    def _rank(p) -> int:
        url = (getattr(p, "url", "") or "")
        if CHATGPT_HOST in url and "/c/" in url:
            return 0
        if CHATGPT_HOST in url:
            return 1
        return 2

    pages_sorted = sorted(chatgpt_pages, key=_rank)
    keeper = pages_sorted[0]
    closed_urls = []
    for p in pages_sorted[1:]:
        url = (getattr(p, "url", "") or "(unknown)")
        try:
            p.close()
            closed_urls.append(url)
        except Exception as exc:
            print(
                f"TAB HYGIENE WARN: failed to close chatgpt tab {url}: {exc}",
                file=sys.stderr,
            )
    if closed_urls:
        keeper_url = (getattr(keeper, "url", "") or "(unknown)")
        print(
            f"TAB HYGIENE: closed {len(closed_urls)} extra chatgpt tab(s); "
            f"kept {keeper_url}; closed {closed_urls}",
            file=sys.stderr,
        )
    return len(closed_urls)


def _ensure_chatgpt_page(browser):
    """Find an existing chatgpt.com tab or navigate the first available tab.

    Unlike claude_chat.py we don't repurpose a tab that's on a different
    host — co-existence with the claude driver matters. If no chatgpt tab
    exists and there's no spare tab to navigate, we open one explicitly.
    """
    p = _find_chatgpt_page(browser)
    if p is not None:
        _enforce_chatgpt_tab_hygiene(browser)
        return p
    # No chatgpt tab exists. Try to navigate a blank-ish tab if one exists.
    for ctx in browser.contexts:
        for cand in ctx.pages:
            url = (getattr(cand, "url", "") or "")
            if url in ("", "about:blank") or url.startswith("chrome://newtab"):
                cand.goto(NEW_CHAT_URL, timeout=30000)
                time.sleep(2)
                _enforce_chatgpt_tab_hygiene(browser)
                return cand
    # No blank tab — open a new chatgpt tab in the first existing context.
    for ctx in browser.contexts:
        page = ctx.new_page()
        page.goto(NEW_CHAT_URL, timeout=30000)
        time.sleep(2)
        _enforce_chatgpt_tab_hygiene(browser)
        return page
    raise RuntimeError("No browser contexts available to open chatgpt.com.")


DIALOG_DISMISS_SELECTORS = [
    # ChatGPT permission dialog candidates. Keep narrow — never click
    # arbitrary buttons. Only matches inside dialog-like containers.
    '[role="dialog"] button:has-text("Allow")',
    '[role="dialog"] button:has-text("Confirm")',
    '[role="dialog"] button:has-text("Continue")',
    '[role="dialog"] button:has-text("Use this connector")',
    '[role="dialog"] button:has-text("Enable")',
    '[role="dialog"] button:has-text("Approve")',
    '[role="dialog"] button:has-text("Trust")',
    '[aria-modal="true"] button:has-text("Allow")',
    '[aria-modal="true"] button:has-text("Confirm")',
    '[aria-modal="true"] button:has-text("Continue")',
    '[aria-modal="true"] button:has-text("Use this connector")',
    '[aria-modal="true"] button:has-text("Enable")',
    '[aria-modal="true"] button:has-text("Approve")',
    '[aria-modal="true"] button:has-text("Trust")',
]


def _log_notepad(text: str, outcome: str, tool_name: str = "") -> None:
    """Append one event line to the shared notepad. Best-effort; never raises."""
    try:
        NOTEPAD.parent.mkdir(parents=True, exist_ok=True)
        snippet = (text or "").strip().replace("\n", " ")
        if len(snippet) > 80:
            snippet = snippet[:80]
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        tool = tool_name or "-"
        line = (
            f"## [{stamp}] CHATGPT_CHAT {tool} — "
            f'"{snippet}" outcome: {outcome}\n'
        )
        fd = os.open(
            str(NOTEPAD),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o644,
        )
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except Exception:
        pass


def _dismiss_dialogs(page) -> int:
    """Click any permission/allow dialog ChatGPT has put up.

    Scoped to dialog-like containers — never clicks arbitrary buttons.
    Returns how many dialogs were dismissed. Cheap no-op when no dialog
    exists, so safe to call before every ask and before every response
    wait.
    """
    clicked = 0
    for sel in DIALOG_DISMISS_SELECTORS:
        try:
            loc = page.locator(sel)
            n = loc.count()
        except Exception:
            continue
        for i in range(n):
            try:
                btn = loc.nth(i)
                if not btn.is_visible():
                    continue
                btn_text = ""
                try:
                    btn_text = (btn.inner_text() or "").strip()
                except Exception:
                    pass
                try:
                    btn.click(force=True)
                except Exception:
                    _log_notepad(
                        btn_text or sel, outcome="failed",
                        tool_name="_dismiss_dialogs",
                    )
                    continue
                clicked += 1
                _log_notepad(
                    btn_text or sel, outcome="ok",
                    tool_name="_dismiss_dialogs",
                )
                time.sleep(0.3)
                break
            except Exception:
                continue
        if clicked:
            break
    return clicked


def _first_visible(page, selectors):
    for sel in selectors:
        try:
            loc = page.locator(sel)
            count = loc.count()
        except Exception:
            continue
        for i in range(count):
            try:
                if loc.nth(i).is_visible():
                    return loc.nth(i)
            except Exception:
                continue
    return None


def _type_multiline(page, message: str, *, per_char_delay_ms: int = 5) -> None:
    """Type ``message`` into the focused composer, preserving newlines.

    ChatGPT's composer treats plain Enter as Send. A naive
    ``page.keyboard.type(message)`` for a multi-paragraph brief would
    therefore fire Send the moment it typed the first ``\\n``, truncating
    the message to its first paragraph. This helper splits on newlines and
    emits ``Shift+Enter`` between chunks so the composer stays in compose
    mode until the caller explicitly clicks Send.

    Per-char delay is intentionally short (5ms vs claude_chat.py's 15ms)
    because long briefs are common in dev-partner mode and 15ms × 3,000
    chars = 45 seconds of typing for a single message.
    """
    chunks = message.split("\n")
    for i, chunk in enumerate(chunks):
        if i > 0:
            # Shift+Enter inserts a newline in the composer without firing
            # Send. Works for both contenteditable composers and
            # <textarea> shells.
            page.keyboard.press("Shift+Enter")
        if chunk:
            page.keyboard.type(chunk, delay=per_char_delay_ms)


def _wait_for_send_button_ready(page, *, timeout_s: int = 10):
    """Return a visible & enabled Send button locator, or None on timeout.

    Defensive guard: composer state machines occasionally show the Send
    button before they've accepted typed input. Clicking too early sends
    an empty (or partial) message. We poll until the button reports
    ``aria-disabled`` != "true" and ``disabled`` is not set.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        btn = _first_visible(page, SEND_BUTTON_SELECTORS)
        if btn is not None:
            try:
                aria_disabled = (btn.get_attribute("aria-disabled") or "").lower()
                disabled_attr = btn.get_attribute("disabled")
                if aria_disabled != "true" and disabled_attr is None:
                    return btn
            except Exception:
                return btn
        time.sleep(0.15)
    return _first_visible(page, SEND_BUTTON_SELECTORS)  # final best-effort


def _first_usable_input(page):
    """Visible composer input that's not locked / disabled."""
    for sel in INPUT_SELECTORS:
        try:
            loc = page.locator(sel)
            count = loc.count()
        except Exception:
            continue
        for i in range(count):
            cand = loc.nth(i)
            try:
                if not cand.is_visible():
                    continue
                get_attribute = getattr(cand, "get_attribute", None)
                if callable(get_attribute):
                    aria_disabled = (get_attribute("aria-disabled") or "").lower()
                    if aria_disabled == "true":
                        continue
                    contenteditable = (get_attribute("contenteditable") or "").lower()
                    if contenteditable == "false":
                        continue
                evaluate = getattr(cand, "evaluate", None)
                if callable(evaluate):
                    if evaluate(
                        "el => el.tagName.toLowerCase() === 'textarea' && el.disabled"
                    ):
                        continue
                return cand
            except Exception:
                continue
    return None


def _read_last_assistant_text(page) -> str:
    """Return the inner_text of the most recent assistant message, or ''."""
    best_text = ""
    for sel in ASSISTANT_MSG_SELECTORS:
        try:
            loc = page.locator(sel)
            n = loc.count()
        except Exception:
            continue
        for i in range(n - 1, -1, -1):
            try:
                node = loc.nth(i)
                if not node.is_visible():
                    continue
                text = (node.inner_text() or "").strip()
                if text:
                    return text
            except Exception:
                continue
    return best_text


def _wait_for_response_complete(page, prev_text: str, *, timeout_s: int = 180):
    """Wait for ChatGPT to finish generating a new response.

    The signal we watch:
    - The last assistant message's inner_text has changed from ``prev_text``.
    - The Stop button is gone (response stream finished).
    - Text has been stable for at least ``stable_s`` seconds.

    Returns ``(response_text, timed_out)``.
    """
    deadline = time.monotonic() + timeout_s
    stable_s = 2.5
    last_text = ""
    last_change = time.monotonic()
    while time.monotonic() < deadline:
        # Cheap dismiss check so a mid-stream connector dialog doesn't stall us.
        try:
            _dismiss_dialogs(page)
        except Exception:
            pass
        cur = _read_last_assistant_text(page)
        stop_btn = _first_visible(page, STOP_BUTTON_SELECTORS)
        if cur and cur != prev_text:
            if cur != last_text:
                last_text = cur
                last_change = time.monotonic()
            elif stop_btn is None and (time.monotonic() - last_change) >= stable_s:
                return cur, False
        time.sleep(0.4)
    return last_text or "(no response captured)", True


def _append_trace(direction: str, body: str) -> None:
    try:
        TRACE.parent.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(TRACE, "a", encoding="utf-8") as fh:
            fh.write(f"\n## [{stamp}] {direction}\n\n{body}\n")
    except Exception as exc:
        print(f"WARN: failed to append trace: {exc}", file=sys.stderr)


def _capture_failure_dump(page, reason: str, *, note: str = "") -> str:
    """Write HTML + screenshot + note triple under output/chatgpt_chat_failures/.

    Returns the basename so callers can reference it in error messages.
    """
    try:
        FAILURE_DIR.mkdir(parents=True, exist_ok=True)
        ts = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
        base = f"{ts}_{reason}"
        html_path = FAILURE_DIR / f"{base}.html"
        png_path = FAILURE_DIR / f"{base}.png"
        txt_path = FAILURE_DIR / f"{base}.txt"
        try:
            html_path.write_text(page.content(), encoding="utf-8")
        except Exception:
            pass
        try:
            page.screenshot(path=str(png_path), full_page=True)
        except Exception:
            pass
        if note:
            try:
                txt_path.write_text(note, encoding="utf-8")
            except Exception:
                pass
        return base
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_ask(message: str) -> int:
    pw, browser = _connect()
    try:
        page = _ensure_chatgpt_page(browser)
        page.bring_to_front()
        _dismiss_dialogs(page)
        prev = _read_last_assistant_text(page)

        inp = _first_usable_input(page)
        if inp is None:
            dump = _capture_failure_dump(
                page, "input_not_found",
                note=(
                    f"prev_text_len={len(prev)}; "
                    f"message_preview={message[:80]!r}"
                ),
            )
            print(
                "ERROR: could not find chat input on chatgpt.com. "
                "Is the page loaded? Diagnostic dump: "
                f"output/chatgpt_chat_failures/{dump}." "{html,png,txt}",
                file=sys.stderr,
            )
            return 3

        inp.click()
        # Clear any stale text so we don't interleave the prior compose-buffer.
        try:
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
        except Exception:
            pass
        try:
            current = (inp.inner_text() or "").strip()
        except Exception:
            current = ""
        if current:
            try:
                inp.evaluate(
                    "(el) => { "
                    "if ('value' in el) { el.value = ''; } "
                    "else { el.textContent = ''; } "
                    "el.dispatchEvent(new Event('input', {bubbles: true})); "
                    "}"
                )
            except Exception:
                pass
        # CRITICAL: ChatGPT's composer sends on plain Enter. A naive
        # `keyboard.type(message)` for a multi-paragraph brief would fire
        # Send on the first paragraph break, truncating the message. Split
        # on newlines and emit Shift+Enter between chunks so the composer
        # stays in compose mode until we explicitly click Send.
        _type_multiline(page, message)
        # Defensive: wait briefly for the composer to register the typed
        # text and for the send button to become enabled before clicking,
        # so we don't fire on a half-typed message.
        send = _wait_for_send_button_ready(page, timeout_s=10)
        if send is not None:
            send.click()
        else:
            # Last-resort fallback: use the platform's "send" keystroke.
            # ChatGPT respects Ctrl/Cmd+Enter on long messages even when
            # the visible button isn't found.
            modifier = "Meta" if sys.platform == "darwin" else "Control"
            page.keyboard.press(f"{modifier}+Enter")

        _append_trace("USER -> CHATGPT", message)
        response, timed_out = _wait_for_response_complete(page, prev)

        if timed_out:
            note = (
                f"prev_len={len(prev)}; response_len={len(response)}; "
                f"message_preview={message[:80]!r}"
            )
            dump = _capture_failure_dump(page, "response_timeout", note=note)
            _append_trace(
                "CHATGPT -> USER",
                f"(TIMEOUT after 180s; partial response below; dump={dump})\n{response}",
            )
            print(response or "(no response captured)")
            print(
                f"WARN: response did not settle within 180s. "
                f"Diagnostic dump: output/chatgpt_chat_failures/{dump}.{{html,png,txt}}",
                file=sys.stderr,
            )
            return 5

        _append_trace("CHATGPT -> USER", response)
        print(response or "(no response captured)")
        return 0
    finally:
        browser.close()
        pw.stop()


def cmd_read() -> int:
    pw, browser = _connect()
    try:
        page = _ensure_chatgpt_page(browser)
        text = _read_last_assistant_text(page)
        print(text or "(no assistant message visible)")
        return 0
    finally:
        browser.close()
        pw.stop()


def cmd_dismiss_dialogs() -> int:
    pw, browser = _connect()
    try:
        page = _ensure_chatgpt_page(browser)
        n = _dismiss_dialogs(page)
        print(f"dismissed {n} dialog(s)")
        return 0
    finally:
        browser.close()
        pw.stop()


def cmd_new_chat() -> int:
    pw, browser = _connect()
    try:
        page = _ensure_chatgpt_page(browser)
        page.goto(NEW_CHAT_URL, timeout=30000)
        time.sleep(2)
        _enforce_chatgpt_tab_hygiene(browser)
        print("new chatgpt chat ready")
        return 0
    finally:
        browser.close()
        pw.stop()


def cmd_status() -> int:
    try:
        pw, browser = _connect(auto_launch=False)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 4
    try:
        _enforce_chatgpt_tab_hygiene(browser)
        page = _find_chatgpt_page(browser)
        if page is None:
            print("CDP reachable; no chatgpt.com tab found.")
            return 1
        print(f"OK: chatgpt.com tab at {page.url}")
        return 0
    finally:
        browser.close()
        pw.stop()


def cmd_tabs() -> int:
    """Report open-tab count + URLs. Enforces per-chatgpt tab hygiene only."""
    try:
        pw, browser = _connect(auto_launch=False)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 4
    try:
        pages = _enumerate_pages(browser)
        urls_before = [(getattr(p, "url", "") or "(unknown)") for p in pages]
        closed = _enforce_chatgpt_tab_hygiene(browser)
        pages_after = _enumerate_pages(browser)
        urls_after = [(getattr(p, "url", "") or "(unknown)") for p in pages_after]
        chatgpt_after = [u for u in urls_after if CHATGPT_HOST in u]
        print(
            f"TAB HYGIENE: {len(pages_after)} total tab(s); "
            f"chatgpt={len(chatgpt_after)}; urls={urls_after}"
        )
        if closed:
            print(
                f"  (healed {closed} chatgpt tab(s); before={urls_before})"
            )
        return 0
    finally:
        browser.close()
        pw.stop()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    sub = p.add_subparsers(dest="cmd", required=True)
    ask = sub.add_parser("ask")
    ask.add_argument("message")
    sub.add_parser("read")
    sub.add_parser("new-chat")
    sub.add_parser("status")
    sub.add_parser("dismiss-dialogs")
    sub.add_parser("tabs")
    ns = p.parse_args()

    if ns.cmd == "ask":
        return cmd_ask(ns.message)
    if ns.cmd == "read":
        return cmd_read()
    if ns.cmd == "new-chat":
        return cmd_new_chat()
    if ns.cmd == "status":
        return cmd_status()
    if ns.cmd == "dismiss-dialogs":
        return cmd_dismiss_dialogs()
    if ns.cmd == "tabs":
        return cmd_tabs()
    return 1


if __name__ == "__main__":
    sys.exit(main())
