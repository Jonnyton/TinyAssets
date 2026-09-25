"""A throwaway git repo shaped like the deploy chain sees this one.

Shared by the runtime-classifier, deployed_sha and release-reconcile tests so
all three judge the same kinds of history: a Dockerfile with context and stage
copies, a host-uptime manifest, a daemon module that serves PLAN.md excerpts,
and docs next to them.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

SERVED_LIMIT = 200

DOCKERFILE = """\
FROM python:3.11-slim AS builder
COPY scripts/codex_cli_smoke.py /tmp/codex_cli_smoke.py
WORKDIR /build
COPY pyproject.toml ./
COPY PLAN.md ./
COPY tinyassets/ ./tinyassets/
RUN echo building && \\
    echo done
FROM python:3.11-slim
COPY --from=builder /build/tinyassets /app/tinyassets
COPY --from=builder /build/PLAN.md /app/PLAN.md
COPY --chown=1001:1001 scripts/_canary_common.py /app/scripts/_canary_common.py
COPY ["data/world_rules.lp", "/app/data/world_rules.lp"]
"""

HOST_MANIFEST = """\
#!/usr/bin/env bash
RUNTIME_FILES=(
    deploy/backup.sh
    scripts/watchdog.py
)
"""

UNIVERSE = f"""\
_CHANGE_LOOP_PLAN_HEADINGS = (
    "Scoping Rules",
    "Module: Daemon Platform",
)


def _shorten(value, max_chars):
    text = "" if value is None else str(value)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 15)].rstrip() + "\\n...[truncated]"


def _change_loop_plan_context():
    sections = {{}}
    for heading in _CHANGE_LOOP_PLAN_HEADINGS:
        sections[heading] = _shorten(heading, {SERVED_LIMIT})
    return sections
"""

SCOPING_BODY = "Served opening paragraph. " * 20  # well past SERVED_LIMIT


def plan(*, scoping_tail: str = "tail", unserved: str = "unserved", daemon: str = "daemon") -> str:
    return (
        "# Plan\n\n"
        "## Scoping Rules\n\n"
        f"{SCOPING_BODY}\n\n{scoping_tail}\n\n"
        "## Unserved Module\n\n"
        f"{unserved}\n\n"
        "## Module: Daemon Platform\n\n"
        f"{daemon}\n"
    )


WORKFLOWS: dict[str, str] = {
    ".github/workflows/build-image.yml": (
        "name: Build and publish image\n"
        "on:\n  push:\n    paths:\n      - 'tinyassets/**'\n"
    ),
    # Flow-list trigger + the droplet's host-mutation group + the SSH key.
    ".github/workflows/deploy-prod.yml": (
        "name: Deploy prod\n"
        "on:\n  workflow_run:\n    workflows: [\"Build and publish image\"]\n"
        "    types: [completed]\n"
        "concurrency:\n  group: production-host-mutation\n"
        "jobs:\n  deploy:\n    steps:\n"
        "      - run: echo \"${{ secrets.DO_SSH_KEY }}\"\n"
        "      - run: python scripts/prepare_state.py --out state.json\n"
    ),
    # Block-list trigger, chained on the deploy, holds the SSH key.
    ".github/workflows/install-host-services.yml": (
        "name: Install host services\n"
        "on:\n  workflow_run:\n    workflows:\n      - Deploy prod\n"
        "    types: [completed]\n"
        "jobs:\n  install:\n    steps:\n"
        "      - run: echo \"${{ secrets.DO_SSH_KEY }}\"\n"
    ),
    # Chained on the deploy, but a pure observer: no host credential.
    ".github/workflows/uptime-canary.yml": (
        "name: Uptime canary\n"
        "on:\n  workflow_run:\n    workflows: [\"Deploy prod\"]\n"
        "jobs:\n  probe:\n    steps:\n      - run: echo probe\n"
    ),
    ".github/workflows/tests.yml": (
        "name: Tests\non:\n  push:\njobs:\n  t:\n    steps:\n      - run: pytest\n"
    ),
}

BASE_FILES: dict[str, str] = {
    **WORKFLOWS,
    "Dockerfile": DOCKERFILE,
    ".dockerignore": "docs/\n",
    "pyproject.toml": "[project]\nname = 'x'\n",
    "PLAN.md": plan(),
    "tinyassets/__init__.py": "",
    "tinyassets/app.py": "VERSION = 1\n",
    "tinyassets/api/universe.py": UNIVERSE,
    "scripts/codex_cli_smoke.py": "print('smoke')\n",
    "scripts/_canary_common.py": "TOKEN = 1\n",
    "scripts/watchdog.py": "WATCH = 1\n",
    "scripts/unrelated_tool.py": "TOOL = 1\n",
    # The prepare_expected_instance_state.py -> cloud_only_preflight.py shape:
    # deploy-prod runs the first; its output is installed on the host, and it
    # imports a helper through the sys.path-insert idiom.
    "scripts/prepare_state.py": (
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
        "from preflight_helper import resolve_expected  # noqa: E402\n"
        "import json\n"
        "print(json.dumps(resolve_expected()))\n"
    ),
    "scripts/preflight_helper.py": "def resolve_expected():\n    return {'id': 1}\n",
    "data/world_rules.lp": "rule.\n",
    "deploy/install-host-uptime-services.sh": HOST_MANIFEST,
    "deploy/compose.yml": "services: {}\n",
    "docs/notes.md": "notes\n",
    "tests/test_x.py": "def test_x():\n    pass\n",
    "AGENTS.md": "agents\n",
}


class Repo:
    def __init__(self, root: Path) -> None:
        self.root = root

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()

    def commit(self, message: str, files: dict[str, str | None]) -> str:
        for rel, content in files.items():
            path = self.root / rel
            if content is None:
                self.git("rm", "-q", "--", rel)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
            self.git("add", "--", rel)
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def rename(self, message: str, old: str, new: str) -> str:
        (self.root / new).parent.mkdir(parents=True, exist_ok=True)
        self.git("mv", old, new)
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")


def make_repo(root: Path, extra: dict[str, str] | None = None) -> tuple[Repo, str]:
    root.mkdir(parents=True, exist_ok=True)
    repo = Repo(root)
    repo.git("init", "-q", "-b", "main")
    repo.git("config", "user.email", "proof@example.invalid")
    repo.git("config", "user.name", "Runtime Proof")
    repo.git("config", "core.autocrlf", "false")
    base = repo.commit("base", {**BASE_FILES, **(extra or {})})
    return repo, base
