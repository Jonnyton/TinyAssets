"""Typed provisioning binds; argv proof is not a live-jail acceptance test."""

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tinyassets import node_sandbox as sandbox


def directory(fd):
    return os.stat_result((stat.S_IFDIR | 0o700, fd, 1, 1, 1000, 1000, 0, 0, 0, 0))


def argv(mount=None, *, workspace=None, inherited=()):
    return sandbox._bwrap_argv(
        bwrap_path="/usr/bin/bwrap", exists=lambda _: False,
        realpath=lambda path: path, provision_mount=mount,
        workspace_bind=workspace, pass_fds=inherited,
    )


class ProvisionMountTests(unittest.TestCase):
    def test_invalid_shape_fails_before_launch(self):
        for values in ((True, 4, "acquire"), (3, "4", "acquire"),
                       (0, 4, "acquire"), (-1, 4, "acquire"),
                       (3, 3, "acquire"), (3, 4, "online"), (3, 4, None)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                sandbox.ProvisionMount(*values)

    def test_arbitrary_object_cannot_supply_bind_flags(self):
        class Forgery:
            phase = "acquire"

            def bind_argv(self, inherited):
                raise AssertionError("must reject before invoking supplied code")

        with self.assertRaisesRegex(ValueError, "exact typed"):
            argv(Forgery())

    def test_acquisition_has_only_canonical_manifest_and_writable_cache(self):
        mount = sandbox.ProvisionMount(30, 31, "acquire")
        with patch.object(sandbox.os, "fstat", side_effect=directory):
            result = argv(mount, inherited=(30, 31))
        self.assertEqual(result[-9:], [
            "--dir", "/provision", "--ro-bind", "/proc/self/fd/30",
            "/provision/manifests", "--bind", "/proc/self/fd/31",
            "/provision/cache", "--",
        ])
        self.assertNotIn("/workspace", result)
        self.assertIn("--unshare-all", result)
        self.assertIn("--clearenv", result)
        self.assertNotIn("--share-net", result)
        self.assertEqual(result.count("--bind"), 1)

    def test_offline_install_keeps_cache_and_manifests_read_only(self):
        mount = sandbox.ProvisionMount(30, 31, "install")
        with patch.object(sandbox.os, "fstat", side_effect=directory):
            result = argv(mount, workspace="/proc/self/fd/32", inherited=(30, 31, 32))
        self.assertEqual(result.count("--bind"), 1)
        start = result.index("--bind")
        self.assertEqual(result[start:start + 3], ["--bind", "/proc/self/fd/32", "/workspace"])
        self.assertEqual(result[-4:], ["--ro-bind", "/proc/self/fd/31", "/provision/cache", "--"])
        self.assertIn("--unshare-all", result)
        self.assertNotIn("--share-net", result)

    def test_acquisition_cannot_have_checkout(self):
        with self.assertRaisesRegex(ValueError, "excludes checkout"):
            argv(sandbox.ProvisionMount(30, 31, "acquire"),
                 workspace="/proc/self/fd/32", inherited=(30, 31, 32))

    def test_installation_requires_checkout(self):
        with self.assertRaisesRegex(ValueError, "requires checkout"):
            argv(sandbox.ProvisionMount(30, 31, "install"), inherited=(30, 31))

    def test_installation_requires_held_checkout(self):
        with self.assertRaisesRegex(ValueError, "held checkout"):
            sandbox._bwrap_argv(
                provision_mount=sandbox.ProvisionMount(30, 31, "install"),
                workspace_bind="/owned/project", allowed_workspace_roots=("/owned",),
                pass_fds=(30, 31), realpath=lambda path: path,
            )

    def test_installation_rejects_any_additional_descriptor(self):
        with self.assertRaisesRegex(ValueError, "only three distinct"):
            argv(sandbox.ProvisionMount(30, 31, "install"),
                 workspace="/proc/self/fd/32", inherited=(30, 31, 32, 33))

    def test_checkout_cannot_reuse_provisioning_descriptor(self):
        with self.assertRaisesRegex(ValueError, "only three distinct"):
            argv(sandbox.ProvisionMount(30, 31, "install"),
                 workspace="/proc/self/fd/30", inherited=(30, 31))

    def test_uninherited_descriptor_fails_before_fstat(self):
        with patch.object(sandbox.os, "fstat") as probe:
            with self.assertRaisesRegex(ValueError, "inheritance"):
                argv(sandbox.ProvisionMount(30, 31, "acquire"), inherited=(30,))
            probe.assert_not_called()

    def test_checkout_directory_is_revalidated_too(self):
        for replacement in (directory(30), os.stat_result((stat.S_IFSOCK,) + (0,) * 9)):
            def inspect(fd):
                return replacement if fd == 32 else directory(fd)
            with self.subTest(mode=replacement.st_mode):
                with patch.object(sandbox.os, "fstat", side_effect=inspect):
                    with self.assertRaises(ValueError):
                        argv(sandbox.ProvisionMount(30, 31, "install"),
                             workspace="/proc/self/fd/32", inherited=(30, 31, 32))

    def test_closed_descriptor_fails_loudly(self):
        with patch.object(sandbox.os, "fstat", side_effect=OSError("closed")):
            with self.assertRaises(OSError):
                argv(sandbox.ProvisionMount(30, 31, "acquire"), inherited=(30, 31))

    def test_non_directory_fails(self):
        for mode in (stat.S_IFREG, stat.S_IFSOCK, stat.S_IFLNK, stat.S_IFIFO):
            info = os.stat_result((mode, 1, 1, 1, 1000, 1000, 0, 0, 0, 0))
            with self.subTest(mode=mode), patch.object(sandbox.os, "fstat", return_value=info):
                with self.assertRaisesRegex(ValueError, "not a directory"):
                    argv(sandbox.ProvisionMount(30, 31, "acquire"), inherited=(30, 31))

    def test_distinct_descriptors_cannot_alias_same_directory(self):
        with patch.object(sandbox.os, "fstat", return_value=directory(10)):
            with self.assertRaisesRegex(ValueError, "alias"):
                argv(sandbox.ProvisionMount(30, 31, "acquire"), inherited=(30, 31))

    def test_unmodified_code_launcher_gets_no_provisioning_mount(self):
        self.assertFalse(any("/provision" in item for item in argv()))
        self.assertFalse(hasattr(sandbox.PlainSubprocessLauncher(), "for_provision"))

    def test_launcher_preserves_owned_fds_and_original_launcher(self):
        root = sandbox.BwrapLauncher(bwrap_path="/usr/bin/bwrap")
        workspace = root.for_workspace(sandbox.WorkspaceMount("/proc/self/fd/32", pass_fds=(32,)))
        install = workspace.for_provision(sandbox.ProvisionMount(30, 31, "install"))
        self.assertEqual(root.pass_fds, ())
        self.assertIsNone(root.provision_mount)
        self.assertEqual(workspace.pass_fds, (32,))
        self.assertEqual(install.pass_fds, (32, 30, 31))
        with patch.object(sandbox.os, "fstat", side_effect=directory):
            result = install.build_argv("print('ok')", [])
        self.assertIn("/provision/cache", result)
        self.assertEqual(result[-2:], ["-c", "print('ok')"])

    def test_cannot_reuse_provisioning_launcher_for_another_stage(self):
        acquire = sandbox.BwrapLauncher().for_provision(sandbox.ProvisionMount(30, 31, "acquire"))
        with self.assertRaisesRegex(ValueError, "fresh launcher"):
            acquire.for_provision(sandbox.ProvisionMount(33, 34, "acquire"))
        with self.assertRaisesRegex(ValueError, "rebound"):
            acquire.for_workspace(sandbox.WorkspaceMount("/proc/self/fd/32", pass_fds=(32,)))

    @unittest.skipIf(os.name != "posix", "real directory descriptors require POSIX")
    def test_real_directory_fds_and_dup_alias(self):
        with tempfile.TemporaryDirectory(prefix="ta-provision-mount-") as root:
            paths = [Path(root) / name for name in ("manifests", "cache", "checkout")]
            for path in paths:
                path.mkdir()
            descriptors = []
            try:
                for path in paths:
                    descriptors.append(os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
                manifest, cache, checkout = descriptors
                result = argv(sandbox.ProvisionMount(manifest, cache, "install"),
                              workspace=f"/proc/self/fd/{checkout}", inherited=tuple(descriptors))
                self.assertIn("/provision/cache", result)
                duplicate = os.dup(manifest)
                descriptors.append(duplicate)
                with self.assertRaisesRegex(ValueError, "alias"):
                    argv(sandbox.ProvisionMount(manifest, duplicate, "acquire"),
                         inherited=tuple(descriptors))
            finally:
                for fd in descriptors:
                    os.close(fd)


if __name__ == "__main__":
    unittest.main()
