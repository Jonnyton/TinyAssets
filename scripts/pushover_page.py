"""Pushover paging for P0 uptime outages.

Navigator 2026-04-22 §c fix for the silent-delivery class: today's 18h blackout
proved that writing alarms to a repo log + GH issue was insufficient — host
learned ~18h after the canary went red. Pushover adds an out-of-band push
channel to the host's phone.

Scope
-----
- Fires on threshold-crossed P0 issue open (2+ consecutive reds).
- Re-pages at 1h / 4h / 24h while the incident remains open with no host
  comment (escalation ladder, navigator §c P1).
- Does NOT solve SMS/Twilio — Pushover app push only.

Design
------
The GH issue IS the durable state. Escalation decisions are computed from
the issue's comments: we scan for our own "[PAGED" markers and compare the
newest marker's timestamp against ``now`` and the escalation table. A host
comment between pages resets the ladder (host acknowledged).

Stdlib-only. The workflow calls us with the issue number + comments JSON
piped in, plus secrets as env. Testable without GH API.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterable

PUSHOVER_API = "https://api.pushover.net/1/messages.json"

# Escalation ladder — seconds since the last PAGED marker at which we re-page.
# 1h / 4h / 24h per navigator §c.
ESCALATION_LADDER_S: tuple[int, ...] = (3600, 4 * 3600, 24 * 3600)

# Priority-2 (emergency) params — per Pushover API, priority=2 REQUIRES
# retry + expire or the API rejects the POST. These are applied to every
# P0 page fired by this module. Not for test-fire workflows (pushover-
# test.yml keeps priority=1 so a validation page doesn't wake the host at
# 3am).
#
#   retry  — seconds between Pushover's re-notify attempts until the host
#            acknowledges. Minimum allowed by the API is 30; we use 60 to
#            balance persistence vs. phone-side noise.
#   expire — seconds the retry loop keeps running before Pushover gives
#            up. Maximum allowed by the API is 10800. We use 3600 (1h) —
#            after that window, our own ESCALATION_LADDER_S takes over
#            with a fresh priority=2 page at the 4h rung, then 24h.
P0_RETRY_S = 60
P0_EXPIRE_S = 3600

# Marker prefix we embed in our own issue comments so we can identify them
# on the next tick. Kept machine-readable so `_extract_paged_markers` can
# parse without HTML/markdown fragility.
PAGED_MARKER_PREFIX = "[PAGED"


def _parse_iso(ts: str) -> _dt.datetime | None:
    try:
        # GitHub returns "2026-04-22T01:12:09Z"; Python 3.11 fromisoformat
        # handles a trailing Z since 3.11, but guard for older syntax too.
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return _dt.datetime.fromisoformat(ts)
    except ValueError:
        return None


def _extract_paged_markers(comments: Iterable[dict]) -> list[_dt.datetime]:
    """Return timestamps of our prior PAGED comments, sorted ascending.

    A "paged" comment is one whose body begins with ``[PAGED`` — we ignore
    author because GH API surfaces bot comments same as human comments.
    """
    out: list[_dt.datetime] = []
    for c in comments:
        body = (c.get("body") or "").lstrip()
        if not body.startswith(PAGED_MARKER_PREFIX):
            continue
        ts = _parse_iso(c.get("created_at") or "")
        if ts is not None:
            out.append(ts)
    out.sort()
    return out


def _host_has_commented_since(
    comments: Iterable[dict], since: _dt.datetime, bot_logins: set[str] | None = None,
) -> bool:
    """True if a non-bot comment exists after ``since`` — host ack signal."""
    bots = bot_logins or {"github-actions[bot]", "tinyassets-daemon[bot]"}
    for c in comments:
        if (c.get("user") or {}).get("login") in bots:
            continue
        body = (c.get("body") or "").lstrip()
        if body.startswith(PAGED_MARKER_PREFIX):
            continue  # our own markers, even if authored by a PAT
        ts = _parse_iso(c.get("created_at") or "")
        if ts is not None and ts > since:
            return True
    return False


def should_page(
    comments: list[dict],
    now: _dt.datetime,
    is_first_alarm: bool,
) -> tuple[bool, str]:
    """Decide whether to fire a Pushover page on this tick.

    Returns (should_page, reason). The reason is embedded in the page and
    also returned for log / GH summary output.

    Rules:
      - ``is_first_alarm`` (threshold just crossed, issue just opened): PAGE.
      - Else: find prior PAGED markers on the issue. If none, PAGE ("catch-up"
        — this should not happen in normal flow but keeps us safe).
      - Else: find most recent marker. If host commented after it, do NOT
        page (host ack). Otherwise, compare elapsed vs the next unclimbed
        rung of the escalation ladder. Page if elapsed >= next rung.
    """
    if is_first_alarm:
        return True, "threshold_crossed"

    markers = _extract_paged_markers(comments)
    if not markers:
        # Open issue but no prior page — treat as first alarm catch-up.
        return True, "catchup_missing_marker"

    latest = markers[-1]
    if _host_has_commented_since(comments, latest):
        # Host acknowledged; reset the ladder. No re-page until threshold
        # crosses again or we've climbed past the ladder for a fresh cycle.
        return False, "host_acknowledged"

    elapsed_s = (now - latest).total_seconds()
    # Which rungs have we ALREADY climbed? Count prior PAGED markers beyond
    # the first (the first is threshold-cross itself). If we've emitted N
    # markers total, we've already completed N-1 rungs of the ladder plus
    # the initial page.
    rungs_climbed = max(0, len(markers) - 1)
    if rungs_climbed >= len(ESCALATION_LADDER_S):
        # Already at 24h rung; don't spam past that, only re-page every 24h.
        next_s = ESCALATION_LADDER_S[-1]
    else:
        next_s = ESCALATION_LADDER_S[rungs_climbed]

    if elapsed_s >= next_s:
        return True, f"escalation_{int(next_s)}s"
    return False, f"within_window_{int(next_s - elapsed_s)}s_to_next"


def send_pushover(
    title: str,
    message: str,
    url: str | None = None,
    url_title: str | None = None,
    priority: int = 1,
    *,
    retry: int | None = None,
    expire: int | None = None,
    sound: str | None = None,
    user_key: str | None = None,
    app_token: str | None = None,
    _opener=urllib.request.urlopen,
) -> tuple[bool, str]:
    """POST to Pushover. Returns (ok, body_or_error).

    priority: -2..2.
      1 = high (bypass quiet hours, no ack required).
      2 = emergency — forces sound even on silent mode, re-notifies until
          the host acknowledges. REQUIRES retry + expire or the API rejects
          the POST.

    P0 pages fired by ``main()`` use priority=2 so a real outage wakes the
    host at 3am. Test-fire workflows (``.github/workflows/pushover-test.yml``)
    intentionally stay at priority=1 — a validation page shouldn't wake
    the host.

    When priority=2, this function requires retry + expire either via the
    named args or by the caller falling back to the module constants
    ``P0_RETRY_S`` / ``P0_EXPIRE_S``. Per Pushover API: retry minimum 30s
    (we default 60); expire maximum 10800s (we default 3600 — after that
    the ESCALATION_LADDER_S fires a fresh priority=2 page anyway).
    """
    user_key = user_key or os.environ.get("PUSHOVER_USER_KEY")
    app_token = app_token or os.environ.get("PUSHOVER_APP_TOKEN")
    if not user_key or not app_token:
        return False, "missing PUSHOVER_USER_KEY or PUSHOVER_APP_TOKEN"

    form: dict[str, str] = {
        "token": app_token,
        "user": user_key,
        "title": title[:250],
        "message": message[:1024],
        "priority": str(priority),
    }
    if priority == 2:
        if retry is None or expire is None:
            return False, (
                "priority=2 requires retry + expire (Pushover API enforces); "
                "pass retry=P0_RETRY_S, expire=P0_EXPIRE_S or explicit values"
            )
        form["retry"] = str(retry)
        form["expire"] = str(expire)
    if sound:
        form["sound"] = sound
    if url:
        form["url"] = url
        if url_title:
            form["url_title"] = url_title[:100]

    data = urllib.parse.urlencode(form).encode("ascii")
    req = urllib.request.Request(PUSHOVER_API, data=data, method="POST")
    try:
        with _opener(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", "replace")
        return True, body
    except urllib.error.HTTPError as e:
        return False, f"HTTPError {e.code}: {e.read().decode('utf-8', 'replace')}"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return False, f"network error: {e}"


def _load_json_or_exit(path: str | None, env_name: str) -> object:
    """Load JSON from --path or the named env var. Fail fast on malformed."""
    if path:
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)
    raw = os.environ.get(env_name)
    if raw is None:
        return []
    return json.loads(raw)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Pushover page for P0 outages.")
    ap.add_argument("--issue-number", required=True, type=int,
                    help="GH issue number (for the page message).")
    ap.add_argument("--run-url", required=True,
                    help="Link to the failing workflow run.")
    ap.add_argument("--probe-url", required=True,
                    help="URL being probed (e.g. https://tinyassets.io/mcp).")
    ap.add_argument("--probe-exit", required=True,
                    help="Probe exit code.")
    ap.add_argument("--kind", default="PUBLIC_MCP_OUTAGE",
                    help="Alarm kind tag (default PUBLIC_MCP_OUTAGE).")
    ap.add_argument("--first-alarm", action="store_true",
                    help="Set when the issue was just opened (threshold crossed).")
    ap.add_argument("--comments-json",
                    help="Path to JSON array of issue comments (from gh api).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Decide page/no-page + print reason; do not POST.")
    args = ap.parse_args(argv)

    comments = _load_json_or_exit(args.comments_json, "COMMENTS_JSON")
    if not isinstance(comments, list):
        print(f"[pushover-page] expected JSON array for comments; got {type(comments).__name__}",
              file=sys.stderr)
        return 2

    now = _dt.datetime.now(tz=_dt.timezone.utc)
    fire, reason = should_page(comments, now, is_first_alarm=args.first_alarm)
    print(f"[pushover-page] decision={'PAGE' if fire else 'SKIP'} reason={reason} "
          f"issue=#{args.issue_number} markers_seen={len(_extract_paged_markers(comments))}")

    if not fire:
        return 0

    title = f"P0 TinyAssets outage — {args.kind}"
    message = (
        f"{args.probe_url} red (exit {args.probe_exit}).\n"
        f"Reason: {reason}.\n"
        f"Issue #{args.issue_number} open.\n"
        f"Time: {now.isoformat(timespec='seconds')}"
    )

    if args.dry_run:
        print(f"[pushover-page] DRY-RUN title={title!r} message={message!r}")
        return 0

    # Priority=2 (emergency): forces sound through silent mode + retries
    # until the host acknowledges. Required for real P0 — the host needs
    # to wake at 3am for a true outage, not sleep through it.
    ok, body = send_pushover(
        title, message,
        url=args.run_url, url_title="Failing run",
        priority=2, retry=P0_RETRY_S, expire=P0_EXPIRE_S,
        sound="vibrate",
    )
    if ok:
        print(f"[pushover-page] POST ok body={body}")
        # Emit the marker line the workflow posts back as an issue comment.
        marker_ts = now.isoformat(timespec="seconds")
        print(f"MARKER::{PAGED_MARKER_PREFIX} {marker_ts} {reason}]")
        return 0
    print(f"[pushover-page] POST failed: {body}", file=sys.stderr)
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
