"""Borrow existing worker fences; never acquire another writer or barrier."""

import sqlite3

import pytest

from tests.test_conversation_run_admissions import HOME, OWNER, source_version
from tests.test_conversation_run_admissions import store as store
from tinyassets.runs import runs_db_path
from tinyassets.storage import conversation_run_admissions as cr
from tinyassets.storage import db_path


def test_supplied_scope_reads_source_without_opening_connection_or_committing(store, monkeypatch):
    version = source_version(store)
    with sqlite3.connect(db_path(store)) as author, sqlite3.connect(runs_db_path(store)) as runs:
        author.execute("BEGIN IMMEDIATE")
        runs.execute("BEGIN IMMEDIATE")
        monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: pytest.fail("new connection"))
        with cr.scope_from_transactions(
            store, owner=OWNER, universe=HOME, author_conn=author, runs_conn=runs,
        ) as scope:
            source = cr.authorize_source_in_transaction(
                runs, scope, version.branch_version_id, version.content_hash,
            )
            assert cr.load_source_in_transaction(runs, scope, source)["branch_def_id"]
            with pytest.raises(RuntimeError, match="nested"):
                with cr.runs_transaction(scope):
                    pass
        assert author.in_transaction and runs.in_transaction
        with pytest.raises(PermissionError, match="not active"):
            scope.check()


@pytest.mark.parametrize("wrong", ["author_path", "runs_path", "author_idle", "runs_idle"])
def test_supplied_scope_rejects_wrong_or_idle_connections(store, wrong):
    author_path = runs_db_path(store) if wrong == "author_path" else db_path(store)
    run_path = db_path(store) if wrong == "runs_path" else runs_db_path(store)
    with sqlite3.connect(author_path) as author, sqlite3.connect(run_path) as runs:
        # BEGIN avoids taking two write locks against the same deliberately wrong DB.
        if wrong != "author_idle":
            author.execute("BEGIN")
        if wrong != "runs_idle":
            runs.execute("BEGIN")
        with pytest.raises((PermissionError, RuntimeError)):
            with cr.scope_from_transactions(
                store, owner=OWNER, universe=HOME, author_conn=author, runs_conn=runs,
            ):
                pytest.fail("invalid connections admitted")


def test_supplied_scope_refuses_source_revoked_before_worker(store):
    version = source_version(store)
    with sqlite3.connect(db_path(store)) as author, sqlite3.connect(runs_db_path(store)) as runs:
        author.execute("UPDATE branch_definitions SET visibility='private'")
        runs.execute("BEGIN IMMEDIATE")
        with cr.scope_from_transactions(
            store, owner=OWNER, universe=HOME, author_conn=author, runs_conn=runs,
        ) as scope:
            with pytest.raises(PermissionError, match="source unavailable"):
                cr.authorize_source_in_transaction(
                    runs, scope, version.branch_version_id, version.content_hash,
                )


def test_supplied_scope_checks_current_home_without_recreating_it(store):
    with sqlite3.connect(db_path(store)) as author, sqlite3.connect(runs_db_path(store)) as runs:
        author.execute("DELETE FROM founder_home")
        runs.execute("BEGIN IMMEDIATE")
        (store / HOME).rmdir()
        with pytest.raises(RuntimeError, match="home changed"):
            with cr.scope_from_transactions(
                store, owner=OWNER, universe=HOME, author_conn=author, runs_conn=runs,
            ):
                pytest.fail("deleted home admitted")
        assert not (store / HOME).exists()
