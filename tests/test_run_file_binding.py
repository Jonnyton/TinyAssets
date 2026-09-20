"""Declared exact file references bind atomically to an already admitted run."""

import copy

import pytest

from tests.test_run_file_capture import intake  # noqa: F401
from tinyassets import runs
from tinyassets.branches import BranchDefinition
from tinyassets.run_file_capture import capture_authoring_files
from tinyassets.storage import run_files


def fixture_run(intake):  # noqa: F811
    base, _, sources, _ = intake
    refs = capture_authoring_files(
        base,
        owner_id="owner",
        universe_id="u",
        label="binding",
        sources=sources,
    )
    branch = BranchDefinition.from_dict(
        {
            "branch_def_id": "branch",
            "name": "Files",
            "state_schema": [{"name": "files", "type": "list"}],
            "io_manifest": {
                "inputs": [
                    {
                        "name": "files",
                        "io_type": "file_bundle",
                        "max_count": 4,
                        "max_bytes": 4 * 1024 * 1024,
                    }
                ]
            },
        }
    )
    run_id = runs.create_run(
        base,
        branch_def_id="branch",
        thread_id="",
        inputs={"files": refs},
        actor="universe:u",
        owner_user_id="owner",
        queue_universe_id="u",
    )
    return base, run_id, refs, branch


def test_declared_binding_preserves_order_and_exact_metadata(intake):  # noqa: F811
    from tinyassets.run_file_binding import bind_declared_files, validate_bound_files

    base, run_id, refs, branch = fixture_run(intake)
    with runs._connect(base) as conn:
        conn.execute("BEGIN IMMEDIATE")
        bind_declared_files(
            conn,
            run_id=run_id,
            owner_id="owner",
            universe_id="u",
            branch=branch,
            inputs={"files": refs},
        )
        validate_bound_files(
            conn,
            run_id=run_id,
            owner_id="owner",
            universe_id="u",
            branch=branch,
            inputs={"files": refs},
        )
        assert [
            row[0] for row in conn.execute("SELECT file_id FROM run_file_bindings ORDER BY ordinal")
        ] == [ref["file_id"] for ref in refs]


@pytest.mark.parametrize("failure", ["metadata", "foreign", "released", "unbound"])
def test_invalid_file_bundle_never_partially_binds(intake, failure):  # noqa: F811
    from tinyassets.run_file_binding import bind_declared_files, validate_bound_files

    base, run_id, refs, branch = fixture_run(intake)
    inputs = {"files": copy.deepcopy(refs)}
    with runs._connect(base) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if failure == "metadata":
            inputs["files"][1]["filename"] = "changed"
        elif failure == "foreign":
            conn.execute(
                "UPDATE run_file_objects SET owner_id='other' WHERE file_id=?",
                (refs[1]["file_id"],),
            )
        elif failure == "released":
            conn.execute(
                "UPDATE run_file_objects SET state='released' WHERE file_id=?",
                (refs[1]["file_id"],),
            )
        function = validate_bound_files if failure == "unbound" else bind_declared_files
        with pytest.raises(run_files.FileCustodyRefused):
            function(
                conn, run_id=run_id, owner_id="owner", universe_id="u", branch=branch, inputs=inputs
            )
        assert conn.execute("SELECT COUNT(*) FROM run_file_bindings").fetchone()[0] == 0
