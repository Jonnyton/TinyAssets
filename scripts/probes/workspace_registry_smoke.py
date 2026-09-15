"""Explicit local Linux proof, NOT a runtime provisioning coordinator.

Downloads the existing public hash-locked fixture through the namespace proxy,
then installs in a separate offline jail after every broker relay has terminated.
Run deliberately in the Linux oracle container; this is not collected by pytest.
No tenant state, credentials, connection grant or production endpoint is used.
The production coordinator still needs lease/consent/reservation/cleanup wiring.
"""

from __future__ import annotations

import json
import os
import select
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tinyassets import node_sandbox as sandbox  # noqa: E402
from tinyassets import workspace_registry as registry  # noqa: E402
from tinyassets import workspace_registry_proxy as proxy  # noqa: E402
from tinyassets import workspace_resolver as resolver  # noqa: E402


def main():
    proxy_source = Path(proxy.__file__).read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="ta-registry-proof-") as temporary:
        root = Path(temporary)
        manifests, cache, checkout = (root / name for name in ("manifests", "cache", "checkout"))
        for directory in (manifests, cache, checkout):
            directory.mkdir()
        fixture = ROOT / "tests/fixtures/workspace/requirements-locked.txt"
        (checkout / "requirements.txt").write_bytes(fixture.read_bytes())
        handles = [os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                   for path in (manifests, cache, checkout)]
        try:
            plan = resolver.read_provision_manifests(
                handles[2], python_path="requirements.txt").python
            staged = resolver.stage_python_plan(plan, manifests)
            inside = resolver.StagedManifest(
                Path("/provision/manifests") / staged.path.name, staged.digest)
            environment = resolver.resolver_environment("/tmp", "/usr/local/bin:/usr/bin:/bin")
            limits = sandbox.WorkspaceLimits().rlimit_profile()
            acquisition = {
                "argv": resolver.pip_download_argv(
                    inside, "/provision/cache", python=sys.executable),
                "env": environment, "limits": limits, "rlimit_helper": sandbox._RLIMIT_HELPER,
            }
            acquire_tail = r'''
import json, resource, subprocess, sys
settings = json.loads(sys.argv[1])
exec(settings['rlimit_helper'])
assert not _apply_rlimits(resource, 40, settings['limits'])
manager = NamespaceRegistryProxy(socket.socket(fileno=0), timeout_s=40)
try:
    manager.start()
    result = subprocess.run(settings['argv'], env=settings['env'],
        stdin=subprocess.DEVNULL, close_fds=True, capture_output=True, text=True, timeout=35)
    if result.returncode:
        raise RuntimeError('pip acquisition failed: '+result.stderr[-1000:])
    if manager.failure:
        raise RuntimeError(manager.failure)
    print(json.dumps({'acquired':True}))
finally:
    manager.close()
'''
            launcher = sandbox.BwrapLauncher().for_provision(
                sandbox.ProvisionMount(handles[0], handles[1], "acquire"))
            parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            budget = registry.TransferBudget(
                max_bytes=32*1024*1024, max_connections=32, max_active=8, timeout_s=45)
            workers = []
            process = None
            try:
                process = subprocess.Popen(
                    launcher.build_argv(
                        proxy_source + "\n" + acquire_tail, [json.dumps(acquisition)]),
                    pass_fds=launcher.pass_fds, stdin=child, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, close_fds=True, env=launcher.env("/tmp"), text=True)
                child.close()
                deadline = time.monotonic() + 45
                while process.poll() is None:
                    if time.monotonic() > deadline:
                        raise RuntimeError("acquisition deadline")
                    ready, _, _ = select.select([parent], [], [], 0.1)
                    if ready:
                        relay = registry.receive_relay(parent)
                        if relay is None:
                            break
                        if len(workers) >= 32:
                            relay.close()
                            raise RuntimeError("connection bound")
                        worker = threading.Thread(
                            target=registry.serve_registry_tunnel,
                            args=(relay, budget), daemon=True)
                        worker.start()
                        workers.append(worker)
                output, errors = process.communicate(timeout=5)
                if process.returncode:
                    raise RuntimeError(errors[-1500:])
                assert json.loads(output) == {"acquired": True}
                for worker in workers:
                    worker.join(timeout=1)
                if any(worker.is_alive() for worker in workers):
                    raise RuntimeError("broker termination unconfirmed")
                receipt = budget.snapshot()
                assert receipt.failure is None, receipt.failure
            finally:
                parent.close()
                child.close()
                budget.cancel()
                if process is not None and process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)
            # All acquisition processes and relay workers are gone. A new jail
            # sees a read-only cache and checkout, with no broker/socket stdin.
            install = sandbox.BwrapLauncher().for_workspace(sandbox.WorkspaceMount(
                f"/proc/self/fd/{handles[2]}", pass_fds=(handles[2],))).for_provision(
                    sandbox.ProvisionMount(handles[0], handles[1], "install"))
            configuration = {
                "argv": resolver.pip_offline_install_argv(
                    inside, "/provision/cache", "/workspace/.venv/bin/python"),
                "env": environment, "digest": staged.digest, "manifest": str(inside.path),
                "limits": limits, "rlimit_helper": sandbox._RLIMIT_HELPER,
            }
            offline_source = r'''
import hashlib, json, resource, subprocess, sys
from pathlib import Path
settings = json.loads(sys.argv[1])
exec(settings['rlimit_helper'])
assert not _apply_rlimits(resource, 40, settings['limits'])
assert hashlib.sha256(Path(settings['manifest']).read_bytes()).hexdigest() == settings['digest']
commands = [[sys.executable,'-m','venv','/workspace/.venv'], settings['argv'],
            ['/workspace/.venv/bin/python','-m','pytest','--version']]
for command in commands:
    result = subprocess.run(command, env=settings['env'], stdin=subprocess.DEVNULL,
        capture_output=True, text=True, close_fds=True, timeout=30)
    if result.returncode:
        raise RuntimeError('offline command failed: '+result.stderr[-1000:])
print(json.dumps({'offline':True, 'pytest':result.stdout.strip()}))
'''
            result = subprocess.run(
                install.build_argv(offline_source, [json.dumps(configuration)]),
                pass_fds=install.pass_fds, stdin=subprocess.DEVNULL, close_fds=True,
                env=install.env("/tmp"), capture_output=True, text=True, timeout=70)
            if result.returncode:
                raise RuntimeError(result.stderr[-1500:])
            print(json.dumps({
                "namespace_acquisition": True, "broker_bytes": receipt.bytes_transferred,
                "broker_connections": receipt.connections,
                "wheels": len(list(cache.glob("*.whl"))), **json.loads(result.stdout),
            }))
        finally:
            for handle in handles:
                os.close(handle)


if __name__ == "__main__":
    main()
