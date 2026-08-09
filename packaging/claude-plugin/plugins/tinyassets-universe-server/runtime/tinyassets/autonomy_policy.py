"""Per-universe LEARNED autonomy / trust policy.

Founder 2026-08-09: "we are intentionally making a proactive agent that carries
out the vision as it understands it and can self-improve — it should LEARN over
time what I trust it to do without asking and what I'd want it to ask about
first. That UX works for all users."

So consent is not a fixed list of always-gated actions. An action maps to a
CLASS (by its surface + its real-world EFFECTS), and a per-universe policy says
whether that class is TRUSTED (act autonomously, no ask) or ASK (get a fresh
yes). Defaults seed a sensible starting point — internal work and self-patching
are trusted so the agent is proactive out of the box; publishing to the world,
merging to main, and spending third-party money are ask-first — but EVERY class
can be promoted or demoted by LEARNING from the founder, and each universe keeps
its own learned policy.

The genuinely dangerous classes stay ask-by-default until the founder explicitly
trusts them; nothing here lets the agent trust itself (only a recorded founder
decision changes a rule).
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DECISION_TRUST = "trust"
DECISION_ASK = "ask"

#: Effect sinks that keep a run ask-first by default: they reach the world,
#: spend real money, or are hard to reverse. A run WITHOUT any of these (a draft
#: PR to the founder's own repo, internal work, drafting, reads) is "internal"
#: and trusted by default. ``github_pull_request`` (a DRAFT PR) is deliberately
#: NOT here — it is reversible self-improvement; ``github_merge`` (merge to main)
#: is.
HIGH_STAKES_SINKS = frozenset({
    "twitter_post",       # publishing in the founder's name, to the world
    "github_merge",       # merging to main / changing production
})

#: Starting policy. Absent classes default to ASK (safe). Learned rules override.
DEFAULT_POLICY = {
    "run.internal": DECISION_TRUST,       # self-patch drafts, internal runs, drafts
    "automation.run": DECISION_TRUST,     # running the founder's own vision automations
    "run.high_stakes": DECISION_ASK,      # a run that publishes/merges
    "automation.high_stakes": DECISION_ASK,
    "effector.grant": DECISION_ASK,       # authorizing posting/effect credentials
    "chat.bind": DECISION_ASK,            # making an agent live to OTHER people
}

_DB_NAME = ".autonomy_policy.db"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS trust_rules (
    action_class TEXT PRIMARY KEY,
    decision     TEXT NOT NULL,
    learned_from TEXT NOT NULL DEFAULT '',
    updated_at   REAL NOT NULL
);
"""


def action_class(surface: str, action: str, effects: "list | set | None") -> str:
    """Map a concrete action + its declared effects to a policy CLASS."""
    s = (surface or "").strip().lower()
    a = (action or "").strip().lower()
    eff = {str(e).strip().lower() for e in (effects or [])}
    high = bool(eff & HIGH_STAKES_SINKS)
    if (s, a) == ("branch", "run"):
        return "run.high_stakes" if high else "run.internal"
    if s == "scheduled_work" and a in ("run_now", "resume"):
        return "automation.high_stakes" if high else "automation.run"
    if (s, a) == ("effector", "grant"):
        return "effector.grant"
    if (s, a) == ("chat_surface", "bind_channel"):
        return "chat.bind"
    return f"{s}.{a}"


def _db_path(universe_dir: "str | Path") -> Path:
    return Path(universe_dir) / _DB_NAME


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(_SCHEMA)
    return conn


def _learned_decision(universe_dir: "str | Path", cls: str) -> str | None:
    db_path = _db_path(universe_dir)
    if not db_path.exists():
        return None
    try:
        conn = _connect(db_path)
        try:
            row = conn.execute(
                "SELECT decision FROM trust_rules WHERE action_class = ?", (cls,)
            ).fetchone()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - a policy-read failure must fail SAFE
        logger.warning("autonomy_policy: read failed for %s", cls, exc_info=True)
        return None
    return str(row[0]) if row else None


def decision_for(universe_dir: "str | Path", cls: str) -> str:
    """The effective decision for a class: learned rule > default > ASK (safe)."""
    learned = _learned_decision(universe_dir, cls)
    if learned in (DECISION_TRUST, DECISION_ASK):
        return learned
    return DEFAULT_POLICY.get(cls, DECISION_ASK)


def is_trusted(universe_dir: "str | Path", cls: str) -> bool:
    """True if this class may run autonomously (no fresh ask). Fail-safe: a read
    error resolves to the default (never silently trusts an unknown class)."""
    return decision_for(universe_dir, cls) == DECISION_TRUST


def set_trust(
    universe_dir: "str | Path",
    cls: str,
    decision: str,
    *,
    learned_from: str = "",
) -> None:
    """Learn a rule from the FOUNDER: trust a class (stop asking) or ask for it.

    Only a recorded founder decision reaches here — the agent never trusts itself.
    """
    if decision not in (DECISION_TRUST, DECISION_ASK):
        raise ValueError(f"decision must be trust|ask, got {decision!r}")
    if not cls:
        raise ValueError("action_class is required")
    db_path = _db_path(universe_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO trust_rules (action_class, decision, learned_from, updated_at)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(action_class) DO UPDATE SET"
            " decision=excluded.decision, learned_from=excluded.learned_from,"
            " updated_at=excluded.updated_at",
            (cls, decision, str(learned_from or ""), time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def list_policy(universe_dir: "str | Path") -> dict[str, dict[str, str]]:
    """The effective policy (defaults merged with learned rules), for display."""
    out: dict[str, dict[str, str]] = {}
    for cls, decision in DEFAULT_POLICY.items():
        out[cls] = {"decision": decision, "source": "default"}
    db_path = _db_path(universe_dir)
    if db_path.exists():
        try:
            conn = _connect(db_path)
            try:
                for cls, decision, learned_from in conn.execute(
                    "SELECT action_class, decision, learned_from FROM trust_rules"
                ).fetchall():
                    out[str(cls)] = {
                        "decision": str(decision),
                        "source": f"learned:{learned_from}" if learned_from else "learned",
                    }
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            logger.warning("autonomy_policy: list failed", exc_info=True)
    return out


__all__ = [
    "DECISION_ASK",
    "DECISION_TRUST",
    "DEFAULT_POLICY",
    "HIGH_STAKES_SINKS",
    "action_class",
    "decision_for",
    "is_trusted",
    "list_policy",
    "set_trust",
]
