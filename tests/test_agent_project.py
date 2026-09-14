"""Inert source-project conformance; runnable without optional test dependencies."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import unittest

from tinyassets.agent_project import (
    ProjectValidationError,
    export_project,
    inspect_project,
)
from tinyassets.custom_agents import _fingerprint, _normalize_definition_payload


class SourceProjectTests(unittest.TestCase):
    def setUp(self):
        self.native = {
            "schema_version": 1, "name": "Public fixture",
            "components": {
                "transform": {"kind": "future.transform", "config": {"factor": 2}},
                "note": {"kind": "unfamiliar.note", "config": {"text": "Retain me"}},
            },
        }
        self.sources = {
            "src/transform.py": "raise RuntimeError('MUST NEVER EXECUTE ON IMPORT')\n",
            "fixtures/input.json": '{"value": 3}\n',
        }

    def package(self, **kwargs):
        return export_project(
            self.native, sources=kwargs.pop("sources", self.sources),
            entry_points={"fixture": "src/transform.py"},
            runtime_requirements=["branch-code-node"], **kwargs,
        )

    def test_round_trip_preserves_native_unknown_components_and_exact_source(self):
        raw = self.package()
        report = inspect_project(raw)
        normalized = _normalize_definition_payload(self.native)
        self.assertEqual(report["portable_definition"], normalized)
        self.assertEqual(report["native_fingerprint"], _fingerprint(normalized))
        package = json.loads(raw)
        sources = {k: v for k, v in package["files"].items() if k != "agent.json"}
        self.assertEqual(sources, self.sources)
        self.assertEqual(export_project(
            report["portable_definition"], sources=sources,
            entry_points=package["descriptor"]["entry_points"],
            runtime_requirements=package["descriptor"]["runtime_requirements"],
        ), raw)
        self.assertFalse(report["compatibility"]["executable"])
        self.assertIsNone(report["compatibility"]["runtime_requirements_satisfied"])

    def test_edit_changes_digest_without_changing_native_fingerprint(self):
        before = inspect_project(self.package())
        sources = {**self.sources, "src/transform.py": "def run(state): return {'value': 9}\n"}
        after = inspect_project(self.package(sources=sources))
        self.assertNotEqual(before["project_digest"], after["project_digest"])
        self.assertEqual(before["native_fingerprint"], after["native_fingerprint"])

    def test_tamper_missing_extra_or_false_lock_refuses(self):
        package = json.loads(self.package())
        mutations = [
            lambda p: p["files"].update({"src/transform.py": "changed"}),
            lambda p: p["files"].pop("fixtures/input.json"),
            lambda p: p["files"].update({"extra.txt": "undeclared"}),
            lambda p: p["lock"].update({"project_digest": "0" * 64}),
            lambda p: p["lock"].update({"native_fingerprint": "0" * 64}),
            lambda p: p["lock"]["inventory"][0].update({"bytes": True}),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                changed = copy.deepcopy(package)
                mutate(changed)
                with self.assertRaises(ProjectValidationError):
                    inspect_project(json.dumps(changed))

    def test_unsafe_paths_and_collisions_refuse(self):
        bad_paths = [
            "/absolute", "../escape", "a/../b", "./a", "a//b", "a/",
            "C:/drive", r"src\file.py", "\0bad", "aux.txt", "a/NUL",
            "a/file.", "a/file ", "e\u0301.txt", "a:stream", "\ud800",
        ]
        for path in bad_paths:
            with self.subTest(path=repr(path)), self.assertRaises(ProjectValidationError):
                self.package(sources={**self.sources, path: "fixture"})
        for extra in [
            {"SRC/transform.py": "collision"},
            {"src": "file"},
            {"Straße/a.txt": "a", "STRASSE/A.txt": "b"},
        ]:
            with self.subTest(extra=extra), self.assertRaises(ProjectValidationError):
                self.package(sources={**self.sources, **extra})

    def test_duplicate_keys_and_nonfinite_json_refuse(self):
        for raw in [
            '{"schema_version":1,"schema_version":1}',
            '{"value":NaN}', '{"value":Infinity}',
        ]:
            with self.subTest(raw=raw), self.assertRaises(ProjectValidationError):
                inspect_project(raw)

    def test_private_definition_binding_and_source_refuse_without_echoing_value(self):
        sentinel = "private-sentinel-that-must-not-appear"
        for field in ["credentials", "conversations", "api_key"]:
            native = {**self.native, field: sentinel}
            with self.subTest(field=field), self.assertRaises(ProjectValidationError) as caught:
                export_project(native, sources=self.sources)
            self.assertNotIn(sentinel, str(caught.exception))
        with self.assertRaises(ProjectValidationError):
            self.package(sources={**self.sources, "bindings.json": '{"api_key":"private"}'})
        with self.assertRaises(ProjectValidationError):
            self.package(sources={**self.sources, "notes.txt": "Bearer secret-value"})

    def test_unknown_representation_missing_entry_binary_and_budget_refuse(self):
        p = json.loads(self.package())
        p["schema_version"] = "future/v99"
        with self.assertRaises(ProjectValidationError):
            inspect_project(json.dumps(p))
        with self.assertRaises(ProjectValidationError):
            self.package(sources={})
        with self.assertRaises(ProjectValidationError):
            self.package(sources={**self.sources, "blob": b"binary"})
        with self.assertRaises(ProjectValidationError):
            self.package(sources={**self.sources, "large.txt": "x" * (1024 * 1024)})
        with self.assertRaises(ProjectValidationError):
            self.package(sources={**self.sources, "agent.json": "{}"})

    def test_descriptor_inventory_digest_matches_javascript_closed_grammar(self):
        if shutil.which("node") is None:
            self.skipTest("Node is unavailable; cross-language digest proof pending")
        package = json.loads(self.package(sources={
            **self.sources, "src/😀.txt": "line\né\u2028😀",
        }))
        program = r"""
const crypto = require('node:crypto');
const fs = require('node:fs');
const p = JSON.parse(fs.readFileSync(0, 'utf8'));
function canonical(v) {
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
  if (v && typeof v === 'object') return '{' + Object.keys(v).sort().map(
    k => JSON.stringify(k) + ':' + canonical(v[k])).join(',') + '}';
  return JSON.stringify(v);
}
process.stdout.write(crypto.createHash('sha256').update(canonical({
  descriptor:p.descriptor,inventory:p.lock.inventory
})).digest('hex'));
"""
        got = subprocess.run(
            ["node", "-e", program], input=json.dumps(package),
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(got.stdout, package["lock"]["project_digest"])
        for item in package["lock"]["inventory"]:
            data = package["files"][item["path"]].encode()
            self.assertEqual(item["sha256"], hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    unittest.main()
