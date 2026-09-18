"""Explicit Linux proof of the production composer, using public test fixtures.

No tenant, credential, connection or production endpoint is involved. Consent
and ledger composition are separately exercised by the workspace effector tests.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tinyassets import node_sandbox as sandbox  # noqa: E402
from tinyassets import workspace_fs as fs  # noqa: E402
from tinyassets.workspace_provision_execution import execute_provision  # noqa: E402
from tinyassets.workspace_provision_process import run_provision_stage  # noqa: E402
from tinyassets.workspace_resolver import read_provision_manifests  # noqa: E402


def main():
    fixtures = ROOT / "tests/fixtures/workspace"
    with tempfile.TemporaryDirectory(prefix="ta-provision-composed-") as temporary:
        root = Path(temporary)
        repo = root / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_bytes((fixtures / "requirements-locked.txt").read_bytes())
        for name in ("package.json", "package-lock.json"):
            (repo / name).write_bytes((fixtures / "node" / name).read_bytes())
        package = json.loads((repo / "package.json").read_bytes())
        package["scripts"] = {"preinstall": "touch /workspace/root-script-ran"}
        (repo / "package.json").write_text(json.dumps(package))
        originals = {name: (repo / name).read_bytes()
                     for name in ("package.json", "package-lock.json")}
        # Isolated Python startup must ignore repository import shadows.
        for name in ("pip.py", "venv.py", "sitecustomize.py"):
            (repo / name).write_text("raise RuntimeError('checkout import shadow executed')")
        handles = [os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                   for path in (root, repo)]
        try:
            manifests = read_provision_manifests(
                handles[1], python_path="requirements.txt", node=True)
            result = execute_provision(
                manifests, lease_fd=handles[0], repo_fd=handles[1],
                max_transfer_bytes=32*1024*1024, storage_bound=512*1024*1024,
                timeout_s=120, cancelled=lambda: False)
            assert result.failure is None, result
            assert not list(root.glob("provision-*")), "private scratch survived"
            for name, content in originals.items():
                assert (repo / name).read_bytes() == content
            assert not (repo / "root-script-ran").exists()
            for name in ("proof-manifests", "proof-cache"):
                handles.append(fs.create_workspace_subdir(handles[0], name))
            launcher = sandbox.BwrapLauncher().for_workspace(sandbox.WorkspaceMount(
                fs.bind_target_for(handles[1]), pass_fds=(handles[1],))).for_provision(
                    sandbox.ProvisionMount(handles[2], handles[3], "install"))
            proof = run_provision_stage(launcher, '''
import subprocess
subprocess.run(['/workspace/.venv/bin/python', '-I', '-m', 'pytest', '--version'], check=True)
subprocess.run(['node', '-e',
    "console.log(require('/workspace/node_modules/picocolors/package.json').version)"], check=True)
''', [], timeout_s=10, storage_bound=512*1024*1024,
                storage_usage=lambda: fs.measure_tree_beneath(handles[0], max_bytes=512*1024*1024),
                cancelled=lambda: False)
            assert proof.failure is None, proof.failure
            assert b"pytest 9.1.1" in proof.stdout and b"1.1.1" in proof.stdout, proof.stdout
            print(json.dumps(dict(composed=True, both_ecosystems=True,
                                  bytes_to_charge=result.bytes_to_charge,
                                  original_manifests_preserved=True, root_script_ran=False,
                                  executed=proof.stdout.decode().strip())))
        finally:
            for handle in reversed(handles):
                os.close(handle)


if __name__ == "__main__":
    main()
