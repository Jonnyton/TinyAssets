"""A metadata launcher is not necessarily the process holding the RPC pipes."""

import asyncio
import os
import signal
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from tests.test_native_model_discovery import PROTOCOL, peer_script, row
from tinyassets.exceptions import ProviderError
from tinyassets.providers.native_jsonrpc_discovery import read_native_catalogue

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX process-group lifecycle")


@pytest.mark.parametrize("mode", ["success", "launcher_exited", "timeout", "cancel", "malformed"])
def test_launcher_and_inherited_pipe_child_are_cleaned_without_losing_result(tmp_path, mode):
    pid_file = tmp_path / "child.pid"
    child_code = peer_script([{"data": [row(isDefault=True)]}])
    if mode in {"timeout", "cancel"}:
        child_code = "import time; time.sleep(60)"
    elif mode == "malformed":
        child_code = "import time; print('not json', flush=True); time.sleep(60)"
    lock_file = tmp_path / "metadata.lock"
    child_code = (
        f"import fcntl; lock = open({str(lock_file)!r}, 'w'); "
        "fcntl.flock(lock, fcntl.LOCK_EX)\n" + child_code
    )
    launcher = f"""
import subprocess, sys
from pathlib import Path
child = subprocess.Popen([sys.executable, '-u', '-c', {child_code!r}])
Path({str(pid_file)!r}).write_text(str(child.pid))
if {mode!r} != 'launcher_exited':
    child.wait()
"""

    async def exercise():
        processes = []
        real_spawn = asyncio.create_subprocess_exec

        async def spawn(*args, **kwargs):
            assert kwargs["start_new_session"] is True
            process = await real_spawn(*args, **kwargs)
            processes.append(process)
            return process

        task = None
        try:
            with patch("asyncio.create_subprocess_exec", spawn):
                task = asyncio.create_task(read_native_catalogue(
                    [sys.executable, "-u", "-c", launcher], protocol=PROTOCOL,
                    env=os.environ.copy(), cwd=str(tmp_path),
                    spawn_kwargs={"start_new_session": False},
                    timeout=0.25 if mode == "timeout" else 5,
                ))
                if mode == "cancel":
                    async with asyncio.timeout(2):
                        while not pid_file.exists():
                            await asyncio.sleep(0.01)
                    task.cancel()
                async with asyncio.timeout(2):
                    if mode == "cancel":
                        with pytest.raises(asyncio.CancelledError):
                            await task
                    elif mode in {"timeout", "malformed"}:
                        with pytest.raises(
                            ProviderError, match="^native model discovery unavailable$",
                        ):
                            await task
                    else:
                        catalogue = await task
                        assert catalogue.default_model_id == "a-future-release"
                        assert len(catalogue.models) == 1
            assert processes[0].returncode is not None
            # A killed orphan can briefly remain a zombie awaiting init. It no
            # longer runs or retains pipes; don't confuse that with a live leak.
            child_pid = int(pid_file.read_text())
            status = Path(f"/proc/{child_pid}/stat")
            if status.exists():
                assert status.read_text().split(") ", 1)[1].startswith("Z")
            import fcntl
            with lock_file.open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            # Red-test cleanup targets only the two PIDs this fixture created.
            if pid_file.exists():
                try:
                    os.kill(int(pid_file.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            for process in processes:
                if process.returncode is None:
                    process.kill()
                await process.wait()
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())


@pytest.mark.parametrize("cancel", [False, True])
def test_cleanup_pipe_wait_is_bounded_and_cancellation_is_not_swallowed(cancel):
    from tinyassets.providers import native_jsonrpc_discovery as module

    async def exercise():
        waiting = asyncio.Event()

        async def stalled(*args):
            waiting.set()
            await asyncio.sleep(60)

        process = SimpleNamespace(
            pid=12345, returncode=0, stdin=Mock(),
            stdout=SimpleNamespace(read=stalled), wait=stalled, _transport=Mock(),
        )
        with patch.object(module.os, "killpg") as kill, patch.object(module, "_REAP_TIMEOUT", .05):
            task = asyncio.create_task(module._close_metadata_process(process))
            await waiting.wait()
            if cancel:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 1)
            else:
                await asyncio.wait_for(task, 1)
            kill.assert_called_once_with(12345, signal.SIGKILL)
            process.stdin.close.assert_called_once()
            process._transport.close.assert_called_once()
    asyncio.run(exercise())
