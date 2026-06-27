"""Mirror-parity invariant: canonical `tinyassets/**` == plugin mirror.

Iterates every canonical file under `tinyassets/` and compares bytes
against the paired plugin-mirror path under
`packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/`.
Mismatch → VIOLATED with a list of diverged paths.

Pre-commit scope (hook invokes it on staged-only set). Non-pre-commit
mode scans the entire tree for diagnostic use. Auto-heal is disabled:
fixing mirror drift requires rebuilding the plugin, which is too
heavyweight for a silent background heal.
"""

from __future__ import annotations

import filecmp
from pathlib import Path

from . import CheckResult, HealResult, Invariant, Status

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CANONICAL_ROOT = REPO_ROOT / "tinyassets"
MIRROR_ROOT = (
    REPO_ROOT
    / "packaging"
    / "claude-plugin"
    / "plugins"
    / "tinyassets-universe-server"
    / "runtime"
    / "tinyassets"
)

SCAN_SUFFIXES = (".py", ".md", ".json", ".toml")


class MirrorParityInvariant(Invariant):
    name = "mirror-parity"
    description = "Canonical tinyassets/ == plugin-mirror byte-for-byte."
    pre_commit_scope = True
    poll_interval_s = None  # diagnostic / pre-commit only
    auto_heal = False

    def _check(self) -> CheckResult:
        if not CANONICAL_ROOT.is_dir():
            return CheckResult(
                status=Status.SKIPPED,
                message=f"canonical root not found: {CANONICAL_ROOT}",
            )
        if not MIRROR_ROOT.is_dir():
            return CheckResult(
                status=Status.SKIPPED,
                message=f"mirror root not found: {MIRROR_ROOT}",
            )

        mismatches: list[str] = []
        checked = 0
        for canon_path in CANONICAL_ROOT.rglob("*"):
            if not canon_path.is_file():
                continue
            if canon_path.suffix not in SCAN_SUFFIXES:
                continue
            rel = canon_path.relative_to(CANONICAL_ROOT)
            mirror_path = MIRROR_ROOT / rel
            if not mirror_path.exists():
                # Canonical-only file — acceptable (packaging build
                # creates mirror later). Not a mismatch.
                continue
            checked += 1
            if not filecmp.cmp(canon_path, mirror_path, shallow=False):
                mismatches.append(str(rel).replace("\\", "/"))

        if mismatches:
            return CheckResult(
                status=Status.VIOLATED,
                message=(
                    f"{len(mismatches)} file(s) diverge between canonical and "
                    f"mirror (out of {checked} checked)"
                ),
                evidence={"mismatches": mismatches, "checked": checked},
            )
        return CheckResult(
            status=Status.OK,
            message=f"all {checked} canonical file(s) mirror-matched",
            evidence={"checked": checked},
        )

    def _heal(self) -> HealResult:
        # auto_heal = False, so the base class short-circuits this.
        # Kept as placeholder for documentation completeness.
        return HealResult(
            healed=False,
            message="mirror-parity heal is manual; re-run the packaging build",
        )
