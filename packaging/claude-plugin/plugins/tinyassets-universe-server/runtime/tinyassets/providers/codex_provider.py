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


_SECRET_SHAPES = re.compile(
    # Explicit secret shapes only (a generic long-token rule also hid hashes,
    # paths and model ids — the real cause). JWT fragments: any `eyJ…` run,
    # with or without the dotted tail.
    r"(sk-[A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_.-]{10,}|"
    r"(?i:bearer\s+\S+)|(?i:(?:token|secret|api[_-]?key|password)[\"']?\s*[:=]\s*\S+))"
)


def _redacted_stderr_excerpt(stderr_text: str, limit: int = 240) -> str:
    """The last stderr line, secrets replaced, as a head+tail excerpt.

    Feeds user-visible diagnostics (router chain_state), so it must be safe
    even if codex ever echoes credential material. Head+tail (not a plain
    prefix) because codex 0.135 appends its auth error code at the END of
    the line."""
    lines = [line.strip() for line in stderr_text.strip().splitlines() if line.strip()]
    if not lines:
        return "(no stderr)"
    text = _SECRET_SHAPES.sub("[redacted]", lines[-1])
    if len(text) <= limit:
        return text
    half = (limit - 5) // 2
    return text[:half] + " ... " + text[-half:]


def _codex_home_file_mounts(codex_home: Path) -> list[str]:
    """``--ro-bind`` args for each regular file of the sealed snapshot."""
    args: list[str] = []
    for entry in sorted(codex_home.iterdir()):
        if entry.is_symlink() or not entry.is_file():
            continue
        args.extend(("--ro-bind", str(entry), f"/codex-home/{entry.name}"))
    if not args:
        raise ProviderError("codex served sandbox found no credential files to mount")
    return args


# System state that lives in the universe dir and must NEVER be exposed to the
# served agent, even read-only: the deposited-LLM credential vault, the codex/
# claude auth snapshots, and the private universe config. Masked in BOTH the
# read-only coding mount and the read/write project-folder mount.
_UNIVERSE_SECRET_ENTRIES = (".credentials", ".credential-vault.json", "config.yaml")


def _mask_arg(path: Path, target: str) -> list[str]:
    """bwrap args that BLIND ``target`` inside the jail: an empty tmpfs over a
    directory, ``/dev/null`` over a file (symlinks masked as files, never
    followed)."""
    if path.is_dir() and not path.is_symlink():
        return ["--tmpfs", target]
    return ["--ro-bind", "/dev/null", target]


def _secret_mask_args(universe_root: Path) -> list[str]:
    """Mask the always-secret universe entries onto ``/workspace``."""
    args: list[str] = []
    for name in _UNIVERSE_SECRET_ENTRIES:
        p = universe_root / name
        if p.exists() or p.is_symlink():
            args += _mask_arg(p, f"/workspace/{name}")
    return args


def _project_folder_mounts(universe_root: Path) -> list[str]:
    """Bind the universe as the served agent's FULLY-OPEN read/WRITE project
    folder — its customizable harness and brain.

    A converse turn is the founder's own agent working in its own universe, so it
    may read, edit, and CREATE any file of any type there — notes, configs, tools,
    sub-agent definitions, whatever harness the founder shapes — and the edits
    persist. The ONLY things masked are the well-known, stable credential paths
    (the deposited-LLM vault, the auth snapshots, the private config); the
    per-launch credential snapshot under ``.runtime`` is masked separately in the
    bwrap builder. Everything else is the founder's to control. Isolation is at
    the universe boundary (OS sandbox + per-universe credentials), so full
    in-universe access is safe.

    NOTE: credentials are being relocated OUT of the universe entirely (to a
    sibling secrets dir); until every universe has migrated, this fixed
    credential mask is the belt-and-suspenders guard — a short, stable list of
    known credential paths, not a fragile "enumerate every secret" denylist.
    """
    return ["--bind", str(universe_root), "/workspace", *_secret_mask_args(universe_root)]


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
                # Defence-in-depth for served turns: `--ignore-user-config` drops
                # only $CODEX_HOME/config.toml — a served CODE turn still mounts
                # the universe at /workspace and could load a project-level
                # `.codex/config.toml` from it, which may declare its OWN
                # `mcp_servers`. Clear them so a crafted universe cannot inject an
                # MCP server into the served model (Codex cross-family review,
                # 2026-08-22). Account ChatGPT connectors are handled separately
                # by `--disable apps` in the shared command below.
                "-c",
                "mcp_servers={}",
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
            # Disable the `apps` feature (codex >= 0.135 default: stable/on) on
            # EVERY codex launch — served and non-served alike. It exposes the
            # subscription account's installed ChatGPT connectors — including
            # TinyAssets' OWN /mcp connector — to the model as `codex_apps` MCP
            # tools. `--ignore-user-config` does NOT strip these: they are
            # account/cloud-side, not config.toml. Seeing its own persona prompt,
            # the served universe intelligence "relays" the turn back through the
            # tinyassets_converse/write_graph app tool, which needs a fresh
            # ChatGPT-side OAuth and returns "This app connection requires
            # reauthentication..." — a confused-deputy loop that intermittently
            # replaced the real reply (live-diagnosed 2026-08-22, raw codex --json
            # showed the codex_apps tool call). No codex turn — served text,
            # served code, or the non-served auto-fix path — is ever a legitimate
            # client of the account's connectors. codex rejects unknown feature
            # names, so this fails closed on any future version that renames it.
            # Disabling apps also removes the codex_apps MCP server upstream, so
            # `enable_mcp_apps` / `apps_mcp_path_override` cannot resurrect it.
            "--disable",
            "apps",
            "--skip-git-repo-check",
            "--ephemeral",
        ]

        win_kw = _no_window_kwargs()
        if config.sandbox_workspace:
            inner_cmd = [*cmd, "-C", "/workspace"]
            # A converse turn is the founder's own agent working IN its universe:
            # its brain is a read/WRITE project folder it reads and evolves in
            # place (edits persist). `_project_folder_mounts` exposes ONLY the
            # markdown brain docs and masks all system state — the credential
            # vault, auth snapshots, private config, state DBs, serving/ledger
            # JSON, and every subdirectory — so the agent can never read a secret
            # or clobber its own permissions (isolation is at the universe
            # boundary, not per-file). Coding turns (run_graph etc.) keep the
            # read-only universe workspace, but with the always-secret entries
            # masked there too.
            if getattr(config, "sandbox_project_folder", False):
                # Founder converse: the universe as a read/WRITE project-folder brain.
                workspace_mount = _project_folder_mounts(universe_root)
            elif getattr(config, "sandbox_chat", False):
                # Non-founder converse: empty scratch workspace, no brain access.
                workspace_mount = ["--tmpfs", "/workspace"]
            else:
                # Coding turn (run_graph etc.): read-only universe, secrets masked.
                workspace_mount = [
                    "--ro-bind",
                    str(universe_root),
                    "/workspace",
                    *_secret_mask_args(universe_root),
                ]
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
                *workspace_mount,
                "--tmpfs",
                "/workspace/.runtime/provider-launch-credentials",
                # CODEX_HOME is a private tmpfs with the snapshot's credential
                # FILES bound read-only into it: codex >= 0.135's launcher
                # takes `flock $CODEX_HOME/.lock` before starting, so a
                # read-only home dir died instantly ("cannot open lock file
                # /codex-home/.lock: Read-only file system", exit 73 in 56 ms
                # -> "codex exhausted", live 2026-08-22). The credential bytes
                # stay immutable; only scratch files can be created beside them.
                "--tmpfs",
                "/codex-home",
                *_codex_home_file_mounts(codex_home),
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

        stderr_text = stderr.decode("utf-8", errors="replace")
        # Sandbox failures are classified FIRST: they are a host defect, not a
        # provider outage, and must surface as such instead of being folded
        # into a "likely unavailable" cooldown (how the 2026-08-21 outage hid).
        check_bwrap_failure(stderr_text)
        # Quick exit-code-1 => provider unavailable (same heuristic as claude).
        # Carry a REDACTED excerpt of codex's own words so the real cause is
        # visible; never raw stderr (it can carry token material).
        if proc.returncode == 1 and elapsed_ms < 5000:
            raise ProviderUnavailableError(
                "codex exec returned exit code 1 quickly -- likely unavailable: "
                + _redacted_stderr_excerpt(stderr_text)
            )


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
