"""Reserve-only direct/version intake binds exact files before one actual start."""

import hashlib

import pytest

from tests.test_run_file_node_rpc import intake, rpc  # noqa: F401
from tinyassets import daemon_server, runs
from tinyassets.branch_versions import publish_branch_version
from tinyassets.run_input_direct import reserve_direct_run
from tinyassets.run_input_origin import OriginHeld
from tinyassets.run_input_origins import dispatch_initial_run
from tinyassets.storage import _connect as author_connect
from tinyassets.storage.run_files import FileCustodyRefused


@pytest.fixture
def direct_files(rpc):  # noqa: F811
    base, branch, refs, bodies = rpc
    with author_connect(base) as conn:
        conn.execute("INSERT INTO founder_home(founder_sub,universe_id,created_at) "
                     "VALUES('owner','u',1)")
    daemon_server.save_branch_definition(base, branch_def=branch.to_dict())
    return base, branch, refs, bodies


def reserve(base, branch, refs, **kwargs):
    return reserve_direct_run(
        base, owner_id="owner", universe_id="u", branch=branch, inputs={"files": refs},
        recursion_limit=50, **kwargs,
    )


@pytest.mark.parametrize("versioned", [False, True])
def test_real_reservation_then_single_static_dispatch_reads_exact_bundle(direct_files, versioned):
    base, branch, refs, bodies = direct_files
    version = (publish_branch_version(base, branch.to_dict(), publisher="owner")
               if versioned else None)
    run_id = reserve(base, branch, refs,
                     branch_version_id=version.branch_version_id if version else None)
    with runs._connect(base) as conn:
        row = conn.execute(
            "SELECT * FROM run_input_admissions WHERE run_id=?", (run_id,),
        ).fetchone()
        assert row["execution_started_at"] is None and row["claim_token"] is None
        assert row["origin_kind"] == "direct" and row["origin_version"] == 1
        assert conn.execute("SELECT COUNT(*) FROM run_file_bindings WHERE run_id=?",
                            (run_id,)).fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM run_lineage WHERE run_id=?",
                            (run_id,)).fetchone()[0] == 0
    dispatch_initial_run(base, run_id=run_id)
    runs.wait_for(run_id, timeout=30)
    outcome = runs.get_run(base, run_id)
    assert outcome["status"] == "completed", outcome["error"]
    digests = [hashlib.sha256(body).hexdigest() for body in bodies]
    assert outcome["output"]["first"] == outcome["output"]["second"] == digests


def test_forged_reference_rolls_back_run_envelope_and_all_bindings(direct_files):
    base, branch, refs, _ = direct_files
    with pytest.raises(FileCustodyRefused):
        reserve(base, branch, [refs[0], {**refs[1], "filename": "relabeled"}])
    with runs._connect(base) as conn:
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
        # Additive schema participates in the rollback too; either absent or empty.
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='run_input_admissions'").fetchone():
            assert conn.execute("SELECT COUNT(*) FROM run_input_admissions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM run_file_bindings").fetchone()[0] == 0


@pytest.mark.parametrize("kwargs", [{"invocation_depth": 1}, {"invocation_depth": True},
                                   {"parent": object()}])
def test_nested_origin_cannot_be_stamped_direct(direct_files, kwargs):
    base, branch, refs, _ = direct_files
    with pytest.raises(OriginHeld, match="depth_zero"):
        reserve(base, branch, refs, **kwargs)
