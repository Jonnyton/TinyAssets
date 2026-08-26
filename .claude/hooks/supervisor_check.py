#!/usr/bin/env python3
"""Stop hook: surface a stagnation signal once, with the evidence for it.

The redirect half of AVO's supervisor layer. `supervisor_record.py` builds the
event stream; this reads it and, when a predicate trips, injects one message
naming what repeated and what to do instead.

Two deliberate limits:

* **It never blocks.** Output is `systemMessage` only. A supervisor that can
  stop a session is a new ratchet, and removing ratchets is why this reset
  happened. The point is to interrupt a loop with information, not to gate.
* **It fires once per finding.** A stagnation warning repeated on every Stop is
  itself the endless-process pattern it exists to break, so each finding is
  stamped in `.agents/supervisor/seen.json` and stays quiet until the shape
  changes (a commit resets the predicates, which clears the stamp naturally).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def _project_dir(payload: dict) -> Path:
    raw = payload.get("cwd") or payload.get("project_dir")
    return Path(raw) if raw else Path.cwd()


def _load_supervisor(project: Path):
    script = project / "scripts" / "supervisor.py"
    if not script.exists():
        return None
    import importlib.util

    spec = importlib.util.spec_from_file_location("supervisor_for_stop_hook", script)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return None
    return mod


def _fingerprint(findings) -> str:
    key = "|".join(
        f"{f.predicate}:{json.dumps(f.evidence, sort_keys=True)}" for f in findings
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0

    project = _project_dir(payload)
    sup = _load_supervisor(project)
    if sup is None:
        return 0

    try:
        findings = sup.check()
    except Exception:
        return 0
    if not findings:
        return 0

    seen_path = project / ".agents" / "supervisor" / "seen.json"
    fingerprint = _fingerprint(findings)
    try:
        seen = json.loads(seen_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        seen = {}
    if seen.get("fingerprint") == fingerprint:
        return 0
    try:
        seen_path.parent.mkdir(parents=True, exist_ok=True)
        seen_path.write_text(
            json.dumps({"fingerprint": fingerprint}), encoding="utf-8"
        )
    except OSError:
        pass

    lines = ["Trajectory supervisor - a loop signal, not a blocker:"]
    for f in findings:
        lines.append(f"  [{f.predicate}] {f.summary}")
        lines.append(f"      {f.redirect}")
    lines.append("  (python scripts/supervisor.py check --json for the evidence)")

    print(json.dumps({"systemMessage": "\n".join(lines)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
