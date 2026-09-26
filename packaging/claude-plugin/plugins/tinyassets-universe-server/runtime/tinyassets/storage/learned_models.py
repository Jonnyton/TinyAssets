"""Model ids that have actually worked, in two tables with two different rules.

Why it exists: a source that cannot enumerate its own catalogue could only ever
offer ids its owner had typed by hand, so a newly released model was invisible
until someone shipped a patch. Founder, 2026-09-26: "we also should not have to
put out new patches for providers ... always updates for users once one user adds
the newly available model."

**Why TWO tables.** The first version published every verified id, and Codex
refuted it: a model id is not necessarily a public name. It published a synthetic
Bedrock ARN carrying an AWS account number to every user of that source kind, and
no character rule can tell a public model name from a private account-bearing
selector without exactly the per-vendor knowledge this design forbids.

The founder's answer (2026-09-26) is a threshold instead of a rule about strings:
an id is public once it has worked for at least ``PROMOTION_OWNERS`` DISTINCT
OWNERS. A private selector -- an ARN with one account number in it, a personal
deployment name -- is by construction unique to its owner, so it can never reach
two and never leaves that owner's own list. Nobody has to classify a string, and
no vendor is named.

So:

* ``learned_model_evidence`` is PRIVATE. It carries ``owner_user_id`` and exists
  only to answer "how many distinct owners have made this id work". It is
  per-user data and is deleted with its user.
* ``learned_models`` is SHARED and still carries **no user data at all**: source
  kind, model id, first-verified time, nothing else. Reading the whole table tells
  you which ids work for a kind of source; it cannot tell you who used one, from
  which universe, when, or what they asked. The promotion COUNT never appears in
  it -- "3 owners verified this" is a population fact about users, so it stays in
  the private table and is never returned to any caller.

A shared row is EVIDENCE THAT AN ID EXISTS AND WORKED, never permission to use it.
Serving still requires the reading universe's own accepted model access.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tinyassets.storage import db_path

_SCHEMA = """CREATE TABLE IF NOT EXISTS learned_models (
  -- The KIND of source (subscription_cli, api_key_http, ...), never a connection
  -- id and never a provider account: two users on the same kind of source are
  -- exactly the ones who should share this evidence.
  source_kind TEXT NOT NULL,
  -- The model id that worked. A public name, not a secret.
  model_id TEXT NOT NULL,
  -- When this platform FIRST saw this id work at all. A property of the id, not
  -- of a person; it exists only to break a version tie.
  first_verified_at TEXT NOT NULL,
  PRIMARY KEY(source_kind, model_id))"""

_EVIDENCE_SCHEMA = """CREATE TABLE IF NOT EXISTS learned_model_evidence (
  -- PRIVATE. This table exists for one question: how many DISTINCT OWNERS have
  -- made this id work? Its answer promotes an id into the shared table above.
  source_kind TEXT NOT NULL,
  model_id TEXT NOT NULL,
  -- The only reason this table has an owner column. It is per-user data, deleted
  -- with its user, and never returned to any caller -- the promotion check
  -- returns a decision, not a population.
  owner_user_id TEXT NOT NULL,
  first_verified_at TEXT NOT NULL,
  PRIMARY KEY(source_kind, model_id, owner_user_id))"""

#: The source KIND a native (subscription CLI) connection reports, and the
#: availability basis a contributed row carries. ONE definition each, read by both
#: the writer (the coordinator) and the reader (the model plan), so the two cannot
#: disagree about what a "kind" is or about which rows are learned rather than
#: granted.
LEARNED_SOURCE_KIND = "subscription"
LEARNED_MODEL_BASIS = "platform_verified_elsewhere"

#: Every column the SHARED table will ever have. A test asserts the shipped table
#: matches, so adding a fourth column has to be a deliberate act that updates this
#: tuple and argues with the cross-user floor.
COLUMNS = ("source_kind", "model_id", "first_verified_at")

#: Columns of the PRIVATE evidence table. It is allowed an owner, because counting
#: distinct owners is its only job; it is classified as per-user data in both
#: deletion sweeps.
EVIDENCE_COLUMNS = ("source_kind", "model_id", "owner_user_id", "first_verified_at")

#: How many DISTINCT OWNERS must have made an id work before it is published to
#: everyone with that kind of source. Founder, 2026-09-26.
#:
#: Two is the smallest number that carries the privacy property, and the property
#: is the whole point: a selector that embeds one account, one tenant or one
#: personal deployment cannot be reached by a second owner, so it can never cross
#: this threshold however many times its own owner uses it. A higher number would
#: only slow the feature down without making it safer.
PROMOTION_OWNERS = 2

#: How long a write may wait for the shared database. Short by design -- see
#: ``_connect``. A read waits the same: nobody's model list is worth a stall.
_BUSY_WAIT_MS = 250

#: What must never appear in this table, by name. A counter of verifications is on
#: the list because "3 universes verified this" is a population fact about users
#: and, with timing, narrows who they are.
FORBIDDEN_COLUMNS = frozenset(
    {"owner_user_id", "universe_id", "connection_id", "actor_id", "principal_id",
     "user_id", "prompt", "reply", "credential", "verified_count", "count"}
)


@dataclass(frozen=True, slots=True)
class LearnedModel:
    source_kind: str
    model_id: str
    first_verified_at: str


#: BASIC SANITY ONLY. The charset used to be doing privacy work -- it was meant to
#: keep a private selector out of a shared table -- and it failed in both
#: directions: it admitted account-bearing ARNs and rejected documented selectors
#: like ``sonnet[1m]``. The distinct-owner threshold carries that boundary now, so
#: this only has to reject what is not an identifier at all: empty, unbounded,
#: whitespace-bearing, or control characters. Printable ASCII with no spaces keeps
#: real selectors (brackets, colons, slashes, dots) usable.
_IDENTIFIER = re.compile(r"\A[!-~]{1,200}\Z", re.ASCII)


def _clean(value: object, field: str) -> str:
    """Validate an identifier. Sanity only -- the threshold carries the privacy."""
    if type(value) is not str:
        raise ValueError(f"invalid learned model {field}")
    text = value.strip()
    if not _IDENTIFIER.match(text):
        raise ValueError(f"invalid learned model {field}")
    return text


class LearnedModelCatalog:
    """Read/record verified model ids. Shared across users by design."""

    def __init__(self, base_path: str | Path) -> None:
        self.base_path = Path(base_path)

    def _connect(self, *, create: bool) -> sqlite3.Connection:
        path = db_path(self.base_path)
        if not create and not path.exists():
            return None
        if create:
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, timeout=_BUSY_WAIT_MS / 1000,
                                   isolation_level=None)
        else:
            # Non-creating: an observational read must not bring a database into
            # being. `mode=rw` opens an existing file and refuses to create one,
            # which also closes the gap after the exists() check above.
            conn = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True,
                                   timeout=_BUSY_WAIT_MS / 1000, isolation_level=None)
        conn.row_factory = sqlite3.Row
        # A SHORT wait, on purpose. Codex measured the old 30s timeout blocking a
        # reply-path write for 318 ms behind a 300 ms competing writer and stalling
        # an asyncio heartbeat (#4028). Learning is optional and repeatable: the
        # next successful turn on the same id records it. Waiting on a busy shared
        # database to do it is never worth a user's latency.
        conn.execute(f"PRAGMA busy_timeout = {_BUSY_WAIT_MS}")
        return conn

    def record(self, *, source_kind: str, model_id: str, owner_user_id: str,
               now: datetime | None = None) -> bool:
        """Record one owner's verified id; publish it once two owners have.

        Returns whether this call PUBLISHED the id -- not whether it stored
        evidence -- because publication is the only outcome another user can see.

        Two steps in one transaction:

        1. The owner's own evidence, private, idempotent on
           ``(source_kind, model_id, owner_user_id)``. The same owner's second
           universe adds nothing, which is what makes "distinct OWNERS" mean what
           it says rather than "distinct universes".
        2. If ``PROMOTION_OWNERS`` distinct owners now have evidence for this id,
           publish it to the shared table. A private selector cannot get here: an
           ARN with one account number in it is unique to its owner by
           construction, so it stays at one owner forever.

        The first-verified time published is the EARLIEST across the owners who
        verified it, so it remains a property of the id rather than of whoever
        happened to be second.

        Callers treat this as best-effort -- failing to learn must never fail the
        call that succeeded -- but the failure is raised here rather than
        swallowed, so the caller decides that explicitly at its own site.
        """
        kind = _clean(source_kind, "source kind")
        model = _clean(model_id, "model id")
        owner = _clean(owner_user_id, "owner")
        stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        when = stamp.isoformat(timespec="microseconds").replace("+00:00", "Z")
        conn = self._connect(create=True)
        try:
            conn.execute(_SCHEMA)
            conn.execute(_EVIDENCE_SCHEMA)
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO learned_model_evidence VALUES (?, ?, ?, ?)",
                    (kind, model, owner, when),
                )
                # COUNT and MIN only. No owner identity leaves this query, and the
                # count itself is never returned to a caller or stored in the
                # shared table -- "N owners verified this" is a fact about users.
                owners, earliest = conn.execute(
                    "SELECT COUNT(*), MIN(first_verified_at) FROM learned_model_evidence "
                    "WHERE source_kind = ? AND model_id = ?",
                    (kind, model),
                ).fetchone()
                published = False
                if owners >= PROMOTION_OWNERS:
                    published = conn.execute(
                        "INSERT OR IGNORE INTO learned_models VALUES (?, ?, ?)",
                        (kind, model, earliest or when),
                    ).rowcount == 1
                conn.commit()
                return published
            except BaseException:
                conn.rollback()
                raise
        finally:
            conn.close()

    def evidence_ids(self, source_kind: str, owner_user_id: str) -> list[LearnedModel]:
        """ONE OWNER's own verified ids for a source kind, oldest first.

        Scoped to a single owner on purpose: this is the private table, and a
        caller may only ever see its own evidence. There is deliberately no API
        that returns other owners' rows, or a count of them -- the promotion check
        does that counting inside a transaction and returns a decision.
        """
        kind = _clean(source_kind, "source kind")
        owner = _clean(owner_user_id, "owner")
        conn = self._connect(create=False)
        if conn is None:
            return []
        try:
            if not conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'learned_model_evidence'"
            ).fetchone():
                return []
            rows = conn.execute(
                "SELECT source_kind, model_id, first_verified_at "
                "FROM learned_model_evidence "
                "WHERE source_kind = ? AND owner_user_id = ? "
                "ORDER BY first_verified_at, model_id",
                (kind, owner),
            ).fetchall()
        finally:
            conn.close()
        return [LearnedModel(row["source_kind"], row["model_id"], row["first_verified_at"])
                for row in rows]

    def for_source_kind(self, source_kind: str) -> list[LearnedModel]:
        """Every verified id for one kind of source, oldest verification first."""
        kind = _clean(source_kind, "source kind")
        conn = self._connect(create=False)
        if conn is None:
            return []
        try:
            if not conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'learned_models'"
            ).fetchone():
                return []
            rows = conn.execute(
                "SELECT source_kind, model_id, first_verified_at FROM learned_models "
                "WHERE source_kind = ? ORDER BY first_verified_at, model_id",
                (kind,),
            ).fetchall()
        finally:
            conn.close()
        return [LearnedModel(row["source_kind"], row["model_id"], row["first_verified_at"])
                for row in rows]

    def newest_for_source_kind(self, source_kind: str) -> list[LearnedModel]:
        """The newest verified model of each class for one kind of source."""
        from tinyassets.providers.model_class import newest_per_class

        return newest_per_class(self.for_source_kind(source_kind))


def record_verified_model(base_path, *, source_kind, model_id, owner_user_id) -> bool:
    """Best-effort learn, for a caller that has already succeeded.

    The one place the failure IS swallowed, and only here, because the caller is
    always a turn that has already produced a result: a catalog write must not turn
    a delivered reply into an error. Anything a caller wants to fail on should use
    ``LearnedModelCatalog.record`` directly.

    Returns whether this call PUBLISHED the id to everyone with that source kind --
    False covers both "stored this owner's evidence, still below the threshold" and
    "could not write", because neither is visible to another user.
    """
    import logging

    try:
        return LearnedModelCatalog(base_path).record(
            source_kind=source_kind, model_id=model_id, owner_user_id=owner_user_id)
    except Exception as exc:  # noqa: BLE001 - never fail a call that already worked
        logging.getLogger("universe_server.learned_models").warning(
            "could not record a verified model id: %s", type(exc).__name__)
        return False
