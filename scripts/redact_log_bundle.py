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
- **A value long enough to cross ``MAX_LINE_CHARS``.** Redaction runs BEFORE
  truncation, so the visible part is redacted; but a single line carrying a
  secret past the bound is truncated rather than inspected further.

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
    # A labelled value: `key=v`, `key: v`, `"key": "v"`, `\"key\": \"v\"`,
    # `--key v`. Everything after the label up to a STRUCTURAL delimiter goes.
    #
    # Rewritten 2026-09-26 after a cross-family review reproduced four leaks in
    # the first version (Codex, output/codex-log-durability-review.md §4). The
    # important one was on the real collection path: Vector's console sink is
    # `codec: json` (deploy/vector.yaml), so a daemon line reaches the journal as
    # an ESCAPED JSON string -- `{"log": "{\"api_key\": \"secret\"}"}` -- and a
    # pattern expecting a bare `"` never fires. Hence `(?:\\?["'])?` on both
    # sides: it matches a plain quote, a backslash-escaped quote, or neither.
    #
    # The value terminator is the other half. The first version stopped at
    # `,;&"'`, which turned `password=alpha,beta;gamma` into
    # `password=[redacted],beta;gamma` -- a PARTIAL disclosure that still looked
    # redacted. The set below stops only at whitespace, a closing brace/bracket,
    # or an escaped quote, so a comma-bearing value is consumed whole. Structural
    # JSON separators (`,` followed by a quoted key) still end it because the
    # escaped-quote alternative matches first.
    (
        re.compile(
            r"""(?ix)
            ( (?:--)?                              # optional argv flag prefix
              (?:\\?["'])?                         # opening quote, escaped or not
              [A-Za-z0-9_.-]*
              (?: token|secret|api[_-]?key|password|passwd
                | credential|private[_-]?key|auth|bearer )
              [A-Za-z0-9_.-]*
              (?:\\?["'])?                         # closing quote of the KEY
              \s* [:=]? \s*                        # separator, or just space (argv)
              (?:\\?["'])?                         # opening quote of the VALUE
            )
            (?! \s )                               # a label with no value is not a leak
            (?: \\. | [^\s"'\\},\]] | ,(?!\s*\\?["']) )+
            """
        ),
        r"\1" + REDACTED,
    ),
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

# Docker's journald driver adds no size guard, and a single line can be a whole
# serialized payload. Truncating past this bound keeps one pathological line
# from dominating a bundle whose point is breadth of history.
MAX_LINE_CHARS = 8192
_TRUNCATION_MARKER = " ...[truncated]"


def redact_line(line: str) -> str:
    """Return ``line`` with every credential shape replaced.

    Idempotent: the replacement marker matches none of the patterns, so
    re-running this over its own output changes nothing.
    """
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
