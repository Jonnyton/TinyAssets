"""Uniform process-launch logging for local runtime adapters."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SUPPORTED_ENGINES = frozenset({
    "scummvm",
    "chocolate-doom",
    "dosbox-staging",
    "retroarch",
})


@dataclass(frozen=True)
class ProcLaunchLog:
    """Structured stdio record for a launched runtime process."""

    engine: str
    argv: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    cwd: str | None = None
    timed_out: bool = False
    launch_error: str = ""
    duration_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.launch_error

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "argv": list(self.argv),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "cwd": self.cwd,
            "timed_out": self.timed_out,
            "launch_error": self.launch_error,
            "duration_ms": self.duration_ms,
            "ok": self.ok,
        }


Runner = Callable[..., subprocess.CompletedProcess[str]]


def launch_process(
    engine: str,
    argv: Sequence[str | Path],
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
    runner: Runner = subprocess.run,
) -> ProcLaunchLog:
    """Launch an approved emulator process and capture stdout/stderr uniformly."""

    normalized_engine = _normalize_engine(engine)
    if normalized_engine not in _SUPPORTED_ENGINES:
        supported = ", ".join(sorted(_SUPPORTED_ENGINES))
        raise ValueError(
            f"unsupported process launch engine {engine!r}; expected one of: {supported}"
        )

    cmd = tuple(str(part) for part in argv)
    if not cmd:
        raise ValueError("argv must contain at least the executable name")

    cwd_text = str(cwd) if cwd is not None else None
    started = time.monotonic()
    try:
        result = runner(
            list(cmd),
            cwd=cwd_text,
            env=dict(env) if env is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
        return ProcLaunchLog(
            engine=normalized_engine,
            argv=cmd,
            cwd=cwd_text,
            returncode=result.returncode,
            stdout=_coerce_text(result.stdout),
            stderr=_coerce_text(result.stderr),
            duration_ms=_elapsed_ms(started),
        )
    except subprocess.TimeoutExpired as exc:
        return ProcLaunchLog(
            engine=normalized_engine,
            argv=cmd,
            cwd=cwd_text,
            returncode=None,
            stdout=_coerce_text(exc.stdout or exc.output),
            stderr=_coerce_text(exc.stderr),
            timed_out=True,
            duration_ms=_elapsed_ms(started),
        )
    except OSError as exc:
        message = f"{type(exc).__name__}: {exc}"
        return ProcLaunchLog(
            engine=normalized_engine,
            argv=cmd,
            cwd=cwd_text,
            returncode=None,
            stdout="",
            stderr=message,
            launch_error=message,
            duration_ms=_elapsed_ms(started),
        )


def launch_scummvm(
    argv: Sequence[str | Path],
    **kwargs: Any,
) -> ProcLaunchLog:
    return launch_process("scummvm", argv, **kwargs)


def launch_chocolate_doom(
    argv: Sequence[str | Path],
    **kwargs: Any,
) -> ProcLaunchLog:
    return launch_process("chocolate-doom", argv, **kwargs)


def launch_dosbox_staging(
    argv: Sequence[str | Path],
    **kwargs: Any,
) -> ProcLaunchLog:
    return launch_process("dosbox-staging", argv, **kwargs)


def launch_retroarch(
    argv: Sequence[str | Path],
    **kwargs: Any,
) -> ProcLaunchLog:
    return launch_process("retroarch", argv, **kwargs)


def _coerce_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _normalize_engine(engine: str) -> str:
    return "-".join(engine.strip().lower().replace("_", "-").split())


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))
