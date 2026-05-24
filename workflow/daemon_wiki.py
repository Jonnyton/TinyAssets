"""Host-local learning wiki for soul-bearing daemons.

The daemon wiki follows the LLM-wiki pattern: immutable raw sources,
maintained markdown synthesis pages, and a schema file that tells future
daemon runs how to use the wiki. It is deliberately host-local; callers should
not publish wiki contents or absolute paths to public platform surfaces.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
VALID_SIGNAL_SOURCES = {"node", "gate", "manual"}
VALID_SIGNAL_OUTCOMES = {"passed", "failed", "blocked", "cancelled", "unknown"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_slug(value: str, *, fallback: str = "item") -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-._").lower()
    return slug[:96] or fallback


def daemon_wiki_root(base_path: str | Path, daemon_id: str) -> Path:
    """Return the host-local wiki root for a daemon identity."""
    return Path(base_path) / "daemon_wikis" / _safe_slug(daemon_id, fallback="daemon")


def _signal_filename(
    *,
    source_kind: str,
    source_id: str,
    outcome: str,
    recorded_at: datetime,
) -> str:
    stamp = recorded_at.strftime("%Y%m%dT%H%M%SZ")
    source = _safe_slug(f"{source_kind}-{source_id}", fallback=source_kind)
    return f"{stamp}-{source}-{_safe_slug(outcome)}.md"


def _append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)


def _write_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8", newline="\n")


def _schema_text(
    *,
    daemon_id: str,
    display_name: str,
    soul_hash: str,
    today: str,
) -> str:
    return f"""---
title: Daemon Wiki Schema
type: schema
updated: {today}
daemon_id: {daemon_id}
soul_hash: {soul_hash}
schema_version: {SCHEMA_VERSION}
---

# Daemon Wiki Schema

This wiki is private to the host machine and belongs to the soul-bearing daemon
`{display_name}`.

## Purpose

Use this wiki to become a better version of the daemon described by the soul
file. "Better" means more aligned with the soul's spirit, better calibrated by
evidence, and more reliable across nodes and gates.

## Layers

- `raw/signals/`: immutable records from passed, failed, blocked, or cancelled
  nodes and gates. Do not edit these files after recording; the memory governor
  may compact older raw signals after they have been summarized.
- `pages/`: maintained synthesis pages. Update these when new signals change
  what the daemon has learned.
- `pages/brain/review.md`: curated review of promoted mini-brain entries.
- `pages/brain/blocked-patterns.md`: loop-discipline patterns that must be
  read before claiming new work, especially rejected PR shapes and gate verdict
  feedback.
- `decision_log/`: durable records of work considered, chosen, or declined.
- `soul_versions/`: immutable soul amendments and forks.
- `claim_proofs/`: domain claims, credentials, attestations, and tests.
- `status/`: machine-readable memory status snapshots.
- `drafts/soul-evolution/`: proposed soul edits. Do not rewrite the soul file
  directly from a failure. Prefer small proposals that preserve the original
  spirit.
- `index.md`: content-oriented map of maintained pages.
- `log.md`: chronological append-only log of wiki changes.

## Learning Rules

1. Treat failures as evidence, not identity. Update tactics before changing the
   soul.
2. Treat passed nodes and gates as signals too. Reinforce what worked.
3. Contradictions stay visible until resolved; do not erase older claims without
   noting what superseded them.
4. Soul edits are rare. They should clarify or mature the soul, not replace its
   core intent.
5. If a node or gate supplied a temporary soul/header, separate what was learned
   for that context from what belongs to the daemon's own lasting identity.
6. Mini-brain entries are searchable evidence beneath the wiki, not a prompt
   preload and not a replacement for curated wiki pages.
7. Respect memory caps. Long life should improve retrieval and synthesis
   quality without growing the normal prompt packet.
8. Before claiming work, read `pages/brain/blocked-patterns.md` and avoid any
   active pattern unless new evidence explicitly resolves it.
"""


def _index_text(*, daemon_id: str, display_name: str, today: str) -> str:
    return f"""---
title: Daemon Wiki Index
type: index
updated: {today}
daemon_id: {daemon_id}
schema_version: {SCHEMA_VERSION}
---

# {display_name} Wiki

## Core Pages

- [[self-model/current-self]] - working synthesis of strengths, weaknesses,
  preferences, and risks.
- [[signals/learning-signals]] - chronological digest of node and gate signals.
- [[decisions/decision-policy]] - how the daemon uses its soul and wiki when
  choosing eligible work.
- [[soul-evolution/proposals]] - proposed soul clarifications, not automatic
  soul rewrites.
- [[brain/review]] - promoted mini-brain memories that became stable wiki
  guidance.
- [[brain/blocked-patterns]] - rejected work shapes and verdict feedback the
  daemon must check before claiming.
"""


def _current_self_text(*, display_name: str, today: str) -> str:
    return f"""---
title: Current Self
type: self_model
updated: {today}
---

# Current Self

`{display_name}` has not accumulated enough signals yet. Future daemon runs
should update this page after meaningful passes, failures, and gate outcomes.

## Stable Strengths

- Unknown.

## Known Failure Modes

- Unknown.

## Current Learning Questions

- Which node and gate types best fit this soul?
- Which refusal patterns are principled soul alignment versus avoidable fear?
- Which tactics produce reliable outcomes without changing the soul's spirit?
"""


def _learning_signals_text(*, today: str) -> str:
    return f"""---
title: Learning Signals
type: signal_digest
updated: {today}
---

# Learning Signals

Append short digests of node and gate outcomes here. Raw source records live in
`raw/signals/` and should remain immutable.
"""


def _decision_policy_text(*, today: str) -> str:
    return f"""---
title: Decision Policy
type: policy
updated: {today}
---

# Decision Policy

When choosing eligible work, read the soul first, then this wiki. The wiki may
explain tactics, preferences, and learned risk, but it does not override the
soul's core intent.

## Current Policy

- Prefer work that fits the soul and has evidence of good outcomes.
- Avoid work that repeatedly violates the soul unless a node/gate explicitly
  supplies a temporary context that the daemon accepts.
- Money, reputation, public-good impact, and interest are comparable only after
  soul eligibility is satisfied.
"""


def _soul_proposals_text(*, today: str) -> str:
    return f"""---
title: Soul Evolution Proposals
type: soul_evolution
updated: {today}
---

# Soul Evolution Proposals

Use this page to draft rare soul clarifications. A proposal should explain:

- which repeated signals motivated it;
- why tactics or wiki updates are insufficient;
- how the proposal preserves the soul's original spirit;
- what behavior should change after adoption.
"""


def _brain_review_text(*, today: str) -> str:
    return f"""---
title: Brain Review
type: brain_review
updated: {today}
---

# Brain Review

Promoted mini-brain memories are summarized here. The daemon brain database is
the searchable atomic store; this page is the curated wiki face.
"""


def _blocked_patterns_text(*, today: str) -> str:
    return f"""---
title: Blocked Patterns
type: blocked_patterns
updated: {today}
---

# Blocked Patterns

This page is the pre-claim loop-discipline page. Read it before claiming new
work, before drafting a coding packet, and before a release-gate verdict.

## Pre-Claim Read

Before claiming work, compare the request against the active patterns below.
If a pattern matches, proceed only when the packet cites fresh evidence that
the block no longer applies.

## Active Patterns

- Unknown. Add concise patterns when a gate, review, or verdict rejects a
  repeatable work shape.

## Evidence Required Before Repeating

- Cite the source verdict, rejection, or failed run that created the pattern.
- Explain what changed since the block was recorded.
- Attach run or review evidence proving the repeated shape is no longer
  blocked.

## Verdict Feedback

Rejected coding packets and release gates should feed back here as
`verdict-feedback` lessons when they describe a reusable blocked pattern.
Automatic verdict-feedback Trigger wiring and end-to-end autoresearch proof are
deferred until BUG-049 supplies terminal run evidence for the closed loop.
"""


def scaffold_daemon_wiki(
    base_path: str | Path,
    *,
    daemon: dict[str, Any],
    soul_text: str = "",
) -> dict[str, Any]:
    """Create the wiki tree for a soul-bearing daemon if needed.

    Returns internal host-local metadata, including the absolute root path.
    Do not expose this return shape directly on public platform surfaces.
    """
    if not daemon.get("has_soul"):
        raise ValueError("daemon wiki requires a soul-bearing daemon")

    daemon_id = str(daemon.get("daemon_id") or "").strip()
    if not daemon_id:
        raise ValueError("daemon_id is required")

    display_name = str(daemon.get("display_name") or daemon_id)
    soul_hash = str(daemon.get("soul_hash") or "")
    root = daemon_wiki_root(base_path, daemon_id)
    today = _utc_now().date().isoformat()

    for rel in (
        "raw/signals",
        "decision_log",
        "soul_versions",
        "claim_proofs",
        "status",
        "pages/self-model",
        "pages/signals",
        "pages/decisions",
        "pages/soul-evolution",
        "pages/brain",
        "drafts/soul-evolution",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)

    _write_if_missing(
        root / "WIKI.md",
        _schema_text(
            daemon_id=daemon_id,
            display_name=display_name,
            soul_hash=soul_hash,
            today=today,
        ),
    )
    _write_if_missing(
        root / "index.md",
        _index_text(daemon_id=daemon_id, display_name=display_name, today=today),
    )
    _write_if_missing(
        root / "log.md",
        f"# Daemon Wiki Log\n\n## [{today}] scaffold | wiki created\n",
    )
    _write_if_missing(
        root / "pages" / "self-model" / "current-self.md",
        _current_self_text(display_name=display_name, today=today),
    )
    _write_if_missing(
        root / "pages" / "signals" / "learning-signals.md",
        _learning_signals_text(today=today),
    )
    _write_if_missing(
        root / "pages" / "decisions" / "decision-policy.md",
        _decision_policy_text(today=today),
    )
    _write_if_missing(
        root / "pages" / "soul-evolution" / "proposals.md",
        _soul_proposals_text(today=today),
    )
    _write_if_missing(
        root / "pages" / "brain" / "review.md",
        _brain_review_text(today=today),
    )
    _write_if_missing(
        root / "pages" / "brain" / "blocked-patterns.md",
        _blocked_patterns_text(today=today),
    )
    if soul_text.strip():
        _write_if_missing(root / "raw" / "initial-soul.md", soul_text.strip() + "\n")

    return {
        "daemon_id": daemon_id,
        "host_local": True,
        "schema_version": SCHEMA_VERSION,
        "wiki_root": str(root),
        "scaffolded": True,
    }


def record_daemon_signal(
    base_path: str | Path,
    *,
    daemon_id: str,
    source_kind: str,
    source_id: str,
    outcome: str,
    summary: str,
    details: str = "",
    metadata: dict[str, Any] | None = None,
    recorded_at: datetime | None = None,
) -> dict[str, Any]:
    """Record an immutable learning signal from a node, gate, or manual note."""
    from workflow.daemon_registry import get_daemon

    kind = source_kind.strip().lower()
    if kind not in VALID_SIGNAL_SOURCES:
        raise ValueError(f"source_kind must be one of {sorted(VALID_SIGNAL_SOURCES)}")
    normalized_outcome = outcome.strip().lower() or "unknown"
    if normalized_outcome not in VALID_SIGNAL_OUTCOMES:
        raise ValueError(
            f"outcome must be one of {sorted(VALID_SIGNAL_OUTCOMES)}"
        )
    clean_summary = summary.strip()
    if not clean_summary:
        raise ValueError("summary is required")

    daemon = get_daemon(base_path, daemon_id=daemon_id, include_soul=True)
    if not daemon.get("has_soul"):
        raise ValueError("soulless daemons do not have learning wikis")

    wiki = scaffold_daemon_wiki(
        base_path,
        daemon=daemon,
        soul_text=str(daemon.get("soul_text") or ""),
    )
    root = Path(wiki["wiki_root"])
    when = recorded_at or _utc_now()
    stamp = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    filename = _signal_filename(
        source_kind=kind,
        source_id=source_id,
        outcome=normalized_outcome,
        recorded_at=when,
    )
    raw_path = root / "raw" / "signals" / filename
    meta = metadata or {}
    meta_lines = "\n".join(
        f"- {key}: {value}"
        for key, value in sorted(meta.items())
        if str(key).strip()
    )
    raw_path.write_text(
        f"""---
type: daemon_signal
daemon_id: {daemon["daemon_id"]}
source_kind: {kind}
source_id: {_safe_slug(source_id, fallback="unknown")}
outcome: {normalized_outcome}
recorded_at: {stamp}
schema_version: {SCHEMA_VERSION}
---

# {kind.title()} Signal: {normalized_outcome}

## Summary

{clean_summary}

## Details

{details.strip() or "No additional details recorded."}

## Metadata

{meta_lines or "- none"}
""",
        encoding="utf-8",
        newline="\n",
    )

    rel_signal = raw_path.relative_to(root).as_posix()
    signal_line = (
        f"\n## [{stamp}] {kind} | {normalized_outcome} | {source_id}\n\n"
        f"- Raw: `{rel_signal}`\n"
        f"- Summary: {clean_summary}\n"
    )
    _append_line(root / "pages" / "signals" / "learning-signals.md", signal_line)
    _append_line(
        root / "log.md",
        f"\n## [{stamp}] signal | {kind}:{source_id} | {normalized_outcome}\n",
    )

    return {
        "daemon_id": daemon["daemon_id"],
        "host_local": True,
        "schema_version": SCHEMA_VERSION,
        "signal_id": raw_path.stem,
        "signal_path": str(raw_path),
        "outcome": normalized_outcome,
        "source_kind": kind,
        "source_id": source_id,
    }


def read_daemon_wiki_context(
    base_path: str | Path,
    *,
    daemon_id: str,
    max_chars: int = 8000,
) -> dict[str, Any]:
    """Read the bounded memory packet future runs may load before reflection."""
    root = daemon_wiki_root(base_path, daemon_id)
    if not root.exists():
        return {
            "daemon_id": daemon_id,
            "host_local": True,
            "exists": False,
            "context": "",
        }
    from workflow.daemon_memory import build_daemon_memory_packet

    packet = build_daemon_memory_packet(
        base_path,
        daemon_id=daemon_id,
        max_chars=max_chars,
        enforce_cap=True,
    )
    packet["schema_version"] = SCHEMA_VERSION
    return packet
