#!/usr/bin/env python3
"""Scope-verified git commit builder for FUSE-locked checkouts.

Cowork sometimes has to use git plumbing because normal git porcelain can race
against FUSE lock behavior. The dangerous pattern is copying ``.git/index`` into
``GIT_INDEX_FILE``: that snapshots stale local staged state and can produce a
kitchen-sink regression commit. This wrapper always starts from an explicit base
ref, applies only declared file blobs, verifies the resulting diff, and then
prints the new commit SHA.

Usage:
    python3 scripts/fuse_safe_commit.py \
        --base-ref origin/main \
        --file REPO_PATH:CONTENT_PATH \
        --message "commit message" \
        --max-files 1 \
        --update-ref .git/refs/heads/main
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class SafeCommitError(RuntimeError):
    """Runtime failure after arguments have been accepted."""


def _run(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    if input_text is not None and input_bytes is not None:
        raise ValueError("input_text and input_bytes are mutually exclusive")
    text_mode = input_bytes is None
    proc = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        input=input_text if text_mode else input_bytes,
        text=text_mode,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        stdout = (
            proc.stdout
            if isinstance(proc.stdout, str)
            else proc.stdout.decode("utf-8", "replace")
        )
        stderr = (
            proc.stderr
            if isinstance(proc.stderr, str)
            else proc.stderr.decode("utf-8", "replace")
        )
        raise SafeCommitError(
            "command failed "
            f"(exit={proc.returncode}): {' '.join(args)}\n"
            f"stdout: {stdout}\n"
            f"stderr: {stderr}"
        )
    return proc


def _repo_root(path: str) -> Path:
    root = Path(path).resolve()
    proc = _run(["git", "rev-parse", "--show-toplevel"], cwd=root)
    out = str(proc.stdout).strip()
    if not out:
        raise SafeCommitError(f"could not resolve git repository root from {path!r}")
    return Path(out).resolve()


def _git_dir(repo_root: Path) -> Path:
    proc = _run(["git", "rev-parse", "--git-dir"], cwd=repo_root)
    raw = str(proc.stdout).strip()
    git_dir = Path(raw)
    if not git_dir.is_absolute():
        git_dir = repo_root / git_dir
    return git_dir.resolve()


def _resolve_ref(repo_root: Path, ref: str) -> str:
    proc = _run(["git", "rev-parse", f"{ref}^{{commit}}"], cwd=repo_root)
    sha = str(proc.stdout).strip()
    if not SHA_RE.fullmatch(sha):
        raise SafeCommitError(f"ref {ref!r} did not resolve to a commit SHA")
    return sha


def _normalize_repo_path(raw: str) -> str:
    path = raw.replace("\\", "/").strip()
    if not path:
        raise ValueError("repo path must be non-empty")
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise ValueError("repo path must be repository-relative")
    parts = PurePosixPath(path).parts
    if ".." in parts:
        raise ValueError("repo path must stay inside the repository")
    if ".git" in parts:
        raise ValueError("repo path must not target .git internals")
    if parts in {(".",), ("",)}:
        raise ValueError("repo path must name a file")
    return PurePosixPath(*parts).as_posix()


def _parse_file_arg(raw: str) -> tuple[str, Path]:
    repo_path, sep, content_path = raw.partition(":")
    if not sep:
        raise ValueError("--file must be REPO_PATH:CONTENT_PATH")
    normalized = _normalize_repo_path(repo_path)
    content = Path(content_path)
    if not content.is_file():
        raise ValueError(f"content path does not exist: {content_path!r}")
    return normalized, content


def _mode_for_path(repo_root: Path, base_sha: str, repo_path: str) -> str:
    proc = _run(["git", "ls-tree", base_sha, "--", repo_path], cwd=repo_root)
    line = str(proc.stdout).strip()
    if not line:
        return "100644"
    return line.split(maxsplit=1)[0]


def _hash_blob(repo_root: Path, env: dict[str, str], content_path: Path) -> str:
    content = content_path.read_bytes()
    proc = _run(
        ["git", "hash-object", "-w", "--stdin"],
        cwd=repo_root,
        env=env,
        input_bytes=content,
    )
    stdout = proc.stdout if isinstance(proc.stdout, bytes) else str(proc.stdout).encode()
    sha = stdout.decode("utf-8", "replace").strip()
    if not SHA_RE.fullmatch(sha):
        raise SafeCommitError(f"hash-object returned non-SHA output: {sha!r}")
    return sha


def _diff_names(repo_root: Path, base_sha: str, new_sha: str) -> list[str]:
    proc = _run(
        ["git", "diff", "--name-only", "-z", f"{base_sha}..{new_sha}"],
        cwd=repo_root,
    )
    raw = str(proc.stdout)
    return [name for name in raw.split("\0") if name]


def build_commit(
    *,
    repo_root: Path,
    base_ref: str,
    files: list[tuple[str, Path]],
    message: str,
    max_files: int | None,
) -> str:
    if not files:
        raise ValueError("at least one --file is required")
    if max_files is not None and max_files < 0:
        raise ValueError("--max-files must be >= 0")

    base_sha = _resolve_ref(repo_root, base_ref)
    declared_paths = {repo_path for repo_path, _ in files}

    with tempfile.TemporaryDirectory(prefix="fuse_safe_commit_") as tmp:
        index_path = str(Path(tmp) / "index")
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = index_path

        _run(["git", "read-tree", base_sha], cwd=repo_root, env=env)

        for repo_path, content_path in files:
            blob_sha = _hash_blob(repo_root, env, content_path)
            mode = _mode_for_path(repo_root, base_sha, repo_path)
            _run(
                [
                    "git",
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    f"{mode},{blob_sha},{repo_path}",
                ],
                cwd=repo_root,
                env=env,
            )

        tree_proc = _run(["git", "write-tree"], cwd=repo_root, env=env)
        tree_sha = str(tree_proc.stdout).strip()
        if not SHA_RE.fullmatch(tree_sha):
            raise SafeCommitError(f"write-tree returned non-SHA output: {tree_sha!r}")

        commit_proc = _run(
            ["git", "commit-tree", tree_sha, "-p", base_sha, "-F", "-"],
            cwd=repo_root,
            env=env,
            input_text=message,
        )
        new_sha = str(commit_proc.stdout).strip()
        if not SHA_RE.fullmatch(new_sha):
            raise SafeCommitError(f"commit-tree returned non-SHA output: {new_sha!r}")

    names = _diff_names(repo_root, base_sha, new_sha)
    if not names:
        raise SafeCommitError("resulting commit has an empty diff")

    cap = len(files) if max_files is None else max_files
    if len(names) > cap:
        raise SafeCommitError(
            f"diff touches {len(names)} files, exceeds --max-files {cap}"
        )

    unexpected = sorted(set(names) - declared_paths)
    if unexpected:
        raise SafeCommitError(
            "diff contains undeclared paths: " + ", ".join(unexpected)
        )

    return new_sha


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        if tmp_path.stat().st_size != len(content):
            raise SafeCommitError(f"temp ref write size mismatch for {path}")
        os.replace(tmp_path, path)
        if path.stat().st_size != len(content):
            raise SafeCommitError(f"final ref write size mismatch for {path}")
    except Exception:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def _update_ref_path(repo_root: Path, update_ref: str, new_sha: str) -> None:
    git_dir = _git_dir(repo_root)
    normalized = update_ref.replace("\\", "/")
    rel: str | None = None

    if normalized.startswith(".git/"):
        rel = normalized[len(".git/") :]
    elif normalized.startswith("refs/"):
        rel = normalized
    else:
        candidate = Path(update_ref)
        if candidate.is_absolute():
            try:
                rel = candidate.resolve().relative_to(git_dir).as_posix()
            except ValueError as exc:
                raise ValueError("--update-ref absolute path must be inside git dir") from exc

    if rel is None or not rel.startswith("refs/") or ".." in PurePosixPath(rel).parts:
        raise ValueError("--update-ref must be refs/... or .git/refs/...")

    _atomic_write(git_dir / PurePosixPath(rel), f"{new_sha}\n".encode("ascii"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a scope-verified git commit from a known-good base ref.",
    )
    parser.add_argument("--base-ref", required=True)
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="REPO_PATH:CONTENT_PATH. Repeat for each file to add or replace.",
        required=True,
    )
    parser.add_argument("--message", required=True)
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--update-ref", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        repo_root = _repo_root(args.repo_root)
        files = [_parse_file_arg(raw) for raw in args.file]
        new_sha = build_commit(
            repo_root=repo_root,
            base_ref=args.base_ref,
            files=files,
            message=args.message,
            max_files=args.max_files,
        )
        if args.update_ref:
            _update_ref_path(repo_root, args.update_ref, new_sha)
    except ValueError as exc:
        print(f"FUSE_SAFE_COMMIT: {exc}", file=sys.stderr)
        return 2
    except SafeCommitError as exc:
        print(f"FUSE_SAFE_COMMIT: {exc}", file=sys.stderr)
        return 1

    print(new_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
