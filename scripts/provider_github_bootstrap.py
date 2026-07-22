"""Bootstrap GitHub CLI/git credentials for sandboxed provider sessions.

This does not create or print secrets. It consumes one of these existing
sources, in order:

1. GH_TOKEN
2. GITHUB_TOKEN
3. WORKFLOW_PUSH_TOKEN
4. GITHUB_PAT
5. .cowork-bootstrap/github.token

It writes ignored local wrappers at the repo root:

- .tmp-gh.cmd for Windows shells
- .tmp-gh.ps1 for PowerShell with ExecutionPolicy bypass
- .tmp-gh.sh for POSIX shells

Use --write-git-credentials to configure this checkout's git credential helper
to read a gitignored .cowork-bootstrap/git-credentials file. This keeps
credentials inside the host-managed ignored bootstrap directory instead of the
provider user's home directory.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO = "Jonnyton/Workflow"
TOKEN_ENV_NAMES = ("GH_TOKEN", "GITHUB_TOKEN", "WORKFLOW_PUSH_TOKEN", "GITHUB_PAT")


@dataclass(frozen=True)
class TokenSource:
    name: str
    value: str


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def token_source(root: Path) -> TokenSource | None:
    for name in TOKEN_ENV_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return TokenSource(name, value)

    token_file = root / ".cowork-bootstrap" / "github.token"
    if token_file.is_file():
        value = token_file.read_text(encoding="utf-8").strip()
        if value:
            return TokenSource(str(token_file.relative_to(root)), value)

    return None


def write_text(path: Path, text: str, executable: bool = False) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")
    if executable:
        try:
            path.chmod(path.stat().st_mode | 0o111)
        except OSError:
            pass


def write_wrappers(root: Path) -> list[Path]:
    config_dir = ".tmp-gh-config-codex"
    cmd = rf"""@echo off
setlocal

set "GH_CONFIG_DIR=%~dp0{config_dir}"
if not exist "%GH_CONFIG_DIR%" mkdir "%GH_CONFIG_DIR%" >nul 2>nul

set "GH_PROMPT_DISABLED=1"
set "GIT_TERMINAL_PROMPT=0"

if "%GH_TOKEN%"=="" if not "%WORKFLOW_PUSH_TOKEN%"=="" set "GH_TOKEN=%WORKFLOW_PUSH_TOKEN%"
if "%GH_TOKEN%"=="" if not "%GITHUB_TOKEN%"=="" set "GH_TOKEN=%GITHUB_TOKEN%"
if "%GH_TOKEN%"=="" if not "%GITHUB_PAT%"=="" set "GH_TOKEN=%GITHUB_PAT%"
if "%GH_TOKEN%"=="" if exist "%~dp0.cowork-bootstrap\github.token" set /p GH_TOKEN=<"%~dp0.cowork-bootstrap\github.token"

gh %*
exit /b %ERRORLEVEL%
"""
    ps1 = rf"""param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $GhArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$configDir = Join-Path $repoRoot "{config_dir}"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null

$env:GH_CONFIG_DIR = $configDir
$env:GH_PROMPT_DISABLED = "1"
$env:GIT_TERMINAL_PROMPT = "0"

if (-not $env:GH_TOKEN -and $env:WORKFLOW_PUSH_TOKEN) {{
    $env:GH_TOKEN = $env:WORKFLOW_PUSH_TOKEN
}}
if (-not $env:GH_TOKEN -and $env:GITHUB_TOKEN) {{
    $env:GH_TOKEN = $env:GITHUB_TOKEN
}}
if (-not $env:GH_TOKEN -and $env:GITHUB_PAT) {{
    $env:GH_TOKEN = $env:GITHUB_PAT
}}

$coworkToken = Join-Path $repoRoot ".cowork-bootstrap/github.token"
if (-not $env:GH_TOKEN -and (Test-Path -LiteralPath $coworkToken -PathType Leaf)) {{
    $env:GH_TOKEN = (Get-Content -LiteralPath $coworkToken -Raw).Trim()
}}

& gh @GhArgs
exit $LASTEXITCODE
"""
    sh = rf"""#!/usr/bin/env bash
set -euo pipefail

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
export GH_CONFIG_DIR="$repo_root/{config_dir}"
mkdir -p "$GH_CONFIG_DIR"

export GH_PROMPT_DISABLED=1
export GIT_TERMINAL_PROMPT=0

if [ -z "${{GH_TOKEN:-}}" ] && [ -n "${{WORKFLOW_PUSH_TOKEN:-}}" ]; then
  export GH_TOKEN="$WORKFLOW_PUSH_TOKEN"
fi
if [ -z "${{GH_TOKEN:-}}" ] && [ -n "${{GITHUB_TOKEN:-}}" ]; then
  export GH_TOKEN="$GITHUB_TOKEN"
fi
if [ -z "${{GH_TOKEN:-}}" ] && [ -n "${{GITHUB_PAT:-}}" ]; then
  export GH_TOKEN="$GITHUB_PAT"
fi
if [ -z "${{GH_TOKEN:-}}" ] && [ -f "$repo_root/.cowork-bootstrap/github.token" ]; then
  export GH_TOKEN="$(tr -d '\r\n' < "$repo_root/.cowork-bootstrap/github.token")"
fi

exec gh "$@"
"""

    paths = [root / ".tmp-gh.cmd", root / ".tmp-gh.ps1", root / ".tmp-gh.sh"]
    write_text(paths[0], cmd)
    write_text(paths[1], ps1)
    write_text(paths[2], sh, executable=True)
    (root / config_dir).mkdir(exist_ok=True)
    return paths


def write_git_credentials(root: Path, token: str) -> Path:
    cred_dir = root / ".cowork-bootstrap"
    cred_dir.mkdir(exist_ok=True)
    cred_file = cred_dir / "git-credentials"
    write_text(cred_file, f"https://Jonnyton:{token}@github.com\n")

    helper = f"store --file {cred_file}"
    subprocess.run(
        ["git", "config", "--local", "credential.helper", helper],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return cred_file


def socket_check(host: str = "api.github.com", port: int = 443) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=5):
            return True, f"{host}:{port} reachable"
    except OSError as exc:
        return False, f"{host}:{port} blocked: {exc.__class__.__name__}: {exc}"


def run_gh(args: list[str], root: Path, token: TokenSource | None) -> tuple[int, str]:
    gh = shutil.which("gh")
    if not gh:
        return 127, "gh not found on PATH"

    env = os.environ.copy()
    env["GH_CONFIG_DIR"] = str(root / ".tmp-gh-config-codex")
    env["GH_PROMPT_DISABLED"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    if token and not env.get("GH_TOKEN"):
        env["GH_TOKEN"] = token.value

    proc = subprocess.run(
        [gh, *args],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=20,
    )
    return proc.returncode, proc.stdout.strip()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write-git-credentials",
        action="store_true",
        help="configure local git credential helper using the discovered token",
    )
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="write wrappers only; skip gh/network diagnostics",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    token = token_source(root)
    wrappers = write_wrappers(root)

    print("provider-github-bootstrap")
    print(f"repo: {root}")
    print("wrappers:")
    for path in wrappers:
        print(f"- {path.name}")

    if token:
        print(f"token source: {token.name} (present, length {len(token.value)})")
    else:
        print("token source: none")

    if args.skip_checks:
        if args.write_git_credentials:
            if not token:
                print("git credentials: skipped, no token source")
            else:
                cred_file = write_git_credentials(root, token.value)
                print(f"git credentials: configured local helper -> {cred_file.relative_to(root)}")
        return 0

    gh_code, gh_output = run_gh(["--version"], root, token)
    if gh_code == 0:
        print("gh binary: ok")
        print(gh_output.splitlines()[0])
    else:
        print(f"gh binary: failed ({gh_code})")
        print(gh_output)

    network_ok, network_msg = socket_check()
    print(f"network: {'ok' if network_ok else 'blocked'}")
    print(network_msg)

    auth_code: int | None = None
    if network_ok:
        auth_code, auth_output = run_gh(["auth", "status"], root, token)
        print(f"gh auth status: exit {auth_code}")
        if auth_output:
            print(auth_output)
    else:
        print("gh auth status: skipped because GitHub network is blocked")

    if args.write_git_credentials:
        if not token:
            print("git credentials: skipped, no token source")
        elif auth_code == 0:
            cred_file = write_git_credentials(root, token.value)
            print(f"git credentials: configured local helper -> {cred_file.relative_to(root)}")
        else:
            print(
                "git credentials: skipped because token/network checks did not pass "
                "(use --skip-checks only when the token is known current)"
            )

    if gh_code != 0:
        return gh_code
    if not token:
        return 2
    if not network_ok:
        return 3
    if auth_code != 0:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
