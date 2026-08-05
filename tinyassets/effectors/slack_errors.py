"""Slack errors that cannot carry a credential.

This module exists because the same two mistakes were made three times, in
three files, by the same author in one sitting — and a cross-family review
reproduced a live token from each:

* ``raise ... from exc``. An HTTP library's exception message routinely quotes
  the request, including the ``Authorization: Bearer …`` header. Chaining keeps
  that cause attached, so any formatted traceback or ``exc_info=True`` log
  writes the credential out. The fix is ``from None`` — chaining is a leak
  here, not a courtesy.
* Interpolating Slack's ``error`` field. It is upstream text, and a response of
  ``{"ok": false, "error": "invalid xoxb-…"}`` puts the token straight into our
  own message from the other direction.

Three one-off patches would have been three chances to miss the fourth. These
are the shared primitives instead.
"""

from __future__ import annotations

import re
import traceback

#: Slack error codes are lowercase snake_case identifiers. Anything else in that
#: field is not a code we recognise, and echoing it verbatim is how upstream
#: text — including a token an error message quoted back — reaches our logs.
_ERROR_CODE = re.compile(r"\A[a-z][a-z0-9_]{0,63}\Z")


def safe_error_code(value: object, *, default: str = "") -> str:
    """Pass through a real Slack error code; refuse anything else.

    An allow-list, not a scrub. A denylist would have to anticipate every shape
    a secret can take; the set of valid Slack codes is small and well-shaped, so
    matching what we *accept* is both simpler and tighter.
    """
    if isinstance(value, str) and _ERROR_CODE.match(value):
        return value
    return default


def contains_secret(exc: BaseException, *secrets: str) -> bool:
    """Whether any of ``secrets`` appears anywhere in the exception chain.

    Walks ``__cause__`` and ``__context__`` explicitly rather than trusting
    ``traceback.format_exception``. That formatter honours
    ``__suppress_context__``, which ``raise ... from None`` sets — so a token
    sitting in ``__context__`` renders as absent and the check would call a
    dirty exception clean. It is invisible to the *default* formatter, which is
    not the same as unreachable: ``repr(exc.__context__)`` still has it, and so
    does any custom log handler that walks the chain.

    Conservative by construction: it errs toward "there is a secret in here".
    """
    real = [s for s in secrets if isinstance(s, str) and s]
    if not real:
        return False

    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        rendered = "".join(
            traceback.format_exception_only(type(current), current)
        ) + "".join(traceback.format_tb(current.__traceback__))
        if any(secret in rendered for secret in real):
            return True
        # Cause first, then context — following both, since either can hold it.
        nxt = current.__cause__ or current.__context__
        current = nxt
    return False


def scrubbed(
    exc: BaseException,
    *secrets: str,
    fallback: str,
    error_type: type[Exception],
) -> Exception:
    """The same error, or ``fallback`` if any secret is anywhere in it.

    Not a general secret scrubber — that would be a denylist and would not work.
    This checks for specific strings the caller is holding, so a diagnostic is
    either verified clean or dropped entirely. There is no third outcome where a
    token slips through because a pattern did not match.
    """
    if contains_secret(exc, *secrets):
        return error_type(fallback)
    return error_type(str(exc))
