"""Guards for public website TinyAssets/Tiny rename surfaces."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PUBLIC_SITE_PATHS = [
    ROOT / "WebSite" / "site-react" / "app",
    ROOT / "WebSite" / "site-react" / "components",
    ROOT / "WebSite" / "site-react" / "lib",
    ROOT / "WebSite" / "site-react" / "public",
]

TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".svelte",
    ".svg",
    ".ts",
    ".tsx",
    ".txt",
}

RETIRED_PUBLIC_STRINGS = {
    "https://github.com/Jonnyton/Workflow": "legacy GitHub repository URL",
    "github.com/Jonnyton/Workflow": "legacy GitHub repository path",
    "Jonnyton/Workflow": "legacy GitHub repository slug",
    "Workflow on GitHub": "legacy GitHub link label",
    "public face of Workflow": "legacy two-name positioning",
    "public face of TinyAssets": "two-name transitional positioning",
    "Tiny is the public face of": "two-name transitional positioning",
    "one body, two names": "two-name transitional positioning",
    "Same thing, one body": "two-name transitional positioning",
    "/workflow-mark.png": "legacy public asset URL",
    "workflow-mark": "legacy public asset/class name",
    '"name":"Workflow"': "legacy JSON-LD site/org name",
    '"alternateName":"Workflow"': "legacy JSON-LD alternate name",
    'name: "Workflow"': "legacy site/org name",
    'alternateName: "Workflow"': "legacy alternate name",
}


def _site_text_files() -> list[Path]:
    files: list[Path] = []
    for base in PUBLIC_SITE_PATHS:
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                files.append(path)
    return files


def test_public_website_has_no_retired_workflow_branding():
    failures: list[str] = []

    for path in _site_text_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(ROOT)
        for needle, reason in RETIRED_PUBLIC_STRINGS.items():
            if needle in text:
                failures.append(f"{rel}: {reason}: {needle!r}")

    assert not failures, "Retired Workflow public branding found:\n" + "\n".join(failures)
