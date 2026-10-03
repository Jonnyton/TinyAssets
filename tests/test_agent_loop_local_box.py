"""The box tools against the real local box driver (``tinyassets.boxes.local``).

POSIX only: the local driver runs commands on the host in their own process
group. This is the contract test the scripted ``FakeBox`` cannot be: real
``start_exec``/``stream``/``cancel`` shapes, real op_id idempotency, and the
box enforcing its own wall clock.
"""

from __future__ import annotations

import asyncio
import shutil
import sys

import pytest

from tinyassets.agent_loop.box_tools import BoxExecutor, BoxTools
from tinyassets.boxes import BOX_ROOT, BoxAuthError

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("flock") is None
    or shutil.which("sha256sum") is None,
    reason="the local box driver and the tool scripts need a POSIX host",
)


@pytest.fixture
def provider(tmp_path):
    from tinyassets.boxes.local import LocalBoxProvider

    owners = {"cc-alice": "alice", "cc-bob": "bob"}
    box = LocalBoxProvider(boxes_root=tmp_path / "boxes", state_dir=tmp_path / "state",
                           owner_of=owners.get, allow_unisolated=True)
    yield box
    box.close()


def _tools(provider, cc="cc-alice", account="alice", turn="t1"):
    handle = provider.bind(cc, account_id=account, turn_id=turn)
    return BoxTools(BoxExecutor(provider, handle), root=BOX_ROOT)


def run(coro):
    return asyncio.run(coro)


def test_write_read_edit_bash_round_trip_in_a_real_box(provider):
    t = _tools(provider)
    assert run(t.write("t1:1:1", "notes/plan.md", "one\ntwo\n")) == (
        "wrote 8 bytes to /cc/notes/plan.md")
    assert run(t.read("t1:1:2", "notes/plan.md", offset=2)) == "two\n"
    assert run(t.edit("t1:1:3", "notes/plan.md", "two", "three")) == "edited /cc/notes/plan.md"
    assert run(t.bash("t1:1:4", "cat notes/plan.md")) == "one\nthree\n[exit code 0]"


def test_the_same_op_id_never_runs_twice(provider):
    t = _tools(provider)
    run(t.bash("t1:2:1", "echo x >> count.txt"))
    run(t.bash("t1:2:1", "echo x >> count.txt"))
    assert run(t.bash("t1:2:2", "wc -l < count.txt")).startswith("1\n")


def test_the_box_kills_a_command_past_its_wall_clock(provider):
    result = run(_tools(provider).bash("t1:3:1", "sleep 30", timeout=1))
    assert result.endswith("[killed: ran longer than 1s]")


def test_a_cancelled_turn_kills_the_command_in_the_box(provider):
    t = _tools(provider)

    async def scenario():
        task = asyncio.ensure_future(t.bash("t1:4:1", "sleep 30; echo late > late.txt"))
        await asyncio.sleep(1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    run(scenario())
    # The process group was killed: the command never reached its write.
    assert "no such file" in run(t.read("t1:4:2", "late.txt"))


def test_one_owner_cannot_bind_another_owners_box(provider):
    with pytest.raises(BoxAuthError):
        provider.bind("cc-bob", account_id="alice", turn_id="t1")
