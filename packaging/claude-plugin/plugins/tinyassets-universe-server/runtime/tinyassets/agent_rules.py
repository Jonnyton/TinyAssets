"""The owner's Custom Rules for their agents (harness D1a).

Founder, 2026-10-01: a new user's universe works the way ChatGPT dots work,
and dots act under per-action Custom Rules with four behaviours: take action
without asking, take action if pre-approved, ask before taking action, or hand
off to you (design #4172 §4.8-4.10).

A rule names an *action class* (what kind of thing the agent is about to do),
optionally narrowed to one connection and one operation, and gives it one of
the four behaviours. Every enforcement point asks :func:`decide` before it acts;
the most specific matching rule wins, and between equally specific rules the
stricter one does.

**Who writes rules.** Only the owner, through the owner door. The store lives
beside the session records in the data root's ``.agent-sessions/<universe>/``,
outside every universe folder, so no process the universe runs (the agent's
tools, a workflow's provider jail, an extension) can create, read or change
it. An agent that wants a different rule raises a request.

**Defaults are rules, not policy.** A universe is seeded with rules that
reproduce dots: inside the universe the agent just works; reaching other people,
publishing, sharing and spending ask first; and three hand-backs (moving money,
security changes, granting others access) hand off to the owner. All of them
are the owner's to edit -- the only fixed platform floor is cross-user isolation
-- but loosening a hand-back must be confirmed against the plain words in
:data:`HANDBACK_CONSEQUENCES`.

D1a enforces at the credential-blind effector, where rules can only TIGHTEN the
standing destination grants already checked there. Declared operation kinds
(which make the hand-back classes bind), the agent's execution context, and the
auto-review arrive in D1b-D1d.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from tinyassets import agent_sessions

DO = "do"
DO_IF_PREAPPROVED = "do_if_preapproved"
ASK_FIRST = "ask_first"
HAND_OFF = "hand_off"
#: Strictest last; ties between equally specific rules go to the stricter.
BEHAVIOURS = (DO, DO_IF_PREAPPROVED, ASK_FIRST, HAND_OFF)

#: Plain words for each behaviour, as the Rules tab says them.
BEHAVIOUR_LABELS = {
    DO: "Take action without asking",
    DO_IF_PREAPPROVED: "Take action if pre-approved",
    ASK_FIRST: "Ask before taking action",
    HAND_OFF: "Hand off to you",
}

#: The action classes the platform can recognise, with what each covers.
ACTION_CLASSES = {
    "workspace.files": "Reading and changing files in its own workspace",
    "workspace.shell": "Running commands in its own workspace",
    "workspace.workflows": "Creating, editing and running its own workflows",
    "shell.egress": "Using the public internet from its shell",
    "app.read": "Reading from a connected app",
    "app.write": "Changing something in a connected app",
    "people.message": "Sending a message to a person",
    "commons.publish": "Publishing to the commons",
    "share": "Sharing your universe or its work with someone",
    "spend": "Spending money over a budget you set",
    "browser.action": "Submitting a form or pressing a purchase button in its browser",
    "money.move": "Moving money or making a payment",
    "security.change": "Changing a password, credential or security setting",
    "access.grant": "Giving another person access to your accounts or data",
}

#: The three dots hand-backs, and what turning one off allows, said plainly.
HANDBACK_CONSEQUENCES = {
    "money.move": "Your agent will be able to move money or pay from connected "
                  "accounts without handing it to you.",
    "security.change": "Your agent will be able to change passwords, credentials "
                       "and security settings on your accounts without handing it to you.",
    "access.grant": "Your agent will be able to give other people access to your "
                    "accounts or data without handing it to you.",
}

#: The seed a new universe starts from (design #4172 §4.8 seed table).
SEED_RULES = (
    ("workspace.files", DO), ("workspace.shell", DO), ("workspace.workflows", DO),
    ("shell.egress", DO), ("app.read", DO),
    # A write to a destination the owner already granted proceeds on that grant
    # (checked at the effector); this rule decides everything before it.
    ("app.write", DO),
    ("people.message", ASK_FIRST), ("commons.publish", ASK_FIRST), ("share", ASK_FIRST),
    ("spend", ASK_FIRST), ("browser.action", ASK_FIRST),
    ("money.move", HAND_OFF), ("security.change", HAND_OFF), ("access.grant", HAND_OFF),
)

#: The agent a rule is for. D8 adds a roster; until then every rule is the main agent's.
MAIN_AGENT = "main"

_FILE = "rules.db"
_SCHEMA = """CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,
    action_class TEXT NOT NULL,
    connection TEXT NOT NULL DEFAULT '',
    operation TEXT NOT NULL DEFAULT '',
    behaviour TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    seeded INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL,
    UNIQUE(agent, action_class, connection, operation))"""


class RuleRefused(ValueError):
    """A rule change cannot be saved as asked (unknown class or behaviour, or a
    hand-back loosened without confirming what that allows)."""


@dataclass(frozen=True, slots=True)
class Rule:
    id: int
    agent: str
    action_class: str
    connection: str
    operation: str
    behaviour: str
    note: str = ""
    seeded: bool = False

    def as_dict(self) -> dict:
        return {
            "id": self.id, "agent": self.agent, "action_class": self.action_class,
            "covers": ACTION_CLASSES.get(self.action_class, ""),
            "connection": self.connection, "operation": self.operation,
            "behaviour": self.behaviour, "label": BEHAVIOUR_LABELS[self.behaviour],
            "note": self.note, "seeded": self.seeded,
        }


@dataclass(frozen=True, slots=True)
class Decision:
    behaviour: str
    rule_id: int | None
    reason: str

    @property
    def proceeds(self) -> bool:
        return self.behaviour == DO


def _connect(universe_dir: Path) -> sqlite3.Connection:
    path = agent_sessions._records_dir(Path(universe_dir)) / _FILE
    conn = sqlite3.connect(path, timeout=10.0, isolation_level=None)
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute(_SCHEMA)
    return conn


def _seed(conn: sqlite3.Connection, agent: str) -> None:
    """Write the seed for ``agent`` once; an owner's edits are never re-seeded."""
    present = conn.execute("SELECT COUNT(*) FROM rules WHERE agent = ?", (agent,)).fetchone()[0]
    if present:
        return
    now = time.time()
    conn.executemany(
        "INSERT OR IGNORE INTO rules (agent, action_class, behaviour, seeded, updated_at) "
        "VALUES (?, ?, ?, 1, ?)",
        [(agent, cls, behaviour, now) for cls, behaviour in SEED_RULES],
    )


def _rule(row) -> Rule:
    return Rule(int(row[0]), row[1], row[2], row[3], row[4], row[5], row[6], bool(row[7]))


def list_rules(universe_dir: Path, agent: str = MAIN_AGENT) -> list[Rule]:
    """Every rule of ``agent``, seeding a new universe's defaults first."""
    with closing(_connect(universe_dir)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _seed(conn, agent)
        rows = conn.execute(
            "SELECT id, agent, action_class, connection, operation, behaviour, note, seeded "
            "FROM rules WHERE agent = ? ORDER BY action_class, connection, operation",
            (agent,),
        ).fetchall()
        conn.execute("COMMIT")
    return [_rule(row) for row in rows]


def _specificity(rule: Rule) -> int:
    return (2 if rule.connection else 0) + (1 if rule.operation else 0)


def decide(universe_dir: Path, action_class: str, *, connection: str = "",
           operation: str = "", agent: str = MAIN_AGENT) -> Decision:
    """The behaviour for one action, from the owner's rules.

    A class no rule names is asked about first, never assumed allowed.
    """
    candidates = [
        rule for rule in list_rules(universe_dir, agent)
        if rule.action_class == action_class
        and rule.connection in ("", connection)
        and rule.operation in ("", operation.upper())
    ]
    if not candidates:
        return Decision(ASK_FIRST, None, f"no rule covers {action_class}; asking first")
    best = max(candidates, key=lambda r: (_specificity(r), BEHAVIOURS.index(r.behaviour)))
    return Decision(best.behaviour, best.id,
                    f"{BEHAVIOUR_LABELS[best.behaviour]} ({best.action_class}"
                    + (f" on {best.connection}" if best.connection else "")
                    + (f" {best.operation}" if best.operation else "") + ")")


def set_rule(universe_dir: Path, action_class: str, behaviour: str, *, connection: str = "",
             operation: str = "", note: str = "", agent: str = MAIN_AGENT,
             confirm_handback: bool = False) -> Rule:
    """Save one rule (the owner door is the only caller).

    Loosening a hand-back class below ``hand_off`` is refused unless the owner
    confirmed what that allows (:data:`HANDBACK_CONSEQUENCES`).
    """
    if action_class not in ACTION_CLASSES:
        raise RuleRefused(f"unknown action class {action_class!r}")
    if behaviour not in BEHAVIOURS:
        raise RuleRefused(f"unknown behaviour {behaviour!r}")
    if (action_class in HANDBACK_CONSEQUENCES and behaviour != HAND_OFF
            and not confirm_handback):
        raise RuleRefused(HANDBACK_CONSEQUENCES[action_class]
                          + " Confirm to save this rule.")
    with closing(_connect(universe_dir)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _seed(conn, agent)
        conn.execute(
            "INSERT INTO rules (agent, action_class, connection, operation, behaviour, note, "
            "seeded, updated_at) VALUES (?, ?, ?, ?, ?, ?, 0, ?) "
            "ON CONFLICT(agent, action_class, connection, operation) DO UPDATE SET "
            "behaviour = excluded.behaviour, note = excluded.note, seeded = 0, "
            "updated_at = excluded.updated_at",
            (agent, action_class, connection.strip(), operation.strip().upper(),
             behaviour, note.strip()[:500], time.time()),
        )
        row = conn.execute(
            "SELECT id, agent, action_class, connection, operation, behaviour, note, seeded "
            "FROM rules WHERE agent = ? AND action_class = ? AND connection = ? "
            "AND operation = ?",
            (agent, action_class, connection.strip(), operation.strip().upper()),
        ).fetchone()
        conn.execute("COMMIT")
    return _rule(row)


def delete_rule(universe_dir: Path, rule_id: int, *, agent: str = MAIN_AGENT) -> bool:
    """Remove one narrowed rule. A class-wide rule is changed, never removed, so
    every class keeps a visible behaviour."""
    with closing(_connect(universe_dir)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT connection, operation FROM rules WHERE id = ? AND agent = ?",
            (int(rule_id), agent),
        ).fetchone()
        if row is None or not (row[0] or row[1]):
            conn.execute("ROLLBACK")
            return False
        conn.execute("DELETE FROM rules WHERE id = ?", (int(rule_id),))
        conn.execute("COMMIT")
    return True
