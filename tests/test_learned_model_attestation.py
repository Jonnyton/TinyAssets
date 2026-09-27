"""Publication by attestation plus peer confirmation, with no platform egress.

The founder's final shape (2026-09-26), after the distinct-owner threshold was
refuted in review round 3 — two genuinely different people can share one
organisation's private selector, so "used by two owners" never implied "public":

* "there is no platform llm, just other users"
* "it still needs to be checked by other users' models with smart recent big models
  before it is shared more"

So: the owner's agent attests with a public page and the exact snippet it read; the
platform's only role is the deterministic check that the id appears in that snippet;
two OTHER owners' agents, each on a current model, independently confirm; then it
publishes. The platform makes no outbound request at any point, which is why there is
no SSRF question to answer here.
"""

from __future__ import annotations

import sqlite3

import pytest

from tinyassets.storage import db_path
from tinyassets.storage.learned_models import (
    COLUMNS,
    CONFIRMATIONS_REQUIRED,
    LearnedModelCatalog,
)

ID = "claude-fable-5-1"
#: An account-bearing selector. It reaches no public page, so no agent can attest it
#: and it can never be published — the property the threshold could not deliver.
ARN = ("arn:aws:bedrock:us-east-1:123456789012:inference-profile/"
       "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
PAGE = "https://docs.example.com/models"
CURRENT = "vendor-line-9-1"


@pytest.fixture
def catalog(tmp_path):
    return LearnedModelCatalog(tmp_path)


def _attested(catalog, model_id=ID, owner="alice", url=PAGE):
    catalog.record(source_kind="subscription", model_id=model_id, owner_user_id=owner)
    return catalog.attest(
        source_kind="subscription", model_id=model_id, evidence_url=url,
        snippet=f"Announcing {model_id}, generally available today.",
        owner_user_id=owner,
    )


def _published(catalog):
    return [row.model_id for row in catalog.for_source_kind("subscription")]


# ---------------------------------------------------------------------------
# The staged spread.
# ---------------------------------------------------------------------------


def test_an_attestation_alone_shares_nothing(catalog):
    assert _attested(catalog) == "pending"
    assert _published(catalog) == [], "an attestation is a claim, not a publication"
    # It is on the owner's own list, and visible to nobody else.
    assert [row.model_id for row in catalog.evidence_ids("subscription", "alice")] == [ID]
    assert catalog.evidence_ids("subscription", "bob") == []


def test_two_other_owners_confirming_publishes_it(catalog):
    _attested(catalog)
    assert catalog.confirm(source_kind="subscription", model_id=ID, snippet=f"{ID} released",
                           owner_user_id="bob", confirming_model_id=CURRENT) == "pending"
    assert _published(catalog) == [], "one confirmation is below the bar"
    assert catalog.confirm(source_kind="subscription", model_id=ID, snippet=f"{ID} released",
                           owner_user_id="carol", confirming_model_id=CURRENT) == "published"
    assert _published(catalog) == [ID]
    # The published row carries the page that proved it, and nothing about people.
    row = catalog.for_source_kind("subscription")[0]
    assert row.evidence_url == PAGE
    assert CONFIRMATIONS_REQUIRED == 2


def test_the_attester_can_never_confirm_their_own_attestation(catalog):
    """Otherwise one owner publishes alone and the whole stage is decorative."""
    _attested(catalog, owner="alice")
    with pytest.raises(PermissionError, match="owner who made it"):
        catalog.confirm(source_kind="subscription", model_id=ID, snippet=ID,
                        owner_user_id="alice", confirming_model_id=CURRENT)
    # Not even repeatedly, and not by reaching the count another way.
    for _ in range(3):
        with pytest.raises(PermissionError):
            catalog.confirm(source_kind="subscription", model_id=ID, snippet=ID,
                            owner_user_id="alice", confirming_model_id=CURRENT)
    assert _published(catalog) == []


def test_one_confirmer_confirming_repeatedly_counts_once(catalog):
    _attested(catalog)
    for _ in range(4):
        assert catalog.confirm(source_kind="subscription", model_id=ID, snippet=ID,
                               owner_user_id="bob",
                               confirming_model_id=CURRENT) == "pending"
    assert _published(catalog) == []


def test_confirming_something_nobody_attested_is_refused(catalog):
    with pytest.raises(ValueError, match="no such pending"):
        catalog.confirm(source_kind="subscription", model_id=ID, snippet=ID,
                        owner_user_id="bob", confirming_model_id=CURRENT)


# ---------------------------------------------------------------------------
# The deterministic check, which is all the platform does.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "snippet",
    [
        "Announcing claude-fable-5, generally available.",   # a PREFIX, not the id
        "Announcing CLAUDE-FABLE-5-1.",                      # case differs
        "nothing about any model",
        "",
        "   ",
        "x" * 20001,                                         # unbounded input
    ],
)
def test_evidence_that_does_not_contain_the_exact_id_is_refused(catalog, snippet):
    catalog.record(source_kind="subscription", model_id=ID, owner_user_id="alice")
    with pytest.raises(ValueError):
        catalog.attest(source_kind="subscription", model_id=ID, evidence_url=PAGE,
                       snippet=snippet, owner_user_id="alice")
    assert catalog.pending_items() == []


def test_the_snippet_is_checked_and_never_stored(catalog):
    """It is agent-supplied free text, and free text is what leaked in rounds 1-2."""
    secret = f"{ID} — internal note: contact alice@example.com about the private tier"
    catalog.record(source_kind="subscription", model_id=ID, owner_user_id="alice")
    catalog.attest(source_kind="subscription", model_id=ID, evidence_url=PAGE,
                   snippet=secret, owner_user_id="alice")
    with sqlite3.connect(db_path(catalog.base_path)) as conn:
        dump = "\n".join(conn.iterdump()).lower()
    assert "alice@example.com" not in dump, "the snippet reached storage"
    assert "internal note" not in dump


@pytest.mark.parametrize(
    "url",
    [
        "http://docs.example.com/models",                 # not https
        "https://user:pw@docs.example.com/models",        # credentials
        "https:///models",                                # no host
        "ftp://docs.example.com/models",
        "not a url",
        "",
        "https://docs.example.com/" + "x" * 3000,         # unbounded
    ],
)
def test_an_evidence_url_that_is_not_a_public_https_page_is_refused(catalog, url):
    catalog.record(source_kind="subscription", model_id=ID, owner_user_id="alice")
    with pytest.raises(ValueError):
        catalog.attest(source_kind="subscription", model_id=ID, evidence_url=url,
                       snippet=f"Announcing {ID}", owner_user_id="alice")


def test_the_stored_url_is_stripped_of_query_and_fragment(catalog):
    """A shared table must not carry an agent-supplied query string.

    Same class of hole as the ARN and the email address in rounds 1 and 2 — and it
    would also let a tracking parameter ride along into every other user's view.
    """
    _attested(catalog, url="https://docs.example.com/models?utm_source=agent&u=alice#sec-3")
    assert catalog.pending_items()[0]["evidence_url"] == PAGE
    for who in ("bob", "carol"):
        catalog.confirm(source_kind="subscription", model_id=ID, snippet=ID,
                        owner_user_id=who, confirming_model_id=CURRENT)
    assert catalog.for_source_kind("subscription")[0].evidence_url == PAGE
    with sqlite3.connect(db_path(catalog.base_path)) as conn:
        dump = "\n".join(conn.iterdump())
    assert "utm_source" not in dump and "u=alice" not in dump


# ---------------------------------------------------------------------------
# "Smart recent big model", derived rather than named.
# ---------------------------------------------------------------------------


def test_a_superseded_confirming_model_cannot_confirm(catalog):
    """The vendor-free reading: not superseded by a newer sibling already published."""
    # Publish a newer sibling of the confirmer's model first.
    _attested(catalog, model_id="vendor-line-9-2", owner="dave")
    for who in ("erin", "frank"):
        catalog.confirm(source_kind="subscription", model_id="vendor-line-9-2",
                        snippet="vendor-line-9-2", owner_user_id=who,
                        confirming_model_id="bootstrap-model-1")
    assert "vendor-line-9-2" in _published(catalog)

    _attested(catalog)
    with pytest.raises(PermissionError, match="superseded"):
        catalog.confirm(source_kind="subscription", model_id=ID, snippet=ID,
                        owner_user_id="bob", confirming_model_id="vendor-line-9-1")
    # The newer one confirms fine, so this is not simply refusing everything.
    assert catalog.confirm(source_kind="subscription", model_id=ID, snippet=ID,
                           owner_user_id="bob",
                           confirming_model_id="vendor-line-9-2") == "pending"


def test_an_empty_catalog_does_not_deadlock_the_first_confirmer(catalog):
    """The bootstrap case, which "must be in the published newest set" would fail.

    With nothing published, no model is in any newest set, so that reading would
    refuse every confirmation forever and the catalog could never fill. "Not
    superseded" is monotone instead: nothing known is newer, so a first confirmer
    qualifies, and the bar rises on its own as the catalog grows.
    """
    assert catalog.for_source_kind("subscription") == []
    _attested(catalog)
    assert catalog.confirm(source_kind="subscription", model_id=ID, snippet=ID,
                           owner_user_id="bob", confirming_model_id="anything-1") == "pending"


# ---------------------------------------------------------------------------
# The opt-in queue, and the floor.
# ---------------------------------------------------------------------------


def test_the_queue_carries_the_work_and_no_owner_data(catalog):
    """Any owner's agent may read it, so it must say nothing about people.

    Not who attested, not who has confirmed, not how many have — a count of
    confirmers is a population fact about users.
    """
    _attested(catalog, owner="alice")
    catalog.confirm(source_kind="subscription", model_id=ID, snippet=ID,
                    owner_user_id="bob", confirming_model_id=CURRENT)
    items = catalog.pending_items()
    assert items == [{"source_kind": "subscription", "model_id": ID, "evidence_url": PAGE}]
    flat = repr(items)
    for who in ("alice", "bob", "carol", "owner", "confirm", "count"):
        assert who not in flat.lower(), who


def test_a_published_item_leaves_the_queue(catalog):
    _attested(catalog)
    for who in ("bob", "carol"):
        catalog.confirm(source_kind="subscription", model_id=ID, snippet=ID,
                        owner_user_id=who, confirming_model_id=CURRENT)
    assert catalog.pending_items() == [], "finished work must not stay on the queue"


def test_the_shared_table_still_carries_no_user_data(catalog):
    _attested(catalog)
    for who in ("bob", "carol"):
        catalog.confirm(source_kind="subscription", model_id=ID, snippet=ID,
                        owner_user_id=who, confirming_model_id=CURRENT)
    with sqlite3.connect(db_path(catalog.base_path)) as conn:
        rows = conn.execute("SELECT * FROM learned_models").fetchall()
        columns = [row[1] for row in conn.execute("PRAGMA table_info(learned_models)")]
    assert tuple(columns) == COLUMNS
    stored = " ".join(str(v) for row in rows for v in row).lower()
    for secret in ("alice", "bob", "carol", "owner", "universe", "confirm"):
        assert secret not in stored, secret


def test_the_private_selector_can_never_be_published(catalog):
    """The whole point, restated on the final shape.

    An account-bearing ARN appears on no public page, so no honest agent can attest
    it and no confirmer can find it. It stays on its owner's list forever.
    """
    catalog.record(source_kind="subscription", model_id=ARN, owner_user_id="alice")
    # An attestation naming it cannot pass the check unless the snippet contains it,
    # and a snippet that contains it is not a public page — but even granting the
    # agent that, the peer stage is what stops it: no other owner can find it.
    catalog.attest(source_kind="subscription", model_id=ARN, evidence_url=PAGE,
                   snippet=f"internal runbook mentions {ARN}", owner_user_id="alice")
    assert _published(catalog) == []
    # One other owner who cannot actually find a public page for it simply never
    # confirms, so the item sits pending and shared with nobody.
    assert catalog.pending_items()[0]["model_id"] == ARN
    assert catalog.for_source_kind("subscription") == []
    assert [row.model_id for row in catalog.evidence_ids("subscription", "alice")] == [ARN]


def test_every_owner_bearing_table_is_reachable_by_the_deletion_sweep(catalog):
    """Named owner_user_id so the by-column sweep finds them.

    A semantically nicer `attested_by` / `confirming_owner` was silently skipped by
    account deletion, which matches PRINCIPAL_KEYS by NAME — it would have left a
    departed owner's attestations and confirmations behind.
    """
    from tinyassets.account_deletion import PRINCIPAL_KEYS
    from tinyassets.scoped_reset import MAIN_DB_TABLE_CLASSIFICATIONS

    _attested(catalog)
    catalog.confirm(source_kind="subscription", model_id=ID, snippet=ID,
                    owner_user_id="bob", confirming_model_id=CURRENT)
    with sqlite3.connect(db_path(catalog.base_path)) as conn:
        for table in ("learned_model_pending", "learned_model_confirmations",
                      "learned_model_evidence"):
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            assert columns & set(PRINCIPAL_KEYS), f"{table} would be orphaned on delete"
            assert MAIN_DB_TABLE_CLASSIFICATIONS.get(table) == "preserve", table
        shared = {row[1] for row in conn.execute("PRAGMA table_info(learned_models)")}
    assert not shared & set(PRINCIPAL_KEYS), "the shared table must have no owner column"
