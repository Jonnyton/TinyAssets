"""Codex / GPT provider -- ``codex exec`` subprocess.

Covered by the ChatGPT Plus subscription.  Different model family from
Claude, making it ideal as a judge when Claude is the writer.
"""

from __future__ import annotations

import asyncio
import os
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
    OS_SANDBOX_ATTESTATION_ENV,
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    SandboxUnavailableError,
    check_bwrap_failure,
    cleanup_sandbox_job_dir,
    get_sandbox_status,
    new_sandbox_job_dir,
    os_sandbox_attested,
    sandbox_spawn_env_and_dir,
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
    return ["codex"], False


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


def _codex_sandbox_args(
    config: ModelConfig, sandbox_status: dict,
) -> list[str]:
    """Pick codex's sandbox flags, gating the bypass on attestation.

    Codex honors NO tool allow/deny policy (unlike claude), so a node's
    classification is IRRELEVANT to what codex can touch: the only two modes are
    ``--full-auto`` (real bwrap sandbox) and
    ``--dangerously-bypass-approvals-and-sandbox`` (full host shell + repo). The
    escape (Codex S3 REJECT C1): declassify a node → route to codex via
    ``llm_policy`` → on a bwrap-LESS host codex used the bypass = shell on the
    droplet, regardless of the sandbox tool policy claude enforces.

    So the gate is independent of ``os_sandbox_required``:

    * bwrap available → ``--full-auto`` (real per-call sandbox) — unchanged, and
      the expected Linux-droplet path.
    * bwrap absent BUT the whole process is attested-isolated
      (``TINYASSETS_OS_SANDBOX_ATTESTED``) → bypass permitted (an external
      sandbox contains it).
    * bwrap absent AND unattested → REFUSE for ALL nodes (fail closed) — this is
      the actual multi-tenant vulnerability.
    """
    bwrap_ok = bool(sandbox_status.get("bwrap_available"))
    if bwrap_ok:
        return ["--full-auto"]
    if os_sandbox_attested():
        return ["--dangerously-bypass-approvals-and-sandbox"]
    raise SandboxUnavailableError(
        "codex has no bwrap sandbox and this process is not attested-isolated "
        f"({sandbox_status.get('reason') or 'no bwrap'}; "
        f"{OS_SANDBOX_ATTESTATION_ENV} unset). Its only non-bwrap mode "
        "(--dangerously-bypass-approvals-and-sandbox) grants full host "
        "shell/repo access regardless of any node tool policy — refusing for ALL "
        "nodes (fail closed). Provide bwrap (--full-auto per call) or run the "
        "daemon under attested OS isolation."
    )


class CodexProvider(BaseProvider):
    """Calls GPT via the ``codex exec`` CLI binary."""

    name = "codex"
    family = "openai"
    # Enforces the hardened coding-sandbox contract (bwrap --full-auto
    # self-confinement, never bypass, sanitized vault-only env). See FINDING 4.
    supports_coding_sandbox = True

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

        # Fail-closed (2026-07-03 P0 review, Codex ADAPT): Codex cannot enforce
        # the founder-facing universe sandbox — its `--sandbox read-only` still
        # reads the whole filesystem and it honors no tool allow/deny policy, so
        # a founder's universe could read the repo / other universes / host files.
        # Refuse rather than run a founder-facing turn unconfined; the universe's
        # assigned engine must be a sandbox-capable one (claude-code).
        if config.sandbox_workspace:
            raise ProviderError(
                "codex cannot enforce the universe sandbox (WebFetch-only + "
                "filesystem confinement); refusing to run a founder-facing turn "
                "unconfined. Assign a sandbox-capable engine (claude-code)."
            )
        base_cmd, use_shell = _resolve_codex_cmd()
        model = _codex_model()
        sandbox_status = get_sandbox_status()
        # Coding-node sandboxes fail closed here (never bypass); host-trusted
        # calls keep the --full-auto / hosted-mode fallback.
        sandbox_args = _codex_sandbox_args(config, sandbox_status)
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
        # Sanitized env for a sandbox-required coding node (only codex's own auth
        # — no cross-tenant secrets to `env`-dump); normal calls keep the full env.
        proc_env, scratch_dir = sandbox_spawn_env_and_dir(
            self.name, config, universe_dir=universe_dir,
        )
        # C1(a) (Codex S3 REJECT r2): codex's `-C` workdir MUST ALWAYS be a fresh
        # per-job SCRATCH dir, NEVER the daemon repo / host checkout — codex honors
        # NO tool policy and BOTH --full-auto (workspace-write) and the bypass grant
        # file write, so a text/declassified node routed here would otherwise get
        # read/edit/commands in the daemon checkout. An empty scratch makes that
        # workspace-write harmless. This applies to EVERY node kind (text + coding),
        # under --full-auto AND bypass. `_codex_workdir()` (the repo root) is no
        # longer used for -C — repo-touching nodes fail closed before reaching any
        # provider, so codex never legitimately needs the daemon repo.
        if scratch_dir is None:
            scratch_dir = new_sandbox_job_dir()
        workdir = scratch_dir

        win_kw = _no_window_kwargs()
        cmd_with_cwd = [*cmd, "-C", workdir]
        try:
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

            text = stdout.decode("utf-8", errors="replace").strip()

            if not text:
                # codex v0.122+ exits 0 on auth failure (401) but emits nothing to
                # stdout. Detect the silent-auth-failure pattern and surface it as
                # a hard error rather than returning an empty response that
                # cascades silently through downstream nodes.
                _auth_patterns = ("401", "Unauthorized", "Reconnecting", "auth")
                stderr_lower = stderr_text.lower()
                if any(p.lower() in stderr_lower for p in _auth_patterns):
                    excerpt = stderr_text[:300].strip()
                    raise ProviderError(
                        f"codex returned empty stdout with auth-error signal in "
                        f"stderr (exit={proc.returncode}): {excerpt}"
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
            )
        finally:
            cleanup_sandbox_job_dir(scratch_dir)
