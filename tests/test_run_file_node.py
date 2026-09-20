"""Node reads need a live pinned run and declared actual incoming references."""

import base64
from dataclasses import replace

import pytest

from tests.test_run_file_reader import bound, intake  # noqa: F401
from tinyassets import runs
from tinyassets.authoring.io import IODeclaration
from tinyassets.run_file_node import NodeFileSource, read_node_file
from tinyassets.storage import run_files


def source(run_id):
    return NodeFileSource(
        "owner", "u", "owner", run_id, "branch", "entry",
        (IODeclaration("files", "file_bundle", "input", max_count=4),),
    )


def read(base, run_id, refs, **changes):
    kwargs = dict(
        source=source(run_id),
        incoming={"files": refs},
        file_id=refs[0]["file_id"],
        offset=0,
        count=11,
        should_cancel=lambda: False,
    )
    kwargs.update(changes)
    return read_node_file(base, **kwargs)


def test_pinned_running_node_reads_exact_incoming_file(bound):  # noqa: F811
    base, run_id, refs, bodies = bound
    with runs._managed_execution_scope(base, run_id):
        runs.update_run_status(base, run_id, status="running")
        with runs._execution_use_scope():
            value = read(base, run_id, refs)
    assert base64.b64decode(value["bytes_base64"]) == bodies[0][:11]


@pytest.mark.parametrize(
    "bad", ["no_pin", "no_field", "wrong_run", "wrong_actor", "metadata", "cancel"]
)
def test_guessed_or_revoked_node_context_cannot_read(bound, bad):  # noqa: F811
    base, run_id, refs, _ = bound
    changes = {}
    if bad == "no_field":
        changes["source"] = replace(source(run_id), fields=())
    elif bad == "wrong_run":
        changes["source"] = replace(source(run_id), run_id="foreign")
    elif bad == "wrong_actor":
        changes["source"] = replace(source(run_id), actor="other")
    elif bad == "metadata":
        changes["incoming"] = {"files": [{**refs[0], "filename": "forged"}]}
    elif bad == "cancel":
        changes["should_cancel"] = lambda: True
    with runs._managed_execution_scope(base, run_id):
        runs.update_run_status(base, run_id, status="running")
        if bad == "no_pin":
            with pytest.raises((run_files.FileCustodyRefused, RuntimeError)):
                read(base, run_id, refs)
        else:
            with runs._execution_use_scope():
                with pytest.raises(run_files.FileCustodyRefused):
                    read(base, run_id, refs, **changes)
