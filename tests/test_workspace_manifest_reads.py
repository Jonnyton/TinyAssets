"""Manifest extraction composes the real parsers and existing no-follow reader.

The POSIX cohort also runs with stdlib unittest in WSL; Windows parser/contract
tests do not pretend to exercise directory-descriptor isolation.
"""

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tinyassets import workspace_fs, workspace_resolver
from tinyassets.workspace_provision import ProvisionRefused

REQ = b"# original comment\nExample_Pkg==1.0 --hash=sha256:" + b"a" * 64 + b"\n"
PACKAGE = b'{"name":"app","version":"1.0.0","scripts":{"install":"secret-command"}}'
LOCK = b'{"lockfileVersion":3,"packages":{"":{"name":"app","version":"1.0.0"}}}'


class ManifestReadContractTests(unittest.TestCase):
    def read(self, files, *, python_path="deps/requirements.txt", node=True):
        calls = []

        def reader(fd, path, *, max_bytes):
            calls.append((fd, path, max_bytes))
            if path not in files:
                raise FileNotFoundError("private host path or credential")
            return files[path]

        with patch.object(workspace_fs, "read_regular_file_beneath", side_effect=reader):
            plans = workspace_resolver.read_provision_manifests(
                37, python_path=python_path, node=node
            )
        return plans, calls

    def test_both_languages_use_same_held_descriptor_and_canonical_digests(self):
        plans, calls = self.read({
            "deps/requirements.txt": REQ, "package.json": PACKAGE, "package-lock.json": LOCK,
        })
        self.assertEqual(calls, [
            (37, "deps/requirements.txt", 256 * 1024),
            (37, "package.json", 4 * 1024 * 1024),
            (37, "package-lock.json", 4 * 1024 * 1024),
        ])
        self.assertNotIn("comment", plans.python.normalized_text)
        self.assertNotIn("secret-command", plans.node.normalized_package_json)
        self.assertEqual(plans.python.digest, hashlib.sha256(
            plans.python.normalized_text.encode()).hexdigest())
        self.assertEqual(plans.node.digest, hashlib.sha256(
            plans.node.normalized_package_json.encode() + b"\0" +
            plans.node.normalized_lockfile.encode()).hexdigest())

    def test_no_declared_dependencies_reads_nothing(self):
        plans, calls = self.read({}, python_path=None, node=False)
        self.assertEqual(calls, [])
        self.assertIsNone(plans.python)
        self.assertIsNone(plans.node)

    def test_python_only_does_not_read_node_manifests(self):
        plans, calls = self.read({"deps/requirements.txt": REQ}, node=False)
        self.assertEqual(len(calls), 1)
        self.assertIsNone(plans.node)

    def test_missing_lockfile_has_typed_safe_refusal(self):
        with self.assertRaises(ProvisionRefused) as caught:
            self.read({"package.json": PACKAGE}, python_path=None)
        self.assertEqual(caught.exception.reason, "missing_lockfile")
        self.assertNotIn("private", str(caught.exception))

    def test_reader_errors_never_copy_exception_details(self):
        with self.assertRaises(ProvisionRefused) as caught:
            self.read({}, node=False)
        self.assertEqual(caught.exception.reason, "not_regular_file")
        self.assertNotIn("private", str(caught.exception))

    def test_invalid_utf8_is_refused(self):
        with self.assertRaises(ProvisionRefused) as caught:
            self.read({"deps/requirements.txt": b"\xff"}, node=False)
        self.assertEqual(caught.exception.reason, "not_utf8")

    def test_unpinned_requirements_refuse_before_any_plan_is_returned(self):
        with self.assertRaises(ProvisionRefused):
            self.read({"deps/requirements.txt": b"example>=1.0"}, node=False)

    def test_bad_node_input_cannot_return_partial_python_success(self):
        with self.assertRaises(ProvisionRefused):
            self.read({
                "deps/requirements.txt": REQ, "package.json": b"{", "package-lock.json": LOCK,
            })

    def test_oversized_read_is_refused_even_if_reader_breaks_its_contract(self):
        with self.assertRaises(ProvisionRefused) as caught:
            self.read({"deps/requirements.txt": b"x" * (256 * 1024 + 1)}, node=False)
        self.assertEqual(caught.exception.reason, "too_large")

    def test_non_boolean_node_flag_refuses_without_reading(self):
        with patch.object(workspace_fs, "read_regular_file_beneath") as reader:
            for node in (1, "true", [], {}):
                with self.assertRaises(ValueError):
                    workspace_resolver.read_provision_manifests(37, node=node)
            reader.assert_not_called()


@unittest.skipUnless(os.name == "posix", "requires real POSIX directory descriptors")
class ManifestReadPosixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tinyassets-manifest-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.repo / "requirements.txt").write_bytes(REQ)
        self.fd = os.open(self.repo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.addCleanup(os.close, self.fd)

    def read(self, path="requirements.txt"):
        return workspace_resolver.read_provision_manifests(self.fd, python_path=path)

    def test_regular_file_and_held_descriptor_survive_repo_rename(self):
        self.repo.rename(self.root / "original")
        self.repo.mkdir()
        (self.repo / "requirements.txt").write_text("evil>=1")
        self.assertEqual(self.read().python.records[0].name, "example-pkg")
        os.fstat(self.fd)  # The reader must not close the caller's handle.

    def test_symlink_leaf_and_directory_are_refused(self):
        (self.root / "private").write_bytes(REQ)
        (self.repo / "leaf").symlink_to(self.root / "private")
        (self.repo / "parent").symlink_to(self.root, target_is_directory=True)
        for path in ("leaf", "parent/private"):
            with self.subTest(path=path), self.assertRaises(ProvisionRefused):
                self.read(path)

    def test_traversal_absolute_and_backslash_paths_are_refused(self):
        for path in ("../private", str(self.root / "private"), "..\\private"):
            with self.subTest(path=path), self.assertRaises(ProvisionRefused):
                self.read(path)

    def test_directory_and_fifo_are_refused_without_blocking(self):
        (self.repo / "directory").mkdir()
        os.mkfifo(self.repo / "pipe")
        for path in ("directory", "pipe"):
            with self.subTest(path=path), self.assertRaises(ProvisionRefused):
                self.read(path)

    def test_real_oversized_file_is_refused(self):
        (self.repo / "requirements.txt").write_bytes(b"x" * (256 * 1024 + 1))
        with self.assertRaises(ProvisionRefused):
            self.read()


if __name__ == "__main__":
    unittest.main()
