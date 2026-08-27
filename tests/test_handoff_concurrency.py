"""Handoff concurrency — duplicate concurrent submissions, compare-and-swap
lifecycle advance, and bounded fan-out across distinct identities.

Requirement source:
``openspec/changes/archive/2026-08-26-complete-independent-full-platform-targets/
specs/real-world-handoffs-and-outcomes/spec.md`` (tasks 5.1, 5.4).

Covered scenarios:
  - Concurrent same-output submissions race -> one owns adapter execution, the
    other returns shared pending/final evidence without a second push
  - A concurrent lifecycle advance loses its compare-and-swap rather than
    silently overwriting the winner

This is the concurrency half of the §14 proof. It is NOT the full §14 handoff
proof: that additionally requires webhook/poll overlap and a provider mix at 10x
launch volume, both of which belong to task 5.3's verification transport, which
this lane deferred.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from tinyassets.handoffs import adapters as handoff_adapters
from tinyassets.handoffs import service
from tinyassets.handoffs.adapters import HandoffResult
from tinyassets.handoffs.models import HandoffConflictError

DECLARATION = {
    "output_field": "submission",
    "adapter": "arxiv",
    "adapter_action": "submit",
    "destination": "arxiv.org/cs",
    "effect_class": "reversible",
    "outcome_kind": "preprint_submission",
}


def _branch(branch_def_id="b1"):
    return {
        "branch_def_id": branch_def_id,
        "name": f"Branch {branch_def_id}",
        "entry_point": "n1",
        "graph_nodes": [{"id": "n1", "node_def_id": "n1", "position": 0}],
        "node_defs": [{
            "node_id": "n1",
            "display_name": "Writer",
            "source_code": "def run(state):\n    return {}",
            "output_keys": ["submission"],
            "handoffs": [dict(DECLARATION)],
        }],
    }


class Env:
    def __init__(self, base, universe_dir, version):
        self.base = base
        self.universe_dir = universe_dir
        self.version = version
        self.owner = "account-alice"
        self.calls: list = []
        self.lock = threading.Lock()

    @property
    def version_id(self):
        return self.version.branch_version_id

    def new_run(self, thread_id: str, payload: dict) -> str:
        from tinyassets.runs import create_run, update_run_status

        run_id = create_run(
            self.base,
            branch_def_id="b1",
            thread_id=thread_id,
            inputs={},
            actor=self.owner,
            owner_user_id=self.owner,
        )
        update_run_status(
            self.base, run_id, status="completed", output={"submission": payload}
        )
        return run_id

    def execute(self, run_id: str):
        return service.execute(
            actor_id=self.owner,
            base_path=self.base,
            universe_dir=self.universe_dir,
            run_id=run_id,
            branch_version_id=self.version_id,
            output_field="submission",
        )


@pytest.fixture
def env(tmp_path, monkeypatch):
    base = tmp_path / "data"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))

    from tinyassets.branch_versions import publish_branch_version
    from tinyassets.storage.effector_consents import grant_consent
    from tinyassets.storage.external_write_receipts import initialize_receipts_db

    version = publish_branch_version(base, _branch(), publisher="account-alice")
    universe_dir = base / "u1"
    universe_dir.mkdir()
    grant_consent(
        universe_dir,
        sink="arxiv",
        destination="arxiv.org/cs",
        granted_by="account-alice",
    )
    # Create the receipts DB before any race starts. SQLite cannot convert a
    # fresh database to WAL while other connections hold it, and that conversion
    # is not covered by busy_timeout, so N threads touching a brand-new receipts
    # DB simultaneously can raise "database is locked" from the PRAGMA itself.
    # Warming it here keeps these tests measuring duplicate suppression rather
    # than a first-touch journal-mode race. The underlying fragility lives in the
    # landed store (external_write_receipts._connect) and is reported separately.
    initialize_receipts_db(universe_dir)
    return Env(base, universe_dir, version)


@pytest.fixture
def slow_adapter(env):
    """An adapter that holds the reservation long enough for a real overlap."""
    def _adapter(request):
        with env.lock:
            env.calls.append(request.effect_key)
        time.sleep(0.25)
        return HandoffResult(
            state="accepted",
            external_id=f"arXiv:{request.output_sha256[:12]}",
        )

    handoff_adapters.register_adapter("arxiv", _adapter)
    yield _adapter
    handoff_adapters.unregister_adapter("arxiv")


# ── Duplicate concurrent submissions ──────────────────────────────────────────

class TestDuplicateConcurrentSubmissions:
    def test_only_one_request_reaches_the_adapter(self, env, slow_adapter):
        run_id = env.new_run("t1", {"title": "Paper"})
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = [f.result() for f in [pool.submit(env.execute, run_id) for _ in range(6)]]
        assert len(env.calls) == 1, f"adapter invoked {len(env.calls)} times"
        assert len({key for key in env.calls}) == 1
        assert len(results) == 6

    def test_losers_receive_shared_evidence_not_an_error(self, env, slow_adapter):
        run_id = env.new_run("t2", {"title": "Paper"})
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = [f.result() for f in [pool.submit(env.execute, run_id) for _ in range(6)]]
        executed = [item for item in results if item.get("executed")]
        shared = [item for item in results if not item.get("executed")]
        assert len(executed) == 1
        assert shared, "every loser should return shared evidence"
        for item in shared:
            assert item["status"] in {"accepted", "in_flight"}
            assert item["effect_key"] == executed[0]["effect_key"]

    def test_exactly_one_handoff_row_and_one_outcome_survive(self, env, slow_adapter):
        run_id = env.new_run("t3", {"title": "Paper"})
        with ThreadPoolExecutor(max_workers=6) as pool:
            for future in [pool.submit(env.execute, run_id) for _ in range(6)]:
                future.result()
        listed = service.listing(actor_id=env.owner, base_path=env.base)
        evidence = service.outcome_evidence(actor_id=env.owner, base_path=env.base)
        assert listed["count"] == 1
        assert evidence["summary"]["total_claims"] == 1

    def test_the_transition_journal_has_no_duplicate_sequence(self, env, slow_adapter):
        run_id = env.new_run("t4", {"title": "Paper"})
        with ThreadPoolExecutor(max_workers=6) as pool:
            for future in [pool.submit(env.execute, run_id) for _ in range(6)]:
                future.result()
        handoff = service.listing(actor_id=env.owner, base_path=env.base)["handoffs"][0]
        detail = service.get(
            actor_id=env.owner, base_path=env.base, handoff_id=handoff["handoff_id"]
        )
        seqs = [item["seq"] for item in detail["transitions"]]
        assert seqs == sorted(set(seqs))
        assert seqs == list(range(1, len(seqs) + 1))


# ── Compare-and-swap ──────────────────────────────────────────────────────────

class TestCompareAndSwap:
    def test_a_stale_expected_state_loses_the_swap(self, env, slow_adapter):
        from tinyassets.handoffs.store import HandoffStore

        run_id = env.new_run("t5", {"title": "Paper"})
        env.execute(run_id)
        handoff = service.listing(actor_id=env.owner, base_path=env.base)["handoffs"][0]
        store = HandoffStore(env.base)
        store.initialize()
        with pytest.raises(HandoffConflictError):
            store.advance_handoff(
                handoff["handoff_id"],
                actor_id=env.owner,
                expected_state="reserved",  # already advanced to accepted
                to_state="submitted",
                evidence_source="test",
            )

    def test_concurrent_downgrades_produce_exactly_one_winner(self, env, slow_adapter):
        from tinyassets.handoffs.store import HandoffStore

        run_id = env.new_run("t6", {"title": "Paper"})
        env.execute(run_id)
        handoff = service.listing(actor_id=env.owner, base_path=env.base)["handoffs"][0]
        store = HandoffStore(env.base)
        store.initialize()

        def _downgrade():
            try:
                store.advance_handoff(
                    handoff["handoff_id"],
                    actor_id=env.owner,
                    expected_state="accepted",
                    to_state="orphaned",
                    evidence_source="test",
                )
                return "won"
            except HandoffConflictError:
                return "lost"

        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = [f.result() for f in [pool.submit(_downgrade) for _ in range(4)]]
        assert outcomes.count("won") == 1
        assert outcomes.count("lost") == 3


# ── Bounded fan-out across distinct identities ────────────────────────────────

class TestDistinctIdentityFanOut:
    def test_distinct_sources_each_execute_exactly_once(self, env, slow_adapter):
        """Twenty distinct handoffs concurrently: 20 effects, no cross-talk."""
        runs = [env.new_run(f"fan-{index}", {"title": f"Paper {index}"}) for index in range(20)]
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = [f.result() for f in [pool.submit(env.execute, run) for run in runs]]

        assert len(env.calls) == 20
        assert len(set(env.calls)) == 20, "each source must derive a distinct identity"
        assert all(item["status"] == "accepted" for item in results)
        assert service.listing(
            actor_id=env.owner, base_path=env.base, limit=200
        )["count"] == 20

    def test_each_distinct_identity_gets_its_own_outcome(self, env, slow_adapter):
        runs = [env.new_run(f"fan2-{index}", {"title": f"P{index}"}) for index in range(20)]
        with ThreadPoolExecutor(max_workers=10) as pool:
            for future in [pool.submit(env.execute, run) for run in runs]:
                future.result()
        summary = service.outcome_evidence(actor_id=env.owner, base_path=env.base)["summary"]
        assert summary["total_claims"] == 20
        assert summary["by_evidence_level"] == {"externally_verified": 20}

    def test_duplicate_and_distinct_traffic_mixed(self, env, slow_adapter):
        """Five identities, four requests each: five effects, twenty replies."""
        runs = [env.new_run(f"mix-{index}", {"title": f"M{index}"}) for index in range(5)]
        jobs = [run for run in runs for _ in range(4)]
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = [f.result() for f in [pool.submit(env.execute, run) for run in jobs]]

        assert len(results) == 20
        assert len(env.calls) == 5
        assert len(set(env.calls)) == 5
        assert service.listing(
            actor_id=env.owner, base_path=env.base, limit=200
        )["count"] == 5
