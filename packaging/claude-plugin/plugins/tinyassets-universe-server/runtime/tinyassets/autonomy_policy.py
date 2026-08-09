"""Per-universe LEARNED autonomy / trust policy.

Founder 2026-08-09: "we are intentionally making a proactive agent that carries
out the vision as it understands it and can self-improve — it should LEARN over
time what I trust it to do without asking and what I'd want it to ask about
first. That UX works for all users."

So consent is not a fixed list of always-gated actions. An action maps to a
CLASS (by its surface + its real-world EFFECTS), and a per-universe policy says
whether that class is TRUSTED (act autonomously) or ASK (get a fresh yes).
Defaults make the agent proactive out of the box for reversible / own-asset work
(self-patching draft PRs, internal runs, delivering to the founder's own chat)
while asking for anything that reaches the world, merges, or spends; every class
can be promoted or demoted by LEARNING from the founder, per universe.

Security posture (Codex security review 2026-08-09, hardened):
- **Allowlist, not denylist — FAIL CLOSED.** A run is "internal" (trustable)
  ONLY if every declared effect is in ``SAFE_SINKS``. An unknown, new, or
  misspelled effect makes the run high-stakes → ask. Nothing new becomes
  autonomous by default.
- **The store lives at the DATA ROOT, keyed by universe_id — never inside the
  universe workspace the agent can write.** The sandboxed turn has no shell and
  its ``workspace_write`` is scoped to its own universe dir, so it cannot reach
  or forge this file; the only writer is :func:`set_trust`, reached only through
  the founder-gated ``trust`` surface (promoting a class needs the founder's yes
  once). The agent can never self-promote.
- A policy-read error resolves to the class DEFAULT (never silently trusts).
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DECISION_TRUST = "trust"
DECISION_ASK = "ask"

#: ALLOWLIST of effect sinks that are safe to run autonomously (reversible /
#: own-asset / internal delivery). A run whose effects are ALL in this set (or
#: which has no external effect) is "internal". ANY effect outside it — twitter
#: (publish to the world), github_merge (merge to production), a host-desktop
#: install, or ANYTHING UNKNOWN — makes the run high-stakes and ask-first.
#: ``github_pull_request`` opens a PR (a reversible proposal, not a merge) and is
#: additionally bounded by the effector's capability gate, which requires a
#: deposited founder credential for the destination repo — so it cannot PR a
#: repo the founder does not own.
SAFE_SINKS = frozenset({
    "github_pull_request",   # a reversible PR proposal to a credentialed (owned) repo
    "chat_post",             # deliver output to the founder's own chat
    "wiki_write_back",       # write the universe's OWN wiki
})

#: Starting policy. Absent classes default to ASK (safe). Learned rules override.
DEFAULT_POLICY = {
    "run.internal": DECISION_TRUST,       # self-patch drafts, internal runs, drafts
    "automation.run": DECISION_TRUST,     # running the founder's own vision automations
    "run.high_stakes": DECISION_ASK,      # a run that publishes/merges/spends/unknown
    "automation.high_stakes": DECISION_ASK,
    "effector.grant": DECISION_ASK,       # authorizing posting/effect credentials
    "chat.bind": DECISION_ASK,            # making an agent live to OTHER people
}

_DB_NAME = ".autonomy_policy.db"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS trust_rules (
    universe_id  TEXT NOT NULL,
    action_class TEXT NOT NULL,
    decision     TEXT NOT NULL,
    learned_from TEXT NOT NULL DEFAULT '',
    updated_at   REAL NOT NULL,
    PRIMARY KEY (universe_id, action_class)
);
"""


def action_class(surface: str, action: str, effects: "list | set | None") -> str:
    """Map a concrete action + its declared effects to a policy CLASS.

    FAIL CLOSED: a run is internal only if EVERY declared effect is known-safe.
    """
    s = (surface or "").strip().lower()
    a = (action or "").strip().lower()
    eff = {str(e).strip().lower() for e in (effects or []) if str(e).strip()}
    unsafe = bool(eff - SAFE_SINKS)  # any effect outside the allowlist (incl. unknown)
    if (s, a) == ("branch", "run"):
        return "run.high_stakes" if unsafe else "run.internal"
    if s == "scheduled_work" and a in ("run_now", "resume"):
        return "automation.high_stakes" if unsafe else "automation.run"
    if (s, a) == ("effector", "grant"):
        return "effector.grant"
    if (s, a) == ("chat_surface", "bind_channel"):
        return "chat.bind"
    return f"{s}.{a}"


def _db_path(base_path: "str | Path") -> Path:
    return Path(base_path) / _DB_NAME


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(_SCHEMA)
    return conn


def _learned_decision(base_path: "str | Path", universe_id: str, cls: str) -> str | None:
    db_path = _db_path(base_path)
    if not db_path.exists():
        return None
    try:
        conn = _connect(db_path)
        try:
            row = conn.execute(
                "SELECT decision FROM trust_rules WHERE universe_id = ? AND action_class = ?",
                (universe_id, cls),
            ).fetchone()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - a policy-read failure must fail SAFE
        logger.warning("autonomy_policy: read failed for %s", cls, exc_info=True)
        return None
    return str(row[0]) if row else None


def decision_for(base_path: "str | Path", universe_id: str, cls: str) -> str:
    """The effective decision for a class: learned rule > default > ASK (safe)."""
    learned = _learned_decision(base_path, universe_id, cls)
    if learned in (DECISION_TRUST, DECISION_ASK):
        return learned
    return DEFAULT_POLICY.get(cls, DECISION_ASK)


def is_trusted(base_path: "str | Path", universe_id: str, cls: str) -> bool:
    """True if this class may run autonomously (no fresh ask). Fail-safe: a read
    error resolves to the default (never silently trusts an unknown class)."""
    return decision_for(base_path, universe_id, cls) == DECISION_TRUST


def set_trust(
    base_path: "str | Path",
    universe_id: str,
    cls: str,
    decision: str,
    *,
    learned_from: str = "",
) -> None:
    """Learn a rule from the FOUNDER: trust a class (stop asking) or ask for it.

    Only reached through the founder-gated ``trust`` surface — the agent never
    trusts itself. The store is at the data root, outside the agent's writable
    workspace.
    """
    if decision not in (DECISION_TRUST, DECISION_ASK):
        raise ValueError(f"decision must be trust|ask, got {decision!r}")
    if not cls or not universe_id:
        raise ValueError("universe_id and action_class are required")
    db_path = _db_path(base_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO trust_rules"
            " (universe_id, action_class, decision, learned_from, updated_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(universe_id, action_class) DO UPDATE SET"
            " decision=excluded.decision, learned_from=excluded.learned_from,"
            " updated_at=excluded.updated_at",
            (universe_id, cls, decision, str(learned_from or ""), time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def list_policy(base_path: "str | Path", universe_id: str) -> dict[str, dict[str, str]]:
    """The effective policy (defaults merged with learned rules), for display."""
    out: dict[str, dict[str, str]] = {}
    for cls, decision in DEFAULT_POLICY.items():
        out[cls] = {"decision": decision, "source": "default"}
    db_path = _db_path(base_path)
    if db_path.exists():
        try:
            conn = _connect(db_path)
            try:
                rows = conn.execute(
                    "SELECT action_class, decision, learned_from FROM trust_rules"
                    " WHERE universe_id = ?",
                    (universe_id,),
                ).fetchall()
            finally:
                conn.close()
            for cls, decision, learned_from in rows:
                out[str(cls)] = {
                    "decision": str(decision),
                    "source": f"learned:{learned_from}" if learned_from else "learned",
                }
        except Exception:  # noqa: BLE001
            logger.warning("autonomy_policy: list failed", exc_info=True)
    return out


__all__ = [
    "DECISION_ASK",
    "DECISION_TRUST",
    "DEFAULT_POLICY",
    "SAFE_SINKS",
    "action_class",
    "decision_for",
    "is_trusted",
    "list_policy",
    "set_trust",
]
