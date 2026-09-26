"""Redact credential material from a log stream on its way off the box.

Filter, stdin to stdout, one line at a time::

    journalctl CONTAINER_NAME=tinyassets-logs --since '3 days ago' \\
        | python3 scripts/redact_log_bundle.py > bundle/container-logs.log

Called by deploy/backup.sh for the nightly log tier, which ships to GitHub
release assets in a private repo. That destination is off the droplet, so
anything this filter misses leaves the trust boundary.

Relationship to the in-process redaction
----------------------------------------
Two definitions already exist for "what a secret looks like" in this repo:
``tinyassets.workspace_git.scrub_text`` (exact registered secrets plus generic
patterns) and ``tinyassets.providers.codex_provider._SECRET_SHAPES`` (shapes in
provider output). This module is deliberately a SUPERSET of their generic
patterns rather than a third opinion, and
``tests/test_redact_log_bundle.py::test_covers_the_canonical_secret_shapes``
imports both and fails if any input they redact survives this filter.

Superset, not equality, is the right direction for a bundle that leaves the box:
being stricter here can only cost readability, while being looser leaks. The
extra shapes are ones the in-process redactors do not need because they never
see a bare token on a line of their own -- Slack ``xoxb-``/``xapp-`` tokens,
Cloudflare tunnel tokens, and ``KEY=value`` environment echoes.

What this deliberately does NOT catch
------------------------------------
Stated because a filter whose limits are unwritten gets trusted past them. A
cross-family review reproduced these; they are accepted, not overlooked:

- **An unlabelled high-entropy blob.** A bare base64 or hex string with no
  adjacent key name is indistinguishable from a content hash, a request id, a
  digest or a model id, all of which appear constantly in this daemon's output.
  A generic "long token" rule was already tried once in
  ``codex_provider._SECRET_SHAPES`` and removed for exactly this reason.
- **A secret split across two journal records.** This is a line filter by
  construction, and the journal's unit of storage is the record.
- **An UNQUOTED value containing a structural delimiter.** ``password=a]b}c``
  redacts ``a`` and leaves ``]b}c``, because an unquoted field ends at a
  delimiter and ``}``/``]`` overwhelmingly close a structure rather than belong to
  a value. Consuming through them is the opposite failure: it eats the sibling
  fields on every ordinary ``k=v,k=v`` line. Quote the value and it is redacted
  whole; a credential logged bare enough to hit this needs the upstream fix.

``MAX_LINE_CHARS`` is NOT in this list: redaction runs over the whole line before
truncation, so a 10,000-character labelled value is redacted and then the
remainder is cut. An earlier version of this docstring claimed otherwise.

The mitigation for all three is upstream: the daemon should not log credential
material, and ``providers/diagnostics.py`` / ``workspace_git.scrub_text`` are
where that is enforced. This filter is the second line, not the first.

Stdlib only -- this runs from the host-uptime runtime closure, which ships no
third-party packages and not the ``tinyassets`` package.
"""

from __future__ import annotations

import re
import sys
from typing import IO

REDACTED = "[redacted]"

# Ordered: the URL-userinfo and header rules run before the bare-token rules so
# a match consumes the whole credential-bearing span rather than leaving the
# scheme or header name glued to a redaction marker.
PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # userinfo in an https URL: https://user:token@host/... (workspace_git)
    (re.compile(r"https://[^/@\s]+@"), f"https://{REDACTED}@"),
    # an Authorization header value, however it is spelled (workspace_git)
    (re.compile(r"(?i)(authorization\s*:\s*)([^\r\n]+)"), r"\1" + REDACTED),
    # `Bearer <token>` outside a header (codex_provider _SECRET_SHAPES)
    (re.compile(r"(?i)bearer\s+\S+"), REDACTED),
    # NOTE: labelled values (`api_key=…`, `"password": "…"`) are NOT handled here.
    # A single pattern cannot get them right, which two review rounds demonstrated
    # in both directions -- see `_redact_labelled_values` below, which runs first.
    # OpenAI/Anthropic/OpenRouter-style keys: sk-, sk-ant-, sk-or-v1-.
    # No leading `\b`: the canonical `_SECRET_SHAPES` has none, and `prefix_sk-…`
    # kept the whole key alive because `_` is a word character so `\b` never
    # matched (same review, §4).
    (re.compile(r"sk-[A-Za-z0-9_-]{8,}"), REDACTED),
    # JWT or any base64url JSON object header (codex_provider _SECRET_SHAPES)
    (re.compile(r"\beyJ[A-Za-z0-9_.-]{10,}"), REDACTED),
    # GitHub (workspace_git) and the rest of the token estate
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}"), REDACTED),
    (re.compile(r"\bgho_[A-Za-z0-9]{20,}"), REDACTED),
    (re.compile(r"\bghs_[A-Za-z0-9]{20,}"), REDACTED),
    (re.compile(r"\bghu_[A-Za-z0-9]{20,}"), REDACTED),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), REDACTED),
    # Slack bot/user/app tokens. The daemon's Slack surface logs these paths.
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), REDACTED),
    (re.compile(r"\bxapp-[A-Za-z0-9-]{10,}"), REDACTED),
    # AWS / DO Spaces access key ids, and anything asserting an AWS secret.
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), REDACTED),
)

# ---------------------------------------------------------------------------
# Labelled values, scanned rather than pattern-matched
# ---------------------------------------------------------------------------
#
# `api_key=…`, `"password": "…"`, `\"token\": \"…\"`, `--password …`. Two review
# rounds showed a single regex cannot do this, failing in BOTH directions:
#
#   round 1: stopping the value at `,;&` left `password=[redacted],beta` --
#            redacted-looking, still disclosing.
#   round 2: widening the terminator to whitespace then left
#            `"password": "[redacted] beta gamma"` for a quoted passphrase
#            containing spaces, and -- worse -- adding `auth` to the key list with
#            an optional separator destroyed ordinary evidence:
#            `authentication succeeded` became `authentication [redacted]`.
#
# The reason is that where a value ENDS depends on how it STARTED, which is state
# a flat pattern does not carry. So: find the label, look at the first character
# of the value, and end where that opening implies.
#
#   * opened with a quote (`"`, `'`, or an escaped `\"`)  -> ends at the matching
#     closing quote. Spaces, commas and brackets inside are part of the value.
#   * opened bare -> ends at whitespace or a structural delimiter. An unquoted
#     value CANNOT contain those, so stopping there is not partial disclosure --
#     `password=alpha,elapsed=17` really is the field `alpha` followed by another
#     field, and eating `elapsed=17` would destroy a diagnostic.
#
# The key must be followed by a real separator (`:` or `=`), except for the argv
# form, which requires an explicit `--flag`. That is what keeps
# `authentication succeeded` intact: no separator, no `--`, no match.
# The bounded prefix and the lookbehind are a PERFORMANCE requirement, not style.
# With an unbounded leading `[A-Za-z0-9_.-]*` and no anchor, `finditer` attempts a
# match at every offset of a long identifier-ish run, each attempt consuming to the
# end and backtracking in search of `token`/`password`/... That is quadratic: a
# 1 KiB line -- entirely ordinary once Vector wraps daemon output in JSON -- took
# 27.85 ms, against 0.028 ms for a short one. At 50,000 records that is ~23 minutes
# for ONE source, which would blow the per-source timeout every night.
#
# The lookbehind means a match can only START where a key could actually start, so
# a 1 KiB run of key characters offers one candidate rather than a thousand; the
# {0,40} bound caps the work at each candidate. Measured after: 0.10 ms on the same
# 1 KiB line, ~280x faster.
_SECRET_KEY = (
    r"[A-Za-z0-9_.-]{0,40}?"
    r"(?:token|secret|api[_-]?key|password|passwd|credential|private[_-]?key)"
    r"[A-Za-z0-9_.-]{0,40}"
)
# The anchor goes on the FIELD form only. Putting it inside _SECRET_KEY broke the
# argv form, because `--password` presents `-` to the lookbehind and `-` is a key
# character; `--` is its own anchor and needs no help.
_KEY_START = r"(?<![A-Za-z0-9_.-])"
# Group 1 is everything up to and including the value's opening quote, if any;
# group 2 is that quote (empty when the value is bare).
_LABELLED = re.compile(
    r"(?i)("
    # argv form: a whitespace separator is only allowed after an explicit --flag.
    r"--" + _SECRET_KEY + r"\s+"
    r"|"
    # field form: the key, optionally quoted, then a real `:` or `=`.
    + _KEY_START + r"(?:\\?[\"'])?" + _SECRET_KEY + r"(?:\\?[\"'])?\s*[:=]\s*"
    r")(\\?[\"']|)"                 # the value's opening quote, or empty
)
# Bare values end here. `)` included because a value in a parenthesised aside is
# bounded by it; `\` excluded so an escaped quote ends the span rather than being
# consumed as content.
_BARE_VALUE_END = re.compile(r"[\s,;&}\])\"'\\]")


def _redact_labelled_values(line: str) -> str:
    """Replace the value of every credential-named field, whole."""
    out: list[str] = []
    pos = 0
    for match in _LABELLED.finditer(line):
        if match.start() < pos:  # already inside a replaced span
            continue
        label, quote = match.group(1), match.group(2)
        value_start = match.end()
        if value_start >= len(line):
            continue
        if quote:
            # Ends at the same quote form it opened with. `\"` closes `\"`.
            closer = line.find(quote, value_start)
            if closer == -1:
                # Unterminated: treat the rest of the line as the value rather
                # than leaving it exposed. Truncated JSON is the likely cause.
                value_end = len(line)
            else:
                value_end = closer
        else:
            terminator = _BARE_VALUE_END.search(line, value_start)
            value_end = terminator.start() if terminator else len(line)
        if value_end <= value_start:
            continue  # a label with an empty value is not a leak
        out.append(line[pos : match.start()])
        out.append(label)
        out.append(quote)
        out.append(REDACTED)
        pos = value_end
    out.append(line[pos:])
    return "".join(out)


# Docker's journald driver adds no size guard, and a single line can be a whole
# serialized payload. Truncating past this bound keeps one pathological line
# from dominating a bundle whose point is breadth of history. Redaction runs
# BEFORE truncation, so a long value is redacted rather than merely cut off.
MAX_LINE_CHARS = 8192
_TRUNCATION_MARKER = " ...[truncated]"


def redact_line(line: str) -> str:
    """Return ``line`` with every credential shape replaced.

    Idempotent: the replacement marker matches none of the patterns, so
    re-running this over its own output changes nothing.
    """
    line = _redact_labelled_values(line)
    for pattern, replacement in PATTERNS:
        line = pattern.sub(replacement, line)
    if len(line) > MAX_LINE_CHARS:
        line = line[:MAX_LINE_CHARS] + _TRUNCATION_MARKER
    return line


def redact_stream(source: IO[str], sink: IO[str]) -> int:
    """Filter ``source`` into ``sink``. Returns the number of lines written."""
    written = 0
    for raw in source:
        stripped = raw.rstrip("\n").rstrip("\r")
        sink.write(redact_line(stripped) + "\n")
        written += 1
    return written


def main() -> int:
    # errors="replace" on both ends: journald can hand us a line that is not
    # valid UTF-8, and a UnicodeDecodeError here would abort the log tier and
    # take the bundle with it. A mangled character costs one glyph; a crash
    # costs the evidence.
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    redact_stream(sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
