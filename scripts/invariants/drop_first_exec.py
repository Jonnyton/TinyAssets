"""Drop-first exec invariant: no repo-authored bare exec into the daemon.

Wraps ``scripts/check_drop_first_exec.py``. Every ``docker exec`` into the
daemon container that this repository authors must go through
``/usr/local/libexec/ta-op <mode>``, with the mode declared in
``deploy/native/ta_op_modes.tsv`` — the same file the runtime's mode table is
kept in parity with (``tests/test_ta_op_modes.py``).

No auto-heal: rewriting an operational callsite is a judgement about which
mode it is, and a wrong guess reaches production. The check names the file,
line and reason; a human or an agent picks the mode.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from . import CheckResult, Invariant, Status

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHECKER = REPO_ROOT / "scripts" / "check_drop_first_exec.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_drop_first_exec_for_invariant", CHECKER,
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class DropFirstExecInvariant(Invariant):
    name = "drop-first-exec"
    description = (
        "Repo-authored daemon execs go through /usr/local/libexec/ta-op with a "
        "declared mode."
    )
    pre_commit_scope = True
    poll_interval_s = None
    auto_heal = False

    def _check(self) -> CheckResult:
        if not CHECKER.exists():
            return CheckResult(
                status=Status.SKIPPED,
                message=f"check_drop_first_exec.py not found at {CHECKER}",
            )
        mod = _load_checker()
        try:
            modes = mod.load_modes()
        except (OSError, ValueError) as exc:
            return CheckResult(
                status=Status.VIOLATED,
                message=f"the ta-op mode table is unreadable: {exc}",
            )
        findings: list[str] = []
        for path in mod.tracked_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            rel = path.relative_to(REPO_ROOT)
            findings += [
                f"{rel}:{ln}: {why}" for ln, why in mod.scan_text(text, modes)
            ]

        if findings:
            return CheckResult(
                status=Status.VIOLATED,
                message=f"{len(findings)} unwrapped daemon exec(s)",
                evidence={"violations": findings},
            )
        return CheckResult(
            status=Status.OK,
            message=f"all daemon execs wrapped ({len(modes)} modes declared)",
        )
