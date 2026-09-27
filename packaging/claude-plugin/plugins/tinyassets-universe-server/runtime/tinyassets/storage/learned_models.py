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
  -- The public page that proved it is a public release. A URL with query and
  -- fragment stripped, and the check had to pass against THIS value, so it is
  -- provably sufficient on its own and cannot carry a tracking parameter. It is the
  -- one field here that came from an agent, which is why it is stripped and bounded
  -- rather than stored as given.
  evidence_url TEXT NOT NULL,
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

_PENDING_SCHEMA = """CREATE TABLE IF NOT EXISTS learned_model_pending (
  -- An id one owner's agent has ATTESTED is a public release, awaiting independent
  -- confirmation by other owners' agents. Not shared with anyone yet.
  source_kind TEXT NOT NULL,
  model_id TEXT NOT NULL,
  -- The public page the attesting agent cited, query and fragment already stripped.
  -- A confirmer re-fetches exactly this, so the stored value has to be sufficient
  -- on its own.
  evidence_url TEXT NOT NULL,
  -- Who attested. Present so their OWN universes can never confirm their own
  -- attestation; per-user data, deleted with its user, never returned by the queue.
  --
  -- Named owner_user_id, not attested_by, because account deletion finds per-user
  -- rows BY COLUMN NAME from its PRINCIPAL_KEYS list. A semantically nicer name was
  -- silently skipped by that sweep, leaving a departed owner's rows behind.
  owner_user_id TEXT NOT NULL,
  attested_at TEXT NOT NULL,
  PRIMARY KEY(source_kind, model_id))"""

_CONFIRMATION_SCHEMA = """CREATE TABLE IF NOT EXISTS learned_model_confirmations (
  -- One other owner's independent confirmation of a pending attestation.
  source_kind TEXT NOT NULL,
  model_id TEXT NOT NULL,
  -- Per owner, so the same owner confirming repeatedly counts once. Per-user data,
  -- and named to match PRINCIPAL_KEYS so account deletion actually finds it.
  owner_user_id TEXT NOT NULL,
  -- The model the confirming TURN ran on, recorded because the founder's bar is
  -- that a confirmation comes from a current model. A public model id, not a secret.
  confirming_model_id TEXT NOT NULL,
  confirmed_at TEXT NOT NULL,
  PRIMARY KEY(source_kind, model_id, owner_user_id))"""

#: The source KIND a native (subscription CLI) connection reports, and the
#: availability basis a contributed row carries. ONE definition each, read by both
#: the writer (the coordinator) and the reader (the model plan), so the two cannot
#: disagree about what a "kind" is or about which rows are learned rather than
#: granted.
LEARNED_SOURCE_KIND = "subscription"
LEARNED_MODEL_BASIS = "platform_verified_elsewhere"
#: An id THIS owner has already made work here. Distinct from the published basis
#: because the two are different claims: "you have run this" versus "two owners
#: elsewhere have run this". Neither is admitted without the owner's model access.
OWN_VERIFIED_BASIS = "owner_verified_here"

#: Every column the SHARED table will ever have. A test asserts the shipped table
#: matches, so adding a fourth column has to be a deliberate act that updates this
#: tuple and argues with the cross-user floor.
COLUMNS = ("source_kind", "model_id", "first_verified_at", "evidence_url")

#: Columns of the PRIVATE evidence table. It is allowed an owner, because counting
#: distinct owners is its only job; it is classified as per-user data in both
#: deletion sweeps.
EVIDENCE_COLUMNS = ("source_kind", "model_id", "owner_user_id", "first_verified_at")

#: How many OTHER owners' agents must independently confirm an attestation before it
#: is published. Founder, 2026-09-26: "it still needs to be checked by other users'
#: models with smart recent big models before it is shared more". The attester never
#: counts toward their own total.
CONFIRMATIONS_REQUIRED = 2

#: RETIRED as the publication rule. Kept only as the name of the count in step 2.
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
    #: The public page that proved it. Empty only for a row read from the private
    #: evidence table, which has no such page -- it is one owner's own history.
    evidence_url: str = ""


#: BASIC SANITY ONLY. The charset used to be doing privacy work -- it was meant to
#: keep a private selector out of a shared table -- and it failed in both
#: directions: it admitted account-bearing ARNs and rejected documented selectors
#: like ``sonnet[1m]``. The distinct-owner threshold carries that boundary now, so
#: this only has to reject what is not an identifier at all: empty, unbounded,
#: whitespace-bearing, or control characters. Printable ASCII with no spaces keeps
#: real selectors (brackets, colons, slashes, dots) usable.
#: A stripped https URL: no whitespace, no control characters, printable ASCII.
_URL_SAFE = re.compile(r"\Ahttps://[\x21-\x7e]{1,2040}\Z", re.ASCII)

_IDENTIFIER = re.compile(r"\A[!-~]{1,200}\Z", re.ASCII)


def _clean(value: object, field: str) -> str:
    """Validate an identifier. Sanity only -- the threshold carries the privacy."""
    if type(value) is not str:
        raise ValueError(f"invalid learned model {field}")
    text = value.strip()
    if not _IDENTIFIER.match(text):
        raise ValueError(f"invalid learned model {field}")
    return text


def _stamp(now: datetime | None) -> str:
    value = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone() is not None


def _clean_evidence_url(value: object) -> str:
    """An https URL with query and fragment STRIPPED, bounded.

    Stripped rather than stored as given, and the id check has to pass against this
    stripped value, so the stored URL is provably sufficient on its own. A shared
    table must not carry an agent-supplied query string: that is free-form text in a
    cross-user store, the same class of hole as the ARN and the email address in
    review rounds 1 and 2. It also cannot carry a tracking parameter.
    """
    from urllib.parse import urlsplit, urlunsplit

    if type(value) is not str or not value.strip() or len(value) > 2048:
        raise ValueError("invalid evidence url")
    parts = urlsplit(value.strip())
    if (parts.scheme != "https" or not parts.hostname or parts.username
            or parts.password or "@" in parts.netloc):
        raise ValueError("evidence url must be a public https page with no credentials")
    stripped = urlunsplit(("https", parts.netloc, parts.path, "", ""))
    if not _URL_SAFE.match(stripped):
        raise ValueError("invalid evidence url")
    return stripped


def _require_id_in_snippet(model_id: str, snippet: object) -> None:
    """The one deterministic check the platform can make with no LLM and no fetch.

    The EXACT id string must appear in what the agent says it read. Bounded because
    it is untrusted input, and never stored -- see ``attest``.
    """
    if type(snippet) is not str or not snippet.strip() or len(snippet) > 20000:
        raise ValueError("invalid evidence snippet")
    if model_id not in snippet:
        raise ValueError("the evidence does not contain this exact model id")


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
        """Record that THIS owner made this id work. Publishes nothing.

        Returns whether this call created the row. Publication is a separate,
        deliberate act -- ``attest`` then two OTHER owners' ``confirm`` -- because
        "it worked for me" never established that an id is public. The threshold
        that used to publish from here was refuted in review: two genuinely
        different people can share one organisation's private selector.

        Idempotent per owner, so one owner's several universes add one row.
        """
        kind = _clean(source_kind, "source kind")
        model = _clean(model_id, "model id")
        owner = _clean(owner_user_id, "owner")
        when = _stamp(now)
        conn = self._connect(create=True)
        try:
            conn.execute(_EVIDENCE_SCHEMA)
            return conn.execute(
                "INSERT OR IGNORE INTO learned_model_evidence VALUES (?, ?, ?, ?)",
                (kind, model, owner, when),
            ).rowcount == 1
        finally:
            conn.close()

    def attest(self, *, source_kind: str, model_id: str, evidence_url: str,
               snippet: str, owner_user_id: str, now: datetime | None = None) -> str:
        """One owner's agent attests an id is a public release. Shares nothing yet.

        The platform makes NO outbound request. There is no platform LLM and no
        platform fetch (founder, 2026-09-26: "there is no platform llm, just other
        users"), so it checks only what is deterministic -- that the exact id string
        appears in the snippet the agent says it read at that URL -- and then waits
        for other owners' agents to reach the same conclusion independently.

        The snippet is CHECKED AND DISCARDED. It is agent-supplied free text, and
        free text in a store other users read is exactly the hole that bit rounds 1
        and 2 (an ARN, an email address). What is kept is the stripped URL and the id.

        Returns the item's state: "pending".
        """
        kind = _clean(source_kind, "source kind")
        model = _clean(model_id, "model id")
        owner = _clean(owner_user_id, "owner")
        url = _clean_evidence_url(evidence_url)
        _require_id_in_snippet(model, snippet)
        when = _stamp(now)
        conn = self._connect(create=True)
        try:
            conn.execute(_PENDING_SCHEMA)
            conn.execute(
                "INSERT OR IGNORE INTO learned_model_pending VALUES (?, ?, ?, ?, ?)",
                (kind, model, url, owner, when),
            )
            return "pending"
        finally:
            conn.close()

    def pending_items(self, source_kind: str | None = None) -> list[dict[str, str]]:
        """The opt-in work queue: what still needs independent confirmation.

        Readable by any owner's agent, so it carries NO owner data -- not who
        attested, not who has confirmed, not how many have. Just the source kind, the
        id, and the page to check. Users build the loop that reads this; there is
        deliberately no platform worker.
        """
        conn = self._connect(create=False)
        if conn is None:
            return []
        try:
            if not _has_table(conn, "learned_model_pending"):
                return []
            sql = (
                "SELECT p.source_kind, p.model_id, p.evidence_url "
                "FROM learned_model_pending p "
                "WHERE NOT EXISTS (SELECT 1 FROM learned_models m "
                "WHERE m.source_kind = p.source_kind AND m.model_id = p.model_id)"
            )
            params: tuple[str, ...] = ()
            if source_kind is not None:
                sql += " AND p.source_kind = ?"
                params = (_clean(source_kind, "source kind"),)
            if not _has_table(conn, "learned_models"):
                conn.execute(_SCHEMA)
            rows = conn.execute(sql + " ORDER BY p.source_kind, p.model_id", params).fetchall()
        finally:
            conn.close()
        return [{"source_kind": row["source_kind"], "model_id": row["model_id"],
                 "evidence_url": row["evidence_url"]} for row in rows]

    def confirm(self, *, source_kind: str, model_id: str, snippet: str,
                owner_user_id: str, confirming_model_id: str,
                now: datetime | None = None) -> str:
        """Another owner's agent independently confirms a pending attestation.

        Four things must hold, each refused with its own reason rather than a
        generic failure:

        * the id is actually pending;
        * the confirmer is NOT the attester -- their own universes never count
          toward their own attestation, or one owner could publish alone;
        * the exact id appears in the snippet THIS agent read (it fetched the
          stripped URL itself, or cited its own public source);
        * the model this confirming turn ran on is not superseded by a newer sibling
          the platform already knows -- the vendor-free reading of "smart recent big
          model". See ``model_class.superseded_by`` for why it is "not superseded"
          rather than "is the newest", which would deadlock an empty catalog.

        Returns "published" when this confirmation reached the threshold, else
        "pending".
        """
        from tinyassets.providers.model_class import superseded_by

        kind = _clean(source_kind, "source kind")
        model = _clean(model_id, "model id")
        owner = _clean(owner_user_id, "owner")
        confirming_model = _clean(confirming_model_id, "confirming model id")
        _require_id_in_snippet(model, snippet)
        when = _stamp(now)
        conn = self._connect(create=True)
        try:
            conn.execute(_SCHEMA)
            conn.execute(_EVIDENCE_SCHEMA)
            conn.execute(_PENDING_SCHEMA)
            conn.execute(_CONFIRMATION_SCHEMA)
            conn.execute("BEGIN IMMEDIATE")
            try:
                pending = conn.execute(
                    "SELECT evidence_url, owner_user_id FROM learned_model_pending "
                    "WHERE source_kind = ? AND model_id = ?", (kind, model),
                ).fetchone()
                if pending is None:
                    raise ValueError("no such pending model attestation")
                if pending["owner_user_id"] == owner:
                    raise PermissionError(
                        "an attestation cannot be confirmed by the owner who made it")
                known = [
                    LearnedModel(row["source_kind"], row["model_id"],
                                 row["first_verified_at"], row["evidence_url"])
                    for row in conn.execute(
                        "SELECT source_kind, model_id, first_verified_at, evidence_url "
                        "FROM learned_models WHERE source_kind = ?", (kind,))
                ]
                stale = superseded_by(confirming_model, known)
                if stale is not None:
                    raise PermissionError(
                        "a confirmation needs a current model; this one is superseded")
                conn.execute(
                    "INSERT OR IGNORE INTO learned_model_confirmations "
                    "VALUES (?, ?, ?, ?, ?)",
                    (kind, model, owner, confirming_model, when),
                )
                confirmations = conn.execute(
                    "SELECT COUNT(*) FROM learned_model_confirmations "
                    "WHERE source_kind = ? AND model_id = ?", (kind, model),
                ).fetchone()[0]
                state = "pending"
                if confirmations >= CONFIRMATIONS_REQUIRED:
                    earliest = conn.execute(
                        "SELECT MIN(first_verified_at) FROM learned_model_evidence "
                        "WHERE source_kind = ? AND model_id = ?", (kind, model),
                    ).fetchone()[0]
                    conn.execute(
                        "INSERT OR IGNORE INTO learned_models VALUES (?, ?, ?, ?)",
                        (kind, model, earliest or when, pending["evidence_url"]),
                    )
                    state = "published"
                conn.commit()
                return state
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
                "SELECT source_kind, model_id, first_verified_at, evidence_url "
                "FROM learned_models "
                "WHERE source_kind = ? ORDER BY first_verified_at, model_id",
                (kind,),
            ).fetchall()
        finally:
            conn.close()
        return [LearnedModel(row["source_kind"], row["model_id"], row["first_verified_at"],
                             row["evidence_url"])
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
