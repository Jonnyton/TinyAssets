"""Explicit local Linux proof, NOT a runtime provisioning coordinator.

Downloads the existing public hash-locked fixture through the namespace proxy,
then installs in a separate offline jail after every broker relay has terminated.
Run deliberately in the Linux oracle container; this is not collected by pytest.
No tenant state, credentials, connection grant or production endpoint is used.
The production coordinator still needs lease/consent/reservation/cleanup wiring.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tinyassets import node_sandbox as sandbox  # noqa: E402
from tinyassets import workspace_registry_proxy as proxy  # noqa: E402
from tinyassets import workspace_resolver as resolver  # noqa: E402
from tinyassets.workspace_registry_process import RegistryBrokerProcess  # noqa: E402


def main():
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--ecosystem", choices=("python", "node"), default="python")
    arguments.add_argument("--diagnose-npm", action="store_true",
                           help="disable npm retries only to expose the first transport failure")
    options = arguments.parse_args()
    ecosystem = options.ecosystem
    proxy_source = Path(proxy.__file__).read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="ta-registry-proof-") as temporary:
        root = Path(temporary)
        manifests, cache, checkout = (root / name for name in ("manifests", "cache", "checkout"))
        for directory in (manifests, cache, checkout):
            directory.mkdir()
        fixtures = ROOT / "tests/fixtures/workspace"
        if ecosystem == "python":
            (checkout / "requirements.txt").write_bytes(
                (fixtures / "requirements-locked.txt").read_bytes())
        else:
            for name in ("package.json", "package-lock.json"):
                (checkout / name).write_bytes((fixtures / "node" / name).read_bytes())
        handles = [os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                   for path in (manifests, cache, checkout)]
        try:
            admitted = resolver.read_provision_manifests(
                handles[2], python_path="requirements.txt" if ecosystem == "python" else None,
                node=ecosystem == "node")
            if ecosystem == "python":
                staged = resolver.stage_python_plan(admitted.python, manifests)
                inside = resolver.StagedManifest(
                    Path("/provision/manifests") / staged.path.name, staged.digest)
                acquisition_argv = resolver.pip_download_argv(
                    inside, "/provision/cache", python=sys.executable)
            else:
                staged = resolver.stage_node_plan(admitted.node, manifests)
                prefix = Path("/tmp/npm-acquire")
                inside = resolver.StagedNodeManifests(
                    prefix, prefix / "package.json", prefix / "package-lock.json", staged.digest)
                acquisition_argv = resolver.npm_fetch_argv(inside, "/provision/cache")
            environment = resolver.resolver_environment("/tmp", "/usr/local/bin:/usr/bin:/bin")
            if options.diagnose_npm:
                environment["NPM_CONFIG_FETCH_RETRIES"] = "0"
            limits = sandbox.WorkspaceLimits().rlimit_profile()
            acquisition = {
                "argv": acquisition_argv, "ecosystem": ecosystem, "digest": staged.digest,
                "env": environment, "limits": limits, "rlimit_helper": sandbox._RLIMIT_HELPER,
            }
            acquire_tail = r'''
import hashlib, json, resource, subprocess, sys
from pathlib import Path
settings = json.loads(sys.argv[1])
exec(settings['rlimit_helper'])
assert not _apply_rlimits(resource, 40, settings['limits'])
if settings['ecosystem'] == 'node':
    # npm ci extracts node_modules: give it its own disposable prefix, never
    # the read-only canonical manifests or the real checkout.
    prefix = Path('/tmp/npm-acquire')
    prefix.mkdir()
    blobs = [(Path('/provision/manifests') / name).read_bytes()
             for name in ('package.json', 'package-lock.json')]
    assert hashlib.sha256(b'\0'.join(blobs)).hexdigest() == settings['digest']
    for name, blob in zip(('package.json', 'package-lock.json'), blobs):
        (prefix / name).write_bytes(blob)
manager = NamespaceRegistryProxy(socket.socket(fileno=0), timeout_s=40)
try:
    manager.start()
    try:
        result = subprocess.run(settings['argv'], env=settings['env'],
            stdin=subprocess.DEVNULL, close_fds=True, capture_output=True, text=True, timeout=35)
    except subprocess.TimeoutExpired:
        # Only our fixed public fixture runs in this manual probe. Its own npm
        # log is useful diagnostics; do not copy this into production evidence.
        for log in Path('/provision/cache/_logs').glob('*debug*'):
            print(log.read_text()[-2500:], file=sys.stderr)
        raise
    if result.returncode:
        raise RuntimeError('package acquisition failed: '+result.stderr[-1000:])
    if manager.failure:
        raise RuntimeError(manager.failure)
    print(json.dumps({'acquired':True}))
finally:
    manager.close()
'''
            launcher = sandbox.BwrapLauncher().for_provision(
                sandbox.ProvisionMount(handles[0], handles[1], "acquire"))
            broker = RegistryBrokerProcess(
                max_bytes=32*1024*1024, max_connections=32, max_active=8, timeout_s=45)
            process = None
            try:
                broker.start()
                process = subprocess.Popen(
                    launcher.build_argv(
                        proxy_source + "\n" + acquire_tail, [json.dumps(acquisition)]),
                    pass_fds=launcher.pass_fds, stdin=broker.control, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, close_fds=True, env=launcher.env("/tmp"), text=True)
                broker.release_control()
                output, errors = process.communicate(timeout=40)
                receipt = broker.finish()
                if process.returncode:
                    raise RuntimeError(str(receipt) + "\n" + errors[-5000:])
                assert json.loads(output) == {"acquired": True}
                assert receipt.failure is None, receipt.failure
            finally:
                broker.close()
                if process is not None and process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)
            # All acquisition processes and relay workers are gone. A new jail
            # sees a read-only cache and checkout, with no broker/socket stdin.
            install = sandbox.BwrapLauncher().for_workspace(sandbox.WorkspaceMount(
                f"/proc/self/fd/{handles[2]}", pass_fds=(handles[2],))).for_provision(
                    sandbox.ProvisionMount(handles[0], handles[1], "install"))
            if ecosystem == "python":
                offline_argv = resolver.pip_offline_install_argv(
                    inside, "/provision/cache", "/workspace/.venv/bin/python")
                manifest = str(inside.path)
            else:
                prefix = Path("/workspace")
                install_manifests = resolver.StagedNodeManifests(
                    prefix, prefix / "package.json", prefix / "package-lock.json", staged.digest)
                offline_argv = resolver.npm_offline_install_argv(
                    install_manifests, "/provision/cache")
                manifest = "/provision/manifests"
            configuration = {
                "argv": offline_argv, "ecosystem": ecosystem,
                "env": environment, "digest": staged.digest, "manifest": manifest,
                "limits": limits, "rlimit_helper": sandbox._RLIMIT_HELPER,
            }
            offline_source = r'''
import hashlib, json, resource, subprocess, sys
from pathlib import Path
settings = json.loads(sys.argv[1])
exec(settings['rlimit_helper'])
assert not _apply_rlimits(resource, 40, settings['limits'])
if settings['ecosystem'] == 'python':
    assert hashlib.sha256(Path(settings['manifest']).read_bytes()).hexdigest() == settings['digest']
    commands = [[sys.executable,'-m','venv','/workspace/.venv'], settings['argv'],
                ['/workspace/.venv/bin/python','-m','pytest','--version']]
else:
    blobs = [(Path(settings['manifest']) / name).read_bytes()
             for name in ('package.json', 'package-lock.json')]
    assert hashlib.sha256(b'\0'.join(blobs)).hexdigest() == settings['digest']
    for name, blob in zip(('package.json', 'package-lock.json'), blobs):
        (Path('/workspace') / name).write_bytes(blob)
    commands = [settings['argv'], ['node', '-e',
        "const p=require('picocolors'); const assert=require('assert'); "
        "assert(require.resolve('picocolors').startsWith('/workspace/node_modules/')); "
        "assert.equal(p.createColors(false).green('offline-ok'),'offline-ok'); "
        "console.log('picocolors '+require('picocolors/package.json').version)"]]
for command in commands:
    result = subprocess.run(command, env=settings['env'], stdin=subprocess.DEVNULL,
        capture_output=True, text=True, close_fds=True, timeout=30)
    if result.returncode:
        raise RuntimeError('offline command failed: '+result.stderr[-1000:])
print(json.dumps({'offline':True, 'executed':result.stdout.strip()}))
'''
            result = subprocess.run(
                install.build_argv(offline_source, [json.dumps(configuration)]),
                pass_fds=install.pass_fds, stdin=subprocess.DEVNULL, close_fds=True,
                env=install.env("/tmp"), capture_output=True, text=True, timeout=70)
            if result.returncode:
                raise RuntimeError(result.stderr[-1500:])
            print(json.dumps({
                "namespace_acquisition": True, "broker_bytes": receipt.bytes_observed,
                "broker_connections": receipt.connections,
                "ecosystem": ecosystem, "diagnostic": options.diagnose_npm,
                **json.loads(result.stdout),
            }))
        finally:
            for handle in handles:
                os.close(handle)


if __name__ == "__main__":
    main()
