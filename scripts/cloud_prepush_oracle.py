#!/usr/bin/env python3
"""Cloud-only pre-push Linux oracle: validate, materialize, apply, run, report.

WHY THIS EXISTS. ``scripts/linux_oracle.py`` needs local Docker. Some lanes
may not run Docker, WSL or any local service, yet a Linux-only mistake still
has to be caught BEFORE the candidate's runtime code is pushed. This helper
is the untrusted-input boundary for ``.github/workflows/cloud-prepush-oracle.yml``:
a manually dispatched, GitHub-hosted ubuntu job with ``contents: read`` only,
no secrets, no environment, that

  1. checks out this helper from the WORKFLOW revision into ``tooling/`` and
     validates the ``base_sha`` input as full 40-hex (``validate-base``)
     BEFORE checking out the immutable base into ``candidate/`` (both with
     credentials not persisted). The helper always runs from ``tooling/``
     with an explicit ``--repo candidate``, so the base commit never needs
     to contain this file,
  2. installs Python 3.11 + dev deps in ``candidate/`` BEFORE the patch
     touches the tree,
  3. receives a bounded base64 raw-or-gzip unified git patch + its SHA256,
     capped at 256 KiB uncompressed,
     materializes it under ``runner.temp`` and applies it with
     ``git apply --check`` then ``git apply`` (never ``--unsafe-paths``),
  4. runs ONLY the selected pytest node ids (validated: relative, under
     ``tests/``, no option-like / absolute / traversal tokens) with the temp
     root outside the checkout, and
  5. uploads JUnit and reports base sha, patch sha256 and pass/fail/skip
     counts. ``PROOF`` requires every selected test to PASS: a failure OR a
     skip is ``NOT-PROOF`` and the job fails.

All workflow inputs reach this helper through environment variables, never
through shell interpolation, and every subprocess is an exact argv list.

Local use (root, before dispatching by hand):

    python scripts/cloud_prepush_oracle.py prepare --base <sha> \
        --patch candidate.patch --out inputs.json -- tests/test_x.py::test_y
    gh workflow run cloud-prepush-oracle.yml --json < inputs.json

This helper never dispatches, publishes or deploys anything.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import zlib
from collections.abc import Callable, Sequence
from pathlib import Path
from xml.etree import ElementTree as ET

# GitHub caps the whole workflow_dispatch payload at 65,535 characters; the
# patch gets ~60 KB, the node-id list the rest, with headroom for the shas.
MAX_PATCH_B64_CHARS = 60_000
MAX_PATCH_BYTES = 256 * 1024
MAX_TESTS_JSON_CHARS = 4_000
MAX_NODEIDS = 64
HELPER_REL = "scripts/cloud_prepush_oracle.py"
#: The candidate may only touch reviewed source/test/script paths. It may
#: never rewrite the running workflow or this gate helper.
ALLOWED_PATCH_ROOTS = ("tinyassets/", "tests/", "scripts/")
ENV_BASE_SHA = "ORACLE_BASE_SHA"
ENV_PATCH_B64 = "ORACLE_PATCH_B64"
ENV_PATCH_SHA256 = "ORACLE_PATCH_SHA256"
ENV_TESTS_JSON = "ORACLE_TESTS_JSON"

_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_DIFF_HEADER_RE = re.compile(r"^diff --git a/(?P<a>.+) b/(?P<b>.+)$")
#: Heuristic only -- a reviewed diff should never carry these. Not a proof of
#: absence; the contract is that root supplies a reviewed tracked diff.
_SECRET_MARKERS = (
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"\bsk-ant-[A-Za-z0-9_-]{8,}"),
    re.compile(rb"\bghp_[A-Za-z0-9]{36}\b"),
    re.compile(rb"\bxox[abp]-[0-9A-Za-z-]{10,}"),
)

Runner = Callable[..., subprocess.CompletedProcess]


class OracleInputError(ValueError):
    """An input failed validation. Always fatal; never downgraded."""


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------


def validate_base_sha(value: str | None) -> str:
    if not isinstance(value, str) or not _SHA1_RE.match(value):
        raise OracleInputError(
            "base_sha must be a full 40-char lowercase hex commit sha "
            "(branch names, tags and abbreviated shas are rejected)"
        )
    return value


def validate_head_matches(base_sha: str, head_sha: str) -> None:
    if head_sha.strip() != base_sha:
        raise OracleInputError(
            f"checked-out HEAD {head_sha.strip()!r} is not base_sha {base_sha!r}"
        )


def decode_patch(patch_b64: str | None, expected_sha256: str | None) -> bytes:
    if not isinstance(patch_b64, str) or not patch_b64.strip():
        raise OracleInputError("patch_b64 is empty")
    if len(patch_b64) > MAX_PATCH_B64_CHARS:
        raise OracleInputError(
            f"patch_b64 is {len(patch_b64)} chars; cap is {MAX_PATCH_B64_CHARS}. "
            "Use prepare for compression or a nearer already-pushed base; "
            "do not omit required candidate code or tests to fit."
        )
    if not isinstance(expected_sha256, str) or not _SHA256_RE.match(expected_sha256):
        raise OracleInputError("patch_sha256 must be 64 hex chars")
    try:
        raw = base64.b64decode(patch_b64.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise OracleInputError(f"patch_b64 is not valid base64: {exc}") from exc
    if raw.startswith(b"\x1f\x8b"):
        decoder = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
        try:
            raw = decoder.decompress(raw, MAX_PATCH_BYTES + 1)
        except zlib.error as exc:
            raise OracleInputError(f"invalid gzip patch: {exc}") from exc
        if len(raw) > MAX_PATCH_BYTES or decoder.unconsumed_tail:
            raise OracleInputError("uncompressed patch exceeds byte cap")
        if not decoder.eof:
            raise OracleInputError("truncated gzip patch")
        if decoder.unused_data:
            raise OracleInputError("gzip patch has trailing bytes or multiple members")
    if len(raw) > MAX_PATCH_BYTES:
        raise OracleInputError("uncompressed patch exceeds byte cap")
    if not raw:
        raise OracleInputError("decoded patch is empty")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256.lower():
        raise OracleInputError(
            f"patch sha256 mismatch: expected {expected_sha256.lower()}, got {actual}"
        )
    return raw


def _check_rel_path(path: str, *, what: str) -> None:
    if not path or "\x00" in path or "\n" in path:
        raise OracleInputError(f"{what}: empty or control characters in {path!r}")
    if "\\" in path:
        raise OracleInputError(f"{what}: backslash in {path!r}")
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise OracleInputError(f"{what}: absolute path {path!r}")
    parts = path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise OracleInputError(f"{what}: traversal or empty segment in {path!r}")


def patch_paths(patch: bytes) -> list[str]:
    """Every path a unified git patch touches, from its ``diff --git`` headers."""
    text = patch.decode("utf-8", errors="replace")
    paths: list[str] = []
    for line in text.splitlines():
        if not line.startswith("diff --git "):
            continue
        if '"' in line:
            raise OracleInputError(f"quoted/escaped path in patch header: {line!r}")
        m = _DIFF_HEADER_RE.match(line)
        if not m:
            raise OracleInputError(f"unparseable patch header: {line!r}")
        paths.extend([m.group("a"), m.group("b")])
    if not paths:
        raise OracleInputError("patch has no 'diff --git' header; not a git patch")
    return paths


def validate_patch_paths(paths: Sequence[str]) -> None:
    for path in paths:
        _check_rel_path(path, what="patch path")
        if path == HELPER_REL:
            raise OracleInputError(f"patch may not modify the gate helper {path!r}")
        if not path.startswith(ALLOWED_PATCH_ROOTS):
            raise OracleInputError(
                f"patch path {path!r} is outside {ALLOWED_PATCH_ROOTS}"
            )


def validate_patch_content(patch: bytes) -> None:
    for marker in _SECRET_MARKERS:
        if marker.search(patch):
            raise OracleInputError(
                f"patch contains a credential-shaped token ({marker.pattern!r}); "
                "the oracle takes reviewed source/test diffs only"
            )


def validate_nodeids(tests_json: str | None) -> list[str]:
    if not isinstance(tests_json, str) or not tests_json.strip():
        raise OracleInputError("tests_json is empty")
    if len(tests_json) > MAX_TESTS_JSON_CHARS:
        raise OracleInputError(f"tests_json exceeds {MAX_TESTS_JSON_CHARS} chars")
    try:
        parsed = json.loads(tests_json)
    except json.JSONDecodeError as exc:
        raise OracleInputError(f"tests_json is not JSON: {exc}") from exc
    if not isinstance(parsed, list) or not parsed:
        raise OracleInputError("tests_json must be a non-empty JSON array")
    if len(parsed) > MAX_NODEIDS:
        raise OracleInputError(f"tests_json lists {len(parsed)} ids; cap is {MAX_NODEIDS}")
    out: list[str] = []
    for item in parsed:
        if not isinstance(item, str) or not item.strip():
            raise OracleInputError(f"node id must be a non-empty string: {item!r}")
        if item != item.strip():
            raise OracleInputError(f"node id has surrounding whitespace: {item!r}")
        if item.startswith("-"):
            raise OracleInputError(f"option-like node id rejected: {item!r}")
        if any(ord(c) < 32 or ord(c) == 127 for c in item):
            raise OracleInputError(f"control character in node id: {item!r}")
        file_part = item.split("::", 1)[0]
        _check_rel_path(file_part, what="node id path")
        if not file_part.startswith("tests/") or not file_part.endswith(".py"):
            raise OracleInputError(
                f"node id must name a .py file under tests/: {item!r}"
            )
        out.append(item)
    return out


# --------------------------------------------------------------------------
# exact argv builders
# --------------------------------------------------------------------------


def build_git_apply_argv(patch_path: Path, *, check: bool) -> list[str]:
    argv = ["git", "apply"]
    if check:
        argv.append("--check")
    argv += ["--", str(patch_path)]
    return argv


def build_pytest_argv(
    nodeids: Sequence[str],
    *,
    temp_root: Path,
    junit_path: Path,
    python: str = sys.executable,
) -> list[str]:
    return [
        python, "-m", "pytest",
        "-p", "no:cacheprovider",
        "-q", "--no-header", "-rfEs",
        "--basetemp", str(temp_root / "pt"),
        "--junitxml", str(junit_path),
        "--",
        *nodeids,
    ]


def apply_patch(patch_path: Path, repo_root: Path, runner: Runner = subprocess.run) -> None:
    for check in (True, False):
        argv = build_git_apply_argv(patch_path, check=check)
        result = runner(argv, cwd=str(repo_root), check=False)
        if result.returncode != 0:
            raise OracleInputError(
                f"{' '.join(argv)} failed with exit {result.returncode}"
            )


# --------------------------------------------------------------------------
# results
# --------------------------------------------------------------------------


def junit_counts(junit_path: Path) -> dict[str, int]:
    root = ET.parse(junit_path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in counts:
            counts[key] += int(suite.get(key, "0") or 0)
    counts["passed"] = max(
        counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"], 0
    )
    return counts


def verdict(counts: dict[str, int], pytest_exit: int) -> tuple[str, str]:
    """(label, reason). Only an all-pass run with zero skips is PROOF."""
    if counts["tests"] == 0:
        return "NOT-PROOF", "no tests ran"
    if counts["failures"] or counts["errors"]:
        return "NOT-PROOF", f"{counts['failures']} failed, {counts['errors']} errored"
    if counts["skipped"]:
        return "NOT-PROOF", f"{counts['skipped']} skipped -- a skip is not a pass"
    if pytest_exit != 0:
        return "NOT-PROOF", f"pytest exited {pytest_exit}"
    return "PROOF", f"{counts['passed']} passed, 0 failed, 0 skipped"


def render_summary(result: dict) -> str:
    c = result["counts"]
    return "\n".join([
        "## Cloud pre-push oracle",
        "",
        f"- verdict: **{result['verdict']}** ({result['reason']})",
        f"- base sha: `{result['base_sha']}`",
        f"- patch sha256: `{result['patch_sha256']}` ({result['patch_bytes']} bytes)",
        f"- tests: {c['tests']} run, {c['passed']} passed, {c['failures']} failed, "
        f"{c['errors']} errored, {c['skipped']} skipped",
        f"- selected node ids: {len(result['nodeids'])}",
        "",
        "A failure or a skip is never relabelled as proof.",
        "",
    ])


# --------------------------------------------------------------------------
# subcommands
# --------------------------------------------------------------------------


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _git_stdout(argv: list[str], cwd: Path, runner: Runner) -> str:
    return runner(argv, cwd=str(cwd), check=True, capture_output=True, text=True).stdout


def cmd_prepare(args: argparse.Namespace) -> int:
    base = validate_base_sha(args.base)
    raw = Path(args.patch).read_bytes()
    if len(raw) > MAX_PATCH_BYTES:
        raise OracleInputError("uncompressed patch exceeds byte cap")
    validate_patch_paths(patch_paths(raw))
    validate_patch_content(raw)
    tests_json = json.dumps(list(args.nodeids))
    validate_nodeids(tests_json)
    b64 = base64.b64encode(raw).decode("ascii")
    if len(b64) > MAX_PATCH_B64_CHARS:
        b64 = base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii")
    sha = hashlib.sha256(raw).hexdigest()
    if decode_patch(b64, sha) != raw:
        raise OracleInputError("patch transport did not round-trip byte-exactly")
    _write_json(Path(args.out), {
        "base_sha": base,
        "patch_b64": b64,
        "patch_sha256": sha,
        "tests_json": tests_json,
    })
    print(f"[oracle] inputs written to {args.out}: base {base} patch sha256 {sha} "
          f"({len(raw)} bytes, {len(b64)} b64 chars), {len(args.nodeids)} node id(s)")
    return 0


def cmd_validate_base(args: argparse.Namespace) -> int:
    """Gate the candidate checkout: the sha input must already be full 40-hex.

    Runs from the trusted tooling checkout before ``actions/checkout`` ever
    sees ``inputs.base_sha``. Reads the env var only; touches no repo.
    """
    base = validate_base_sha(os.environ.get(ENV_BASE_SHA))
    print(f"[oracle] base_sha input accepted: {base}")
    return 0


def cmd_materialize(args: argparse.Namespace, runner: Runner = subprocess.run) -> int:
    work = Path(args.work)
    repo = Path(args.repo).resolve()
    base = validate_base_sha(os.environ.get(ENV_BASE_SHA))
    validate_head_matches(base, _git_stdout(["git", "rev-parse", "HEAD"], repo, runner))
    # Tracked content must be exactly the base; build artifacts from the dev
    # install (egg-info, caches) are untracked and irrelevant to that claim.
    status = _git_stdout(
        ["git", "status", "--porcelain", "--untracked-files=no"], repo, runner
    )
    if status.strip():
        raise OracleInputError("tracked files differ from base before the candidate is applied")
    raw = decode_patch(os.environ.get(ENV_PATCH_B64), os.environ.get(ENV_PATCH_SHA256))
    validate_patch_paths(patch_paths(raw))
    validate_patch_content(raw)
    nodeids = validate_nodeids(os.environ.get(ENV_TESTS_JSON))
    work.mkdir(parents=True, exist_ok=True)
    patch_path = work / "candidate.patch"
    patch_path.write_bytes(raw)
    _write_json(work / "manifest.json", {
        "base_sha": base,
        "patch_sha256": hashlib.sha256(raw).hexdigest(),
        "patch_bytes": len(raw),
        "nodeids": nodeids,
    })
    print(f"[oracle] base {base}; patch {len(raw)} bytes -> {patch_path}; "
          f"{len(nodeids)} node id(s)")
    return 0


def cmd_apply(args: argparse.Namespace, runner: Runner = subprocess.run) -> int:
    work = Path(args.work)
    manifest = _read_json(work / "manifest.json")
    patch_path = work / "candidate.patch"
    raw = patch_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["patch_sha256"]:
        raise OracleInputError("materialized patch no longer matches its manifest")
    apply_patch(patch_path, Path(args.repo).resolve(), runner)
    print(f"[oracle] applied {patch_path} ({len(raw)} bytes) onto {manifest['base_sha']}")
    return 0


def cmd_run(args: argparse.Namespace, runner: Runner = subprocess.run) -> int:
    work = Path(args.work)
    manifest = _read_json(work / "manifest.json")
    junit = work / "junit.xml"
    argv = build_pytest_argv(manifest["nodeids"], temp_root=work, junit_path=junit)
    print("[oracle] exec:", json.dumps(argv))
    result = runner(argv, cwd=str(Path(args.repo).resolve()), check=False)
    _write_json(work / "run.json", {"pytest_exit": int(result.returncode), "argv": argv})
    if not junit.exists():
        raise OracleInputError(f"pytest produced no JUnit at {junit}; exit {result.returncode}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    work = Path(args.work)
    manifest = _read_json(work / "manifest.json")
    run = _read_json(work / "run.json") if (work / "run.json").exists() else {"pytest_exit": -1}
    junit = work / "junit.xml"
    counts = (
        junit_counts(junit) if junit.exists()
        else {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "passed": 0}
    )
    label, reason = verdict(counts, int(run["pytest_exit"]))
    result = {**manifest, "counts": counts, "pytest_exit": run["pytest_exit"],
              "verdict": label, "reason": reason}
    _write_json(work / "result.json", result)
    summary = render_summary(result)
    print(summary)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(summary)
    return 0 if label == "PROOF" else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    prep = sub.add_parser("prepare", help="build workflow inputs JSON locally")
    prep.add_argument("--base", required=True)
    prep.add_argument("--patch", required=True)
    prep.add_argument("--out", required=True)
    prep.add_argument("nodeids", nargs="+")
    prep.set_defaults(fn=cmd_prepare)

    vb = sub.add_parser("validate-base", help="reject a non-40-hex base_sha before checkout")
    vb.set_defaults(fn=cmd_validate_base)

    for name, fn in (("materialize", cmd_materialize), ("apply", cmd_apply),
                     ("run", cmd_run), ("report", cmd_report)):
        sp = sub.add_parser(name)
        sp.add_argument("--work", required=True, help="scratch dir under runner.temp")
        sp.add_argument("--repo", default=".", help="checkout root")
        sp.set_defaults(fn=fn)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(args))
    except OracleInputError as exc:
        print(f"[oracle] REJECTED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
