"""Deployment-shaped concurrency proof for agent interchange.

Run directly with:
    python -m pytest tests/load/test_agent_interchange_load.py -q -s
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

REQUESTS = 1_000
PROCESSES = 8
ACTORS = 200
MAX_AGENT_BYTES = 256 * 1024


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _component(index: int, *, blob: str = "") -> dict[str, Any]:
    config: dict[str, Any] = {"instructions": f"Component {index} stays portable."}
    if blob:
        config["opaque_extension"] = blob
    return {"kind": "load.component", "config": config}


def _definition(name: str, *, component_count: int = 1) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "name": name,
        "description": "Deployment-shaped interchange load fixture.",
        "tags": ["load", "interchange"],
        "components": {
            f"component_{index}": _component(index)
            for index in range(component_count)
        },
        "lineage": {},
        "external_origins": [],
    }


def _maximum_definition() -> dict[str, Any]:
    payload = _definition("Exact 256 KiB agent")
    payload["components"]["component_0"]["config"]["opaque_extension"] = ""
    remaining = MAX_AGENT_BYTES - len(_canonical(payload))
    payload["components"]["component_0"]["config"]["opaque_extension"] = "x" * remaining
    assert len(_canonical(payload)) == MAX_AGENT_BYTES
    return payload


def _public_import_origin_placeholder() -> dict[str, Any]:
    return {
        "kind": "agent_interchange_import",
        "source_media_type": "application/json",
        "sanitized_source_digest_algorithm": "sha256",
        "sanitized_source_digest": "0" * 64,
        "adapter_ref": "commons:load-proof-import",
        "adapter_version": "1.0.0",
        "adapter_digest_algorithm": "sha256",
        "adapter_digest": "0" * 64,
    }


def _maximum_import_definition() -> dict[str, Any]:
    payload = _definition("Exact 256 KiB imported agent")
    payload["components"]["component_0"]["config"]["opaque_extension"] = ""
    with_origin = json.loads(_canonical(payload))
    with_origin["external_origins"] = [_public_import_origin_placeholder()]
    remaining = MAX_AGENT_BYTES - len(_canonical(with_origin))
    payload["components"]["component_0"]["config"]["opaque_extension"] = (
        "x" * remaining
    )
    with_origin = json.loads(_canonical(payload))
    with_origin["external_origins"] = [_public_import_origin_placeholder()]
    assert len(_canonical(with_origin)) == MAX_AGENT_BYTES
    return payload


def _stage_adapter(source: dict[str, Any]) -> dict[str, Any]:
    rules = []
    for key in sorted(source):
        if key == "credentials":
            rules.append(
                {
                    "op": "omit",
                    "source_path": "/credentials",
                    "classification": "omitted_secret",
                    "reason_code": "secret_field",
                }
            )
        else:
            rules.append(
                {
                    "op": "copy",
                    "source_path": f"/{key}",
                    "target_path": f"/{key}",
                    "classification": "preserved",
                }
            )
    return {
        "schema_version": "agent-interchange-adapter/v1",
        "adapter_ref": "commons:load-proof-import",
        "adapter_version": "1.0.0",
        "rules": rules,
    }


def _export_adapter(portable: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "agent-interchange-adapter/v1",
        "adapter_ref": "commons:load-proof-export",
        "adapter_version": "1.0.0",
        "target_media_type": "application/vnd.load-proof.agent+json",
        "rules": [
            {
                "op": "copy",
                "source_path": f"/{key}",
                "target_path": f"/agent/{key}",
                "classification": "preserved",
            }
            for key in sorted(portable)
        ],
    }


def _stage_source(name: str, *, shape: str = "normal") -> dict[str, Any]:
    if shape == "maximum":
        source = _maximum_import_definition()
    elif shape == "components":
        source = _definition("Sixty-four component agent", component_count=64)
    else:
        source = _definition(name)
    source["credentials"] = {"api_key": "load-secret-must-not-persist"}
    return source


def _run_worker(
    base_path: str,
    seed_definition_id: str,
    seed_portable: dict[str, Any],
    export_mapping: dict[str, Any],
    worker_index: int,
) -> dict[str, Any]:
    from tinyassets.agent_interchange import (
        InterchangeConflictError,
        convert_export,
        stage_import,
    )
    from tinyassets.custom_agents import import_definition, publish_definition

    latencies: list[float] = []
    actors: set[str] = set()
    expected_conflicts = 0
    unexpected: list[str] = []
    retry_stage_ids: list[str] = []
    per_worker = REQUESTS // PROCESSES
    for local_index in range(per_worker):
        global_index = worker_index * per_worker + local_index
        actor = f"load-actor-{global_index % ACTORS:03d}"
        actors.add(actor)
        started = time.perf_counter()
        try:
            if local_index < 3:
                retry_actor = f"retry-actor-{worker_index}"
                retry_source = _stage_source(
                    "changed retry" if local_index == 2 else "identical retry"
                )
                result = stage_import(
                    base_path,
                    actor_id=retry_actor,
                    source_json=retry_source,
                    adapter=_stage_adapter(retry_source),
                    idempotency_key=f"retry-{worker_index}",
                )
                retry_stage_ids.append(result["stage_id"])
            elif global_index % 4 == 0:
                shape = "maximum" if global_index == 8 else "normal"
                source = _stage_source(f"Stage {global_index}", shape=shape)
                stage_import(
                    base_path,
                    actor_id=actor,
                    source_json=source,
                    adapter=_stage_adapter(source),
                    idempotency_key=f"stage-{global_index}",
                )
            elif global_index % 4 == 1:
                import_definition(
                    base_path,
                    author_id=actor,
                    portable_definition=seed_portable,
                    idempotency_key=f"import-{global_index}",
                )
            elif global_index % 4 == 2:
                component_count = 64 if global_index == 10 else 1
                publish_definition(
                    base_path,
                    author_id=actor,
                    payload=_definition(
                        f"Remix {global_index}", component_count=component_count
                    ),
                    idempotency_key=f"remix-{global_index}",
                )
            else:
                convert_export(
                    base_path,
                    actor_id=actor,
                    definition_id=seed_definition_id,
                    adapter=export_mapping,
                    idempotency_key=f"export-{global_index}",
                )
        except InterchangeConflictError:
            if local_index == 2:
                expected_conflicts += 1
            else:
                unexpected.append(f"unexpected conflict at {global_index}")
        except Exception as exc:  # pragma: no cover - reported to parent as load evidence
            unexpected.append(f"{global_index}:{type(exc).__name__}:{exc}")
        finally:
            latencies.append(time.perf_counter() - started)
    return {
        "latencies": latencies,
        "actors": sorted(actors),
        "expected_conflicts": expected_conflicts,
        "unexpected": unexpected,
        "retry_stage_ids": retry_stage_ids,
    }


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percentile) - 1)]


def test_agent_interchange_deployment_shaped_load(tmp_path, monkeypatch) -> None:
    from tinyassets.custom_agents import publish_definition
    from tinyassets.storage import db_path

    secret = "load-agent-interchange-purpose-key-at-least-32-bytes"
    monkeypatch.setenv("TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY", secret)
    os.environ["TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY"] = secret
    maximum = _maximum_definition()
    assert len(_canonical(maximum)) == MAX_AGENT_BYTES
    maximum_import = _maximum_import_definition()
    maximum_import["external_origins"] = [_public_import_origin_placeholder()]
    assert len(_canonical(maximum_import)) == MAX_AGENT_BYTES
    assert len(_definition("64 components", component_count=64)["components"]) == 64

    seed = publish_definition(
        tmp_path,
        author_id="load-seed-author",
        payload=_definition("Load seed"),
        idempotency_key="load-seed",
    )
    export_mapping = _export_adapter(seed["portable_definition"])
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=PROCESSES) as pool:
        results = list(
            pool.map(
                _run_worker,
                [str(tmp_path)] * PROCESSES,
                [seed["agent_definition_id"]] * PROCESSES,
                [seed["portable_definition"]] * PROCESSES,
                [export_mapping] * PROCESSES,
                range(PROCESSES),
            )
        )
    wall_seconds = time.perf_counter() - started
    latencies = [value for result in results for value in result["latencies"]]
    actors = {actor for result in results for actor in result["actors"]}
    unexpected = [item for result in results for item in result["unexpected"]]
    expected_conflicts = sum(result["expected_conflicts"] for result in results)
    throughput = REQUESTS / wall_seconds
    p95 = _percentile(latencies, 0.95)
    p99 = _percentile(latencies, 0.99)

    database = db_path(tmp_path)
    with sqlite3.connect(database) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        duplicate_idempotency = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT actor_id, operation, idempotency_key, COUNT(*) AS copies
                FROM agent_interchange_idempotency
                GROUP BY actor_id, operation, idempotency_key
                HAVING copies > 1
            )
            """
        ).fetchone()[0]
    persisted = b"".join(path.read_bytes() for path in Path(tmp_path).glob(".tinyassets.db*"))
    evidence = {
        "actors": len(actors),
        "expected_conflicts": expected_conflicts,
        "processes": PROCESSES,
        "requests": len(latencies),
        "throughput_per_second": throughput,
        "p95_seconds": p95,
        "p99_seconds": p99,
        "unexpected_errors": unexpected,
        "wall_seconds": wall_seconds,
    }
    print(json.dumps(evidence, sort_keys=True))

    assert len(latencies) == REQUESTS
    assert len(actors) == ACTORS
    assert expected_conflicts == PROCESSES
    assert not unexpected
    assert all(
        len(result["retry_stage_ids"]) == 2
        and len(set(result["retry_stage_ids"])) == 1
        for result in results
    )
    assert duplicate_idempotency == 0
    assert b"load-secret-must-not-persist" not in persisted
    assert throughput >= 3.33
    assert p95 < 2.0
    assert p99 < 3.0
