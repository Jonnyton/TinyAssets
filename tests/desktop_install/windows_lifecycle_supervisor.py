from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, TextIO


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
) -> None:
    capture_writer.flush()
    initial_observed_bytes = os.fstat(capture_writer.fileno()).st_size
    replay_bytes = min(initial_observed_bytes, max_bytes)
    with capture_path.open("rb") as capture_reader:
        data = capture_reader.read(replay_bytes)
    observed_bytes = max(
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
    try:
        result = subprocess.run(
            ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=cleanup_timeout_seconds,
            check=False,
            creationflags=creationflags,
        )
        if result.returncode != 0 and process.poll() is None:
            print(
                "::warning title=Windows lifecycle cleanup::"
                f"taskkill exited {result.returncode} for child PID {process.pid}",
                flush=True,
            )
    except subprocess.TimeoutExpired:
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
    try:
        process.wait(timeout=cleanup_timeout_seconds)
    except subprocess.TimeoutExpired:
        print(
            "::warning title=Windows lifecycle cleanup::"
            f"child PID {process.pid} survived bounded cleanup",
            flush=True,
        )


def main() -> int:
    args = _arguments()
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

    with (
        _capture_file() as (stdout_capture_path, stdout_capture_writer),
        _capture_file() as (stderr_capture_path, stderr_capture_writer),
    ):
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout_capture_writer,
                stderr=stderr_capture_writer,
                creationflags=creationflags,
            )
        except OSError as exc:
            print(f"Windows lifecycle child failed to start: {exc}", file=sys.stderr)
            return 1

        print(
            "::notice title=Windows lifecycle supervisor::"
            f"child PID {process.pid}; total deadline "
            f"{args.total_timeout_seconds} seconds",
            flush=True,
        )
        timed_out = False
        try:
            return_code = process.wait(timeout=args.total_timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            print(
                "::error title=Windows lifecycle total timeout::"
                f"child PID {process.pid} exceeded {args.total_timeout_seconds} seconds",
                flush=True,
            )
            _terminate_tree(process, cleanup_timeout_seconds=args.cleanup_timeout_seconds)
            return_code = 1

        _replay_capture(
            stdout_capture_path,
            capture_writer=stdout_capture_writer,
            name="stdout",
            destination=sys.stdout,
            max_bytes=args.max_capture_bytes_per_stream,
        )
        _replay_capture(
            stderr_capture_path,
            capture_writer=stderr_capture_writer,
            name="stderr",
            destination=sys.stderr,
            max_bytes=args.max_capture_bytes_per_stream,
        )

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


if __name__ == "__main__":
    raise SystemExit(main())
