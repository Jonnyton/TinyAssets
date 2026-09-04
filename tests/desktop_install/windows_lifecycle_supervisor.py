from __future__ import annotations

import argparse
import ctypes
import faulthandler
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, TextIO

_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_CHILD_BOOTSTRAP = (
    "import subprocess, sys; "
    "signal = sys.stdin.buffer.read(1); "
    "raise SystemExit(125 if signal != b'1' else "
    "subprocess.call(sys.argv[1:], stdin=subprocess.DEVNULL))"
)


class _JobObjectBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _JobObjectExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobObjectBasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _WindowsKillOnCloseJob:
    """Own a Windows process tree and kill every survivor when closed."""

    def __init__(self) -> None:
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        self._kernel32.SetInformationJobObject.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        self._kernel32.AssignProcessToJobObject.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self._kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self._handle = self._kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _JobObjectExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self._kernel32.SetInformationJobObject(
            self._handle,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(error)

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        process_handle = ctypes.c_void_p(int(process._handle))  # type: ignore[attr-defined]
        if not self._kernel32.AssignProcessToJobObject(self._handle, process_handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


def _new_process_job() -> _WindowsKillOnCloseJob | None:
    if os.name != "nt":
        return None
    return _WindowsKillOnCloseJob()


def _bounded_int(minimum: int, maximum: int):
    def parse(value: str) -> int:
        parsed = int(value)
        if not minimum <= parsed <= maximum:
            raise argparse.ArgumentTypeError(f"must be between {minimum} and {maximum}")
        return parsed

    return parse


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Supervise the unsigned Windows installer lifecycle."
    )
    parser.add_argument("--installer", required=True, type=Path)
    parser.add_argument(
        "--lifecycle-script",
        type=Path,
        default=Path(__file__).with_name("windows_lifecycle.ps1"),
    )
    parser.add_argument("--phase-timeout-seconds", type=_bounded_int(1, 900), default=180)
    parser.add_argument("--total-timeout-seconds", type=_bounded_int(1, 3600), default=300)
    parser.add_argument(
        "--hard-timeout-seconds",
        type=_bounded_int(1, 3600),
        default=420,
        help=(
            "whole-supervisor deadline; dumps every thread stack and exits if "
            "any supervisor operation outlives the child-wait budget"
        ),
    )
    parser.add_argument("--cleanup-timeout-seconds", type=_bounded_int(1, 60), default=10)
    parser.add_argument(
        "--max-capture-bytes-per-stream",
        type=_bounded_int(1024, 10_485_760),
        default=262_144,
    )
    return parser.parse_args()


def _powershell() -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable is None:
        raise RuntimeError("PowerShell is required for the Windows lifecycle")
    return executable


def _replay_capture(
    capture_path: Path,
    *,
    capture_writer: BinaryIO,
    name: str,
    destination: TextIO,
    max_bytes: int,
    observed_bytes: int | None = None,
) -> None:
    capture_writer.flush()
    initial_observed_bytes = os.fstat(capture_writer.fileno()).st_size
    replay_bytes = min(initial_observed_bytes, max_bytes)
    with capture_path.open("rb") as capture_reader:
        data = capture_reader.read(replay_bytes)
    observed_bytes = max(
        observed_bytes or 0,
        initial_observed_bytes,
        os.fstat(capture_writer.fileno()).st_size,
    )
    destination.write(data.decode("utf-8", errors="replace"))
    destination.flush()
    if observed_bytes > len(data):
        print(
            "::warning title=Windows lifecycle capture::"
            f"{name} capture truncated; replay cap {max_bytes} bytes; "
            f"observed at least {observed_bytes} bytes",
            flush=True,
        )


def _drain_stream(
    stream: BinaryIO,
    *,
    capture_writer: BinaryIO,
    max_bytes: int,
) -> int:
    """Drain a child stream while storing at most ``max_bytes`` on disk."""
    observed_bytes = 0
    captured_bytes = 0
    while chunk := stream.read(65_536):
        observed_bytes += len(chunk)
        remaining_bytes = max_bytes - captured_bytes
        if remaining_bytes > 0:
            captured = chunk[:remaining_bytes]
            capture_writer.write(captured)
            captured_bytes += len(captured)
    capture_writer.flush()
    return observed_bytes


def _checkpoint(stage: str) -> None:
    print(
        f"::notice title=Windows lifecycle checkpoint::stage={stage}",
        flush=True,
    )


@contextmanager
def _capture_file() -> Iterator[tuple[Path, BinaryIO]]:
    capture_writer = tempfile.NamedTemporaryFile(
        mode="w+b",
        prefix="tinyassets-lifecycle-",
        suffix=".capture",
        delete=False,
    )
    capture_path = Path(capture_writer.name)
    try:
        yield capture_path, capture_writer
    finally:
        capture_writer.close()
        try:
            capture_path.unlink(missing_ok=True)
        except OSError as exc:
            print(
                "::warning title=Windows lifecycle capture cleanup::"
                f"temporary capture could not be removed: {exc}",
                flush=True,
            )


def _terminate_tree(process: subprocess.Popen[bytes], *, cleanup_timeout_seconds: int) -> None:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    cleanup: subprocess.Popen[bytes] | None = None
    _checkpoint("cleanup.taskkill.started")
    try:
        cleanup = subprocess.Popen(
            ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        cleanup.wait(timeout=cleanup_timeout_seconds)
        if cleanup.returncode != 0 and process.poll() is None:
            print(
                "::warning title=Windows lifecycle cleanup::"
                f"taskkill exited {cleanup.returncode} for child PID {process.pid}",
                flush=True,
            )
    except subprocess.TimeoutExpired:
        if cleanup is not None:
            try:
                cleanup.kill()
            except OSError:
                pass
        print(
            "::warning title=Windows lifecycle cleanup::"
            f"taskkill exceeded {cleanup_timeout_seconds} seconds for child PID "
            f"{process.pid}",
            flush=True,
        )
    except OSError as exc:
        print(
            "::warning title=Windows lifecycle cleanup::"
            f"taskkill failed for child PID {process.pid}: {exc}",
            flush=True,
        )

    if process.poll() is None:
        try:
            process.kill()
        except OSError as exc:
            print(
                "::warning title=Windows lifecycle cleanup::"
                f"root kill failed for child PID {process.pid}: {exc}",
                flush=True,
            )
    _checkpoint("cleanup.root_wait.started")
    try:
        process.wait(timeout=cleanup_timeout_seconds)
    except subprocess.TimeoutExpired:
        print(
            "::warning title=Windows lifecycle cleanup::"
            f"child PID {process.pid} survived bounded cleanup",
            flush=True,
        )
    _checkpoint("cleanup.finished")


def _run(args: argparse.Namespace) -> int:
    try:
        installer = args.installer.resolve(strict=True)
        lifecycle = args.lifecycle_script.resolve(strict=True)
        powershell = _powershell()
    except (OSError, RuntimeError) as exc:
        print(f"Windows lifecycle supervisor preflight failed: {exc}", file=sys.stderr)
        return 1

    command = [
        powershell,
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(lifecycle),
        "-Installer",
        str(installer),
        "-PhaseTimeoutSeconds",
        str(args.phase_timeout_seconds),
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )

    try:
        process_job = _new_process_job()
    except OSError as exc:
        print(
            f"Windows lifecycle process-tree guard failed to start: {exc}",
            file=sys.stderr,
        )
        return 1

    with (
        _capture_file() as (stdout_capture_path, stdout_capture_writer),
        _capture_file() as (stderr_capture_path, stderr_capture_writer),
    ):
        try:
            process = subprocess.Popen(
                [sys.executable, "-c", _CHILD_BOOTSTRAP, *command],
                # The bootstrap cannot spawn PowerShell until its parent has
                # assigned it to the kill-on-close Job Object.  This closes
                # the create/assign race in which a fast child could escape.
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
            )
        except OSError as exc:
            if process_job is not None:
                process_job.close()
            print(f"Windows lifecycle child failed to start: {exc}", file=sys.stderr)
            return 1

        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        capture_observed: dict[str, int] = {}
        capture_errors: dict[str, str] = {}

        def drain(
            name: str,
            stream: BinaryIO,
            capture_writer: BinaryIO,
        ) -> None:
            try:
                capture_observed[name] = _drain_stream(
                    stream,
                    capture_writer=capture_writer,
                    max_bytes=args.max_capture_bytes_per_stream,
                )
            except OSError as exc:
                capture_errors[name] = str(exc)
                print(
                    f"::warning title=Windows lifecycle capture::{name} drain stopped: {exc}",
                    flush=True,
                )

        capture_streams = {
            "stdout": (
                process.stdout,
                stdout_capture_path,
                stdout_capture_writer,
                sys.stdout,
            ),
            "stderr": (
                process.stderr,
                stderr_capture_path,
                stderr_capture_writer,
                sys.stderr,
            ),
        }
        capture_threads = {
            name: threading.Thread(
                target=drain,
                args=(name, stream, capture_writer),
                name=f"windows-lifecycle-{name}-drain",
                daemon=True,
            )
            for name, (
                stream,
                _path,
                capture_writer,
                _destination,
            ) in capture_streams.items()
        }
        for thread in capture_threads.values():
            thread.start()

        try:
            if process_job is not None:
                process_job.assign(process)
        except OSError as exc:
            print(
                f"Windows lifecycle process-tree guard failed to attach: {exc}",
                file=sys.stderr,
            )
            _terminate_tree(process, cleanup_timeout_seconds=args.cleanup_timeout_seconds)
            if process_job is not None:
                process_job.close()
            for stream in (process.stdout, process.stderr):
                try:
                    stream.close()
                except OSError:
                    pass
            for thread in capture_threads.values():
                thread.join(timeout=args.cleanup_timeout_seconds)
            return 1

        try:
            process.stdin.write(b"1")
            process.stdin.flush()
            process.stdin.close()
        except OSError as exc:
            print(
                f"Windows lifecycle bootstrap failed to release: {exc}",
                file=sys.stderr,
            )
            _terminate_tree(process, cleanup_timeout_seconds=args.cleanup_timeout_seconds)
            if process_job is not None:
                process_job.close()
            return 1

        print(
            "::notice title=Windows lifecycle supervisor::"
            f"child PID {process.pid}; total deadline "
            f"{args.total_timeout_seconds} seconds",
            flush=True,
        )
        timed_out = False
        _checkpoint("child.wait.started")
        try:
            return_code = process.wait(timeout=args.total_timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _checkpoint("child.wait.timed_out")
            print(
                "::error title=Windows lifecycle total timeout::"
                f"child PID {process.pid} exceeded {args.total_timeout_seconds} seconds",
                flush=True,
            )
            _checkpoint("cleanup.started")
            _terminate_tree(process, cleanup_timeout_seconds=args.cleanup_timeout_seconds)
            return_code = 1

        # Closing a kill-on-close Job Object terminates descendants that
        # outlived the PowerShell root and closes every inherited pipe writer.
        # Only after this boundary is closed may the bounded drains wait for
        # EOF; capture storage itself is capped by _drain_stream.
        if process_job is not None:
            process_job.close()
        _checkpoint("process_tree.closed")

        for name, (
            stream,
            capture_path,
            capture_writer,
            destination,
        ) in capture_streams.items():
            _checkpoint(f"capture.{name}.started")
            thread = capture_threads[name]
            thread.join(timeout=args.cleanup_timeout_seconds)
            if thread.is_alive():
                try:
                    stream.close()
                except OSError:
                    pass
                thread.join(timeout=args.cleanup_timeout_seconds)
            if thread.is_alive():
                print(
                    "::error title=Windows lifecycle capture::"
                    f"{name} drain survived bounded cleanup",
                    flush=True,
                )
                # The process tree is already closed and the pipe handle was
                # closed above.  Exit without running file-finalizer code that
                # could contend with the stuck daemon drain.
                sys.stdout.flush()
                sys.stderr.flush()
                os._exit(1)
            _replay_capture(
                capture_path,
                capture_writer=capture_writer,
                name=name,
                destination=destination,
                max_bytes=args.max_capture_bytes_per_stream,
                observed_bytes=capture_observed.get(name),
            )
            try:
                stream.close()
            except OSError:
                pass
            _checkpoint(f"capture.{name}.finished")

        if capture_errors:
            return_code = 1

    _checkpoint("supervisor.exiting")
    if timed_out:
        print(
            f"total lifecycle timed out after {args.total_timeout_seconds} seconds",
            file=sys.stderr,
        )
        return 1
    if return_code != 0:
        print(
            f"Windows lifecycle child failed with exit code {return_code}",
            file=sys.stderr,
        )
    return return_code


def main() -> int:
    args = _arguments()
    _checkpoint(f"supervisor.hard_deadline.armed.{args.hard_timeout_seconds}s")
    try:
        # faulthandler owns a native watchdog thread.  Unlike the ordinary
        # process.wait timeout, this bounds preflight, job-object calls,
        # cleanup, capture replay, and interpreter teardown as one lifetime.
        faulthandler.dump_traceback_later(
            args.hard_timeout_seconds,
            repeat=False,
            file=sys.stderr,
            exit=True,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            f"Windows lifecycle supervisor hard deadline could not be armed: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        return _run(args)
    finally:
        faulthandler.cancel_dump_traceback_later()
        _checkpoint("supervisor.hard_deadline.cancelled")


if __name__ == "__main__":
    raise SystemExit(main())
