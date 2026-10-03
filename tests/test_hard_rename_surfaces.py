"""Hard-rename guards for active source/config surfaces.

Historical docs and tests can mention the retired name as evidence or denylist
fixtures. Active code, config, packaging, and website sources should not.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "attic",
    "dist",
    "docs",
    "node_modules",
    "out",
    "tests",
    "venv",
    # Historical RECORDS, not active surfaces. A log or an archived snapshot is
    # evidence of what was true at the time; rewriting the old name out of it
    # would make it say something it did not say. Renaming is for things a
    # reader might still act on.
    ".cowork-uploads",
}

#: Directory-name prefixes skipped for the same reason as `.cowork-uploads`.
#: Dated handoff snapshots are archives that happen to live at the repo root.
SKIP_DIR_PREFIXES = ("COWORK_HANDOFF_",)

#: An inline marker declaring that a retired name on this line is DELIBERATE.
#:
#: Needed because not every occurrence is a straggler. `deploy-prod.yml` keeps
#: `Jonnyton/Workflow` as `historical_destination`, a back-compat branch that
#: accepts a capability secret still keyed under the pre-rename slug. Sweeping
#: it would have broken production deploys for exactly the operators who had
#: not re-keyed. A blanket file exclusion would hide any FUTURE straggler in
#: that file, so the opt-out is per line and has to be written down.
ALLOW_MARKER = "rename-allow"

TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".css",
    ".env",
    ".example",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".sql",
    ".svelte",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yml",
    ".yaml",
}

RETIRED_STRINGS = {
    "https://github.com/Jonnyton/Workflow": "legacy GitHub repository URL",
    "github.com/Jonnyton/Workflow": "legacy GitHub repository path",
    "Jonnyton/Workflow": "legacy GitHub repository slug",
    "Workflow MCP Server": "legacy MCP server label",
    "Workflow on GitHub": "legacy GitHub link label",
    "public face of Workflow": "legacy two-name positioning",
    "public face of TinyAssets": "two-name transitional positioning",
    "Tiny is the public face of": "two-name transitional positioning",
    "workflow-mark": "legacy public asset/class name",
    "workflow_v0": "legacy prototype resource name",
    "workflow-v0": "legacy prototype resource name",
    "workflow_credit": "legacy prototype currency label",
    "workflow-testnet": "legacy prototype treasury label",
    "postgresql://workflow": "legacy prototype DSN",
    ".workflow-secrets": "legacy local secret path",
    '"name":"workflow"': "legacy JSON server name",
    'name = "workflow"': "legacy config server name",
    'name: "workflow"': "legacy config server name",
}


def _active_text_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        parts = path.relative_to(ROOT).parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        if any(part.startswith(SKIP_DIR_PREFIXES) for part in parts):
            continue
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            files.append(path)
    return files


def test_active_surfaces_have_no_high_confidence_retired_workflow_names():
    failures: list[str] = []

    for path in _active_text_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(ROOT)
        # Scanned per LINE so a deliberate occurrence can be declared next to
        # itself with ALLOW_MARKER, instead of exempting a whole file and going
        # blind to real stragglers that land in it later. Line numbers also make
        # a failure directly actionable.
        for lineno, line in enumerate(text.splitlines(), start=1):
            if ALLOW_MARKER in line:
                continue
            for needle, reason in RETIRED_STRINGS.items():
                if needle in line:
                    failures.append(f"{rel}:{lineno}: {reason}: {needle!r}")

    assert not failures, (
        "Retired Workflow names found in active source/config surfaces:\n"
        + "\n".join(failures)
    )


#: The repository moved from the founder's account to the `TinyAssets` org
#: (docs/ops/org-transfer-runbook.md). GitHub redirects the old slug, but GHCR
#: does not: the image under the old owner stops receiving pushes. Matched as a
#: pattern, not a substring, because sibling repos that did NOT move share the
#: prefix (`Jonnyton/TinyAssets-catalog`, `Jonnyton/tinyassets-backups`).
MOVED_REPO_PATTERNS = {
    r"(?i)jonnyton/tinyassets(?![-\w])": "pre-org repository slug",
    r"(?i)ghcr\.io/jonnyton/": "pre-org container image path",
}

#: Records that cite the old slug as evidence of what was true then: review
#: receipts, run links and image digests in change folders, a captured session.
#: Their links still resolve through GitHub's redirect, and a digest names the
#: package it was actually pushed to; rewriting them would alter the record.
MOVED_REPO_RECORD_DIRS = (
    ("openspec", "changes"),
    ("output",),
    (".cowork-revert-patches",),
    (".agents",),
)


def test_active_surfaces_name_the_org_owned_repository():
    import re

    patterns = {re.compile(p): reason for p, reason in MOVED_REPO_PATTERNS.items()}
    failures: list[str] = []
    for path in _active_text_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(ROOT)
        if any(rel.parts[: len(d)] == d for d in MOVED_REPO_RECORD_DIRS):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if ALLOW_MARKER in line:
                continue
            for pattern, reason in patterns.items():
                if pattern.search(line):
                    failures.append(f"{rel}:{lineno}: {reason}: {line.strip()[:120]}")

    assert not failures, (
        "Pre-org repository references found in active surfaces:\n"
        + "\n".join(failures)
    )
