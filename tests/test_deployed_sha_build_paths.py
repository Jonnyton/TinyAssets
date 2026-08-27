r"""`deployed_sha.BUILD_PATHS` must mirror `build-image.yml`'s `paths:` filter.

`deployed_sha.py` reports whether production is behind `main`. Counting every
commit as drift made it cry wolf permanently: a docs or CI commit CANNOT reach
production, because `build-image.yml` is path-filtered, so nothing is built and
nothing is deployed. On 2026-08-27 it reported 9 undeployed commits, all of
which touched zero build paths.

It now splits the count -- but only correctly while its path list matches the
workflow's. If the workflow adds a build input and this list does not, a real
deploy gap is reported as "nothing to deploy", which is the dangerous direction:
Hard Rule 14 exists because five PRs once landed and none shipped.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "build-image.yml"

_SPEC = importlib.util.spec_from_file_location(
    "deployed_sha_for_test", REPO_ROOT / "scripts" / "deployed_sha.py"
)
assert _SPEC is not None and _SPEC.loader is not None
deployed_sha = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = deployed_sha
_SPEC.loader.exec_module(deployed_sha)


def _workflow_paths() -> set[str]:
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # `on` is parsed as the boolean True by YAML 1.1 unless quoted.
    on = wf.get("on", wf.get(True))
    return set(on["push"]["paths"])


def test_the_workflow_still_declares_a_path_filter() -> None:
    # Guards the guard: if the filter is removed, every commit builds and this
    # whole comparison is meaningless -- fail loudly rather than pass vacuously.
    assert _workflow_paths(), "build-image.yml declares no push paths filter"


def test_build_paths_cover_every_workflow_path() -> None:
    missing = []
    for raw in _workflow_paths():
        # `tinyassets/**` in the workflow == `tinyassets/` as a git pathspec.
        normalized = raw.replace("/**", "/")
        if not any(
            normalized == known or normalized.rstrip("/") == known.rstrip("/")
            for known in deployed_sha.BUILD_PATHS
        ):
            missing.append(raw)
    assert not missing, (
        "build-image.yml builds on these paths but deployed_sha.BUILD_PATHS "
        f"omits them, so a real deploy gap would read as 'nothing to deploy': {missing}"
    )
