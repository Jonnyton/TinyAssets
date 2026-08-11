"""Codex / GPT provider -- ``codex exec`` subprocess.

Covered by the ChatGPT Plus subscription.  Different model family from
Claude, making it ideal as a judge when Claude is the writer.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from tinyassets.exceptions import (
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from tinyassets.providers.base import (
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    check_bwrap_failure,
    get_sandbox_status,
    subprocess_env_for_provider,
)


def _no_window_kwargs() -> dict:
    """Return subprocess kwargs to suppress console windows on Windows."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _resolve_codex_cmd() -> tuple[list[str], bool]:
    """Resolve the codex command, handling Windows .cmd/.bat wrappers.

    Returns (base_cmd, use_shell) where base_cmd is the command prefix
    and use_shell indicates whether to use shell execution.
    """
    codex_path = shutil.which("codex")
    if codex_path and sys.platform == "win32" and codex_path.lower().endswith((".cmd", ".bat")):
        return [codex_path], True
    if codex_path:
        return [codex_path], False
    return ["codex"], False


_CODEX_BIN_ASSIGNMENT = re.compile(
    r"(?m)^\s*CODEX_BIN\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|(\S+))\s*$"
)


def _resolved_codex_executable(base_cmd: list[str]) -> tuple[Path, Path]:
    """Return the invoked wrapper and the real executable it delegates to."""

    if not base_cmd:
        raise ProviderError("codex served sandbox cannot resolve an empty command")
    wrapper = Path(base_cmd[0]).expanduser()
    if not wrapper.is_absolute():
        located = shutil.which(str(wrapper))
        if not located:
            raise ProviderError("codex served sandbox cannot resolve the executable")
        wrapper = Path(located)
    try:
        wrapper = Path(os.path.abspath(wrapper))
        resolved = wrapper.resolve(strict=True)
    except OSError as exc:
        raise ProviderError(
            "codex served sandbox cannot resolve the executable"
        ) from exc
    real_executable = resolved
    if wrapper == resolved:
        try:
            with wrapper.open("rb") as stream:
                wrapper_text = stream.read(65_536).decode("utf-8", errors="strict")
        except (OSError, UnicodeError):
            wrapper_text = ""
        if "CODEX_BIN" in wrapper_text:
            match = _CODEX_BIN_ASSIGNMENT.search(wrapper_text)
            if match is None:
                raise ProviderError(
                    "codex served sandbox cannot resolve the wrapper's real binary"
                )
            try:
                raw_real_executable = next(
                    value for value in match.groups() if value is not None
                )
                real_path = Path(raw_real_executable)
                if not real_path.is_absolute():
                    raise OSError("wrapper target is not absolute")
                real_executable = real_path.resolve(strict=True)
            except OSError as exc:
                raise ProviderError(
                    "codex served sandbox cannot resolve the wrapper's real binary"
                ) from exc
    if not real_executable.is_file():
        raise ProviderError("codex served sandbox resolved binary is not a file")
    return wrapper, real_executable


def _codex_binary_tree(real_executable: Path) -> Path:
    for ancestor in real_executable.parents:
        if ancestor.name == "node_modules":
            tree = ancestor.parent
            break
    else:
        tree = real_executable.parent
    if not tree.is_dir():
        raise ProviderError("codex served sandbox cannot mount the resolved binary tree")
    return tree


def _codex_sandbox_mounts(base_cmd: list[str]) -> tuple[Path, ...]:
    wrapper, real_executable = _resolved_codex_executable(base_cmd)
    candidates = [_codex_binary_tree(real_executable)]
    covered_roots = tuple(Path(path) for path in ("/usr", "/bin", "/lib", "/lib64"))
    if not any(wrapper.is_relative_to(root) for root in covered_roots):
        candidates.append(wrapper.parent)
    mounts: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve(strict=True)
        if resolved not in mounts:
            mounts.append(resolved)
    return tuple(mounts)


_VALID_CODEX_EFFORTS = frozenset({"minimal", "low", "medium", "high", "xhigh"})


def _reasoning_effort_args(effort: str | None) -> list[str]:
    """Map a generic ModelConfig.reasoning_effort to Codex's CLI override.

    Codex honors ``-c model_reasoning_effort=<minimal|low|medium|high|xhigh>``.
    Empty / unknown values yield no flag (provider default), so the knob is a
    pure opt-in and never breaks a call.
    """
    normalized = (effort or "").strip().lower()
    if normalized in _VALID_CODEX_EFFORTS:
        return ["-c", f"model_reasoning_effort={normalized}"]
    return []


def _codex_model() -> str:
    """Return the Codex CLI model to request for provider calls."""
    return os.environ.get("TINYASSETS_CODEX_MODEL", "gpt-5.4").strip() or "gpt-5.4"


def _codex_workdir() -> str:
    """Return the source workspace Codex should inspect for coding tasks."""
    configured = os.environ.get("TINYASSETS_CODEX_WORKDIR", "").strip()
    if configured:
        return configured
    return str(Path(__file__).resolve().parents[2])


class CodexProvider(BaseProvider):
    """Calls GPT via the ``codex exec`` CLI binary."""

    name = "codex"
    family = "openai"

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("codex") is not None

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir: Path | None = None,
    ) -> ProviderResponse:
        full_input = f"{system}\n\n{prompt}" if system else prompt

        base_cmd, use_shell = _resolve_codex_cmd()
        model = _codex_model()
        sandbox_status = get_sandbox_status()
        sandbox_args = ["--full-auto"] if sandbox_status.get("bwrap_available") else [
            "--dangerously-bypass-approvals-and-sandbox"
        ]
        # Prompt-node calls use Codex as a subscription-backed text model, but
        # loop-investigation coding prompts still need repo source/tests mounted.
        # Prefer Codex's sandboxed auto mode when bwrap is actually usable;
        # bwrap-less hosts fall back to the hosted subscription mode already
        # used by auto-fix, with API keys stripped.
        # Per-node effort (real Codex setting, not a prompt hint): when the
        # branch node declares config.reasoning_effort, override Codex's
        # model_reasoning_effort so a light node (e.g. localize) runs minimal/
        # low and finishes fast+cheap instead of deep-reasoning a trivial task.
        effort_args = _reasoning_effort_args(
            getattr(config, "reasoning_effort", "")
        )
        proc_env = subprocess_env_for_provider(
            self.name,
            universe_dir=universe_dir,
            credential_snapshot_dir=config.credential_snapshot_dir,
        )
        machine_accounting = bool(config.sandbox_workspace)
        if config.sandbox_workspace:
            if universe_dir is None or use_shell or not sandbox_status.get("bwrap_available"):
                raise ProviderError(
                    "codex served turns require the OS sandbox; refusing unconfined launch"
                )
            bwrap_path = str(sandbox_status.get("bwrap_path") or shutil.which("bwrap") or "")
            codex_home = Path(proc_env.get("CODEX_HOME", "")).resolve(strict=False)
            universe_root = universe_dir.resolve(strict=False)
            try:
                codex_home.relative_to(universe_root)
            except ValueError as exc:
                raise ProviderError("codex auth home is outside the served universe") from exc
            if not bwrap_path or not codex_home.is_dir():
                raise ProviderError(
                    "codex served turns require an available OS sandbox and universe auth"
                )
            binary_mounts = _codex_sandbox_mounts(base_cmd)
            sandbox_args = [
                "--full-auto",
                "--ignore-user-config",
                "--ignore-rules",
                "--disable",
                "shell_tool",
                "--disable",
                "unified_exec",
                "-c",
                'web_search="cached"',
                "--json",
            ]
        cmd = [
            *base_cmd,
            "exec",
            "-m",
            model,
            *effort_args,
            *sandbox_args,
            "--skip-git-repo-check",
            "--ephemeral",
        ]

        win_kw = _no_window_kwargs()
        if config.sandbox_workspace:
            inner_cmd = [*cmd, "-C", "/workspace"]
            bwrap_cmd = [
                bwrap_path,
                "--die-with-parent",
                "--new-session",
                "--unshare-all",
                "--share-net",
                "--dev",
                "/dev",
                "--proc",
                "/proc",
                "--tmpfs",
                "/tmp",
                "--ro-bind",
                str(universe_root),
                "/workspace",
                "--tmpfs",
                "/workspace/.runtime/provider-launch-credentials",
                "--ro-bind",
                str(codex_home),
                "/codex-home",
                "--setenv",
                "CODEX_HOME",
                "/codex-home",
                "--setenv",
                "HOME",
                "/tmp",
            ]
            for system_path in (
                "/usr",
                "/bin",
                "/lib",
                "/lib64",
                "/etc/ssl/certs",
                "/etc/resolv.conf",
                "/etc/hosts",
                "/etc/nsswitch.conf",
            ):
                if Path(system_path).exists() or system_path == "/usr":
                    bwrap_cmd.extend(("--ro-bind", system_path, system_path))
            for binary_mount in binary_mounts:
                if binary_mount == Path("/usr"):
                    continue
                if binary_mount.parent == Path("/opt"):
                    bwrap_cmd.extend(("--dir", "/opt"))
                bwrap_cmd.extend(
                    ("--ro-bind", str(binary_mount), str(binary_mount))
                )
            cmd_with_cwd = [*bwrap_cmd, "--", *inner_cmd]
            proc_env["CODEX_HOME"] = "/codex-home"
            proc_env["HOME"] = "/tmp"
        else:
            cmd_with_cwd = [*cmd, "-C", _codex_workdir()]
        if use_shell:
            proc = await asyncio.create_subprocess_shell(
                shlex.join(cmd_with_cwd),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=proc_env,
                **win_kw,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *cmd_with_cwd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=proc_env,
                **win_kw,
            )

        start = time.monotonic()

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=full_input.encode("utf-8")),
                timeout=config.timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise ProviderTimeoutError(
                f"codex exec exceeded {config.timeout}s timeout"
            )

        elapsed_ms = (time.monotonic() - start) * 1000

        # Quick exit-code-1 => provider unavailable (same heuristic as claude)
        if proc.returncode == 1 and elapsed_ms < 5000:
            raise ProviderUnavailableError(
                "codex exec returned exit code 1 quickly -- likely unavailable"
            )

        stderr_text = stderr.decode("utf-8", errors="replace")
        check_bwrap_failure(stderr_text)

        if proc.returncode != 0:
            raise ProviderError(
                f"codex exec exit {proc.returncode}: {stderr_text}"
            )

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        input_tokens = None
        output_tokens = None
        cost_microunits = None
        if machine_accounting:
            messages: list[str] = []
            usage: dict[str, object] | None = None
            try:
                events = [json.loads(line) for line in stdout_text.splitlines() if line.strip()]
            except (json.JSONDecodeError, TypeError) as exc:
                raise ProviderError("codex returned invalid accounting output") from exc
            for event in events:
                if not isinstance(event, dict):
                    raise ProviderError("codex returned invalid accounting output")
                item = event.get("item")
                if (
                    event.get("type") == "item.completed"
                    and isinstance(item, dict)
                    and item.get("type") == "agent_message"
                    and isinstance(item.get("text"), str)
                ):
                    messages.append(item["text"])
                if event.get("type") == "turn.completed" and isinstance(
                    event.get("usage"), dict
                ):
                    usage = event["usage"]
            if not messages or usage is None:
                raise ProviderError("codex accounting output omitted result or usage")
            try:
                input_tokens = int(usage["input_tokens"])
                output_tokens = int(usage["output_tokens"]) + int(
                    usage.get("reasoning_output_tokens", 0)
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderError("codex accounting output contained invalid usage") from exc
            if input_tokens < 0 or output_tokens < 0:
                raise ProviderError("codex accounting output contained invalid usage")
            cost_microunits = (input_tokens + output_tokens) * 100
            text = messages[-1].strip()
        else:
            text = stdout_text

        if not text:
            # codex v0.122+ exits 0 on auth failure (401) but emits nothing to
            # stdout. Detect the silent-auth-failure pattern and surface it as a
            # hard error rather than returning an empty response that cascades
            # silently through downstream nodes.
            _auth_patterns = ("401", "Unauthorized", "Reconnecting", "auth")
            stderr_lower = stderr_text.lower()
            if any(p.lower() in stderr_lower for p in _auth_patterns):
                excerpt = stderr_text[:300].strip()
                raise ProviderError(
                    f"codex returned empty stdout with auth-error signal in stderr "
                    f"(exit={proc.returncode}): {excerpt}"
                )
            raise ProviderError(
                f"codex returned empty response (exit={proc.returncode}); "
                f"stderr: {stderr_text[:200].strip() or '(empty)'}"
            )

        return ProviderResponse(
            text=text,
            provider=self.name,
            model=model,
            family=self.family,
            latency_ms=elapsed_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_microunits=cost_microunits,
        )
