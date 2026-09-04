"""Brand-parity invariant: every committed mark matches its generator receipt."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import CheckResult, Invariant, Status

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RECEIPT = REPO_ROOT / "WebSite" / "brand" / "generated-assets.json"
ANDROID_ROOT = REPO_ROOT / "mobile" / "resources" / "android"
TEXT_SUFFIXES = {".html", ".py", ".svg", ".tsx", ".webmanifest"}
REQUIRED_SURFACES = {
    "WebSite/site-react/public/favicon.ico",
    "WebSite/site-react/public/icon.svg",
    "WebSite/site-react/public/apple-touch-icon.png",
    "WebSite/site-react/public/site.webmanifest",
    "tinyassets/desktop/app.ico",
    "assets/brand/tinyassets-app.ico",
    "assets/brand/tinyassets-app.icns",
    "mobile/resources/icon.png",
    "mobile/resources/android/mipmap-mdpi/ic_launcher.png",
    "docs/ops/play-assets/icon-512.png",
    "docs/ops/play-assets/feature-graphic-1024x500.png",
}


def _sha256(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.lower() in TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


class BrandParityInvariant(Invariant):
    name = "brand-parity"
    description = "Every website, desktop, mobile, and store mark matches one source."
    pre_commit_scope = True
    poll_interval_s = None
    auto_heal = False

    def _check(self) -> CheckResult:
        if not RECEIPT.is_file():
            return CheckResult(
                status=Status.VIOLATED,
                message="brand receipt missing; run python WebSite/brand/render_marks.py",
                evidence={"missing": [RECEIPT.relative_to(REPO_ROOT).as_posix()]},
            )

        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        generated = receipt.get("generated", {})
        problems: list[str] = []
        if receipt.get("canonical_source") != "tinyassets/desktop/icon_gen.py":
            problems.append("canonical_source is not tinyassets/desktop/icon_gen.py")
        if not re.fullmatch(r"[0-9a-f]{12}", str(receipt.get("mark_version", ""))):
            problems.append("mark_version is not a 12-hex content fingerprint")
        omitted = sorted(REQUIRED_SURFACES - set(generated))
        problems.extend(f"receipt omits required surface: {path}" for path in omitted)

        for group in ("generators", "generated"):
            entries = receipt.get(group)
            if not isinstance(entries, dict):
                problems.append(f"receipt field {group} is not an object")
                continue
            for relative, expected in entries.items():
                path = REPO_ROOT / relative
                if not path.is_file():
                    problems.append(f"missing {group[:-1]}: {relative}")
                elif _sha256(path) != expected:
                    problems.append(f"drifted {group[:-1]}: {relative}")

        actual_android = {
            path.relative_to(REPO_ROOT).as_posix()
            for path in ANDROID_ROOT.rglob("*.png")
        }
        recorded_android = {
            path
            for path in generated
            if path.startswith("mobile/resources/android/") and path.endswith(".png")
        }
        for path in sorted(actual_android ^ recorded_android):
            problems.append(f"Android receipt set differs: {path}")

        if problems:
            return CheckResult(
                status=Status.VIOLATED,
                message=(
                    f"{len(problems)} brand parity problem(s); run "
                    "python WebSite/brand/render_marks.py"
                ),
                evidence={"problems": problems},
            )
        return CheckResult(
            status=Status.OK,
            message=f"{len(generated)} generated brand artifact(s) match",
            evidence={"checked": len(generated)},
        )
