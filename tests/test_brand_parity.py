"""The committed brand exports must stay bound to their one drawing source."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RECEIPT = REPO / "WebSite" / "brand" / "generated-assets.json"


def _sha256(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.lower() in {".html", ".py", ".svg", ".tsx", ".webmanifest"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def test_every_brand_export_matches_the_canonical_receipt() -> None:
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    assert receipt["canonical_source"] == "tinyassets/desktop/icon_gen.py"
    assert len(receipt["mark_version"]) == 12

    for group in ("generators", "generated"):
        for relative, expected in receipt[group].items():
            path = REPO / relative
            assert path.is_file(), f"missing {group[:-1]}: {relative}"
            assert _sha256(path) == expected, (
                f"brand drift: {relative}; run python WebSite/brand/render_marks.py"
            )

    actual_android = {
        path.relative_to(REPO).as_posix()
        for path in (REPO / "mobile" / "resources" / "android").rglob("*.png")
    }
    recorded_android = {
        path
        for path in receipt["generated"]
        if path.startswith("mobile/resources/android/") and path.endswith(".png")
    }
    assert actual_android == recorded_android
