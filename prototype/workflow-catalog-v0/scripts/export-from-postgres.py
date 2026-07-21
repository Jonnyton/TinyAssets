"""Skeleton of the Postgres → catalog/ export pipeline.

Real version runs as a Supabase Edge Function on a 5-min cron
(spec #32 §2.6). This v0 skeleton reads rows from a mock queue
(a JSON file) and writes YAML files to catalog/<kind>/<id>.yaml.

Usage (v0):
    python scripts/export-from-postgres.py --queue pending_export.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CATALOG_DIR = Path(__file__).parent.parent / "catalog"


def render_node_yaml(artifact: dict, license_str: str = "CC0-1.0") -> str:
    """Allowlist-only YAML render per spec #32 §2.5.

    Every field below is explicitly allowlisted. Adding a new column
    to `nodes` does NOT auto-export it — dev must extend this function.
    """
    allowed_keys = {
        "node_id", "slug", "name", "domain", "status",
        "structural_hash", "version", "tags", "parents",
        "input_schema", "output_schema", "concept",
    }
    unexpected = set(artifact.keys()) - allowed_keys
    if unexpected:
        raise RuntimeError(
            f"render_node_yaml: unexpected fields {unexpected} — "
            "extend allowlist only after schema review"
        )

    lines = [
        "# Auto-exported from Workflow Postgres. Do not hand-edit in this repo;",
        "# submit changes via PR — they round-trip back into Postgres on merge.",
        f"license: {license_str}",
        "schema_version: 1",
        f"node_id: {artifact['node_id']}",
        f"slug: {artifact['slug']}",
        f"name: {artifact['name']}",
        f"domain: {artifact['domain']}",
        f"status: {artifact['status']}",
        f"structural_hash: {artifact['structural_hash']}",
        f"version: {artifact['version']}",
        f"tags: {json.dumps(artifact.get('tags', []))}",
        f"parents: {json.dumps(artifact.get('parents', []))}",
    ]
    if artifact.get("input_schema"):
        lines.append(f"input_schema: |\n  {json.dumps(artifact['input_schema'])}")
    if artifact.get("output_schema"):
        lines.append(f"output_schema: |\n  {json.dumps(artifact['output_schema'])}")
    if artifact.get("concept"):
        lines.append(f"concept: |\n  {json.dumps(artifact['concept'])}")
    return "\n".join(lines) + "\n"


def apply_batch(queue_path: Path) -> int:
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    count = 0
    for entry in queue:
        kind = entry["artifact_kind"]
        op = entry["operation"]
        aid = entry["artifact_id"]
        target = CATALOG_DIR / f"{kind}s" / f"{aid}.yaml"

        if op == "upsert":
            target.parent.mkdir(parents=True, exist_ok=True)
            if kind == "node":
                yaml = render_node_yaml(entry["payload"])
                target.write_text(yaml, encoding="utf-8")
            else:
                print(f"v0 skeleton: kind={kind} not yet implemented", file=sys.stderr)
                continue
            count += 1
        elif op == "delete":
            if target.exists():
                target.unlink()
            count += 1
    return count


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", type=Path, required=True)
    args = ap.parse_args()
    if not args.queue.exists():
        print(f"Queue file not found: {args.queue}", file=sys.stderr)
        return 1
    n = apply_batch(args.queue)
    print(f"Applied {n} catalog changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
