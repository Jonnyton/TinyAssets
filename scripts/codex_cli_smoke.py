"""Credential-free real CLI startup gate, using loopback-only fake services.

No real provider request, user home, credential, workflow or MCP is used.
The model endpoint deliberately refuses auth after CLI configuration and the
required engine-shaped MCP server have initialized.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def request_tool_roots(request: dict) -> list:
    """Read classic and Responses-lite tool envelopes without model-name rules.

    Native CLI models may use input additional_tools instead of a top-level
    tools array. Both envelopes carry the same nested namespace/spec structure.
    Absence and malformed envelopes remain failures, not an empty success.
    """
    roots = []
    found = False
    if "tools" in request:
        if not isinstance(request["tools"], list):
            raise ValueError("tools is not an array")
        roots.extend(request["tools"])
        found = True
    inputs = request.get("input", [])
    if not isinstance(inputs, list):
        raise ValueError("input is not an array")
    for item in inputs:
        if isinstance(item, dict) and item.get("type") == "additional_tools":
            if not isinstance(item.get("tools"), list):
                raise ValueError("additional_tools.tools is not an array")
            roots.extend(item["tools"])
            found = True
    if not found or not roots:
        raise ValueError("model request omitted tool specifications")
    return roots


def run_smoke(command: list[str]) -> None:
    seen: set[str] = set()
    violations: set[str] = set()
    resolved_models: set[str] = set()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            self.send_error(405)

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if self.path == "/mcp":
                if self.headers.get("Authorization") != "Bearer smoke-fixture-not-a-credential":
                    violations.add("MCP bearer header missing or changed")
                request = json.loads(body)
                method = request.get("method", "")
                seen.add(method)
                if "id" not in request:
                    self.send_response(202)
                    self.end_headers()
                    return
                result = (
                    {"protocolVersion": request["params"]["protocolVersion"],
                     "capabilities": {"tools": {}},
                     "serverInfo": {"name": "cli-smoke", "version": "1"}}
                    if method == "initialize" else {"tools": [{
                        "name": "read_graph", "description": "Read fixture graph metadata",
                        "inputSchema": {"type": "object", "properties": {},
                                        "additionalProperties": False},
                    }]}
                )
                reply = {"jsonrpc": "2.0", "id": request["id"], "result": result}
                status = 200
            else:
                seen.add("model-auth-refused")
                try:
                    request = json.loads(body)
                    resolved_model = request.get("model")
                    if not isinstance(resolved_model, str) or not resolved_model.strip():
                        violations.add("CLI did not resolve a nonempty native model")
                    else:
                        seen.add("native-model-resolved")
                        resolved_models.add(resolved_model)
                    tools = request_tool_roots(request)
                    lite = self.headers.get("x-openai-internal-codex-responses-lite") == "true"
                    if lite:
                        seen.add("code-mode-encoding")
                    pending = list(tools)
                    forbidden = {"local_shell", "shell", "exec_command", "write_stdin",
                                 "unified_exec"}
                    while pending:
                        item = pending.pop()
                        if isinstance(item, dict):
                            for key in ("name", "type"):
                                value = item.get(key)
                                if isinstance(value, str) and value.endswith("read_graph"):
                                    seen.add("engine-source-discoverable")
                                if value == "tool_search" and "tinyassets" in str(
                                    item.get("description", "")
                                ):
                                    seen.add("engine-source-discoverable")
                                if value == "exec" and lite:
                                    seen.add("code-mode-executor-advertised")
                                # Both 0.135 and 0.153 advertise native file
                                # patching independently of ShellTool. This is
                                # not shell execution; the unchanged outer jail
                                # keeps universe/auth mounts read-only.
                                if value == "apply_patch":
                                    seen.add("native-file-patch-advertised")
                                if isinstance(value, str) and value in forbidden:
                                    violations.add("shell-shaped model tool: " + value)
                            pending.extend(item.values())
                        elif isinstance(item, list):
                            pending.extend(item)
                    seen.add("model-tools-inspected")
                except (ValueError, KeyError, TypeError):
                    violations.add("model tool specs could not be inspected")
                reply = {"error": {"message": "Missing bearer authentication: CLI smoke",
                                   "type": "authentication_error"}}
                status = 401
            payload = json.dumps(reply).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory(prefix="tinyassets-cli-smoke-") as scratch:
                # Allowlist, not a denylist: never inherit provider/API tokens,
                # user config, proxies, or the host's plugin/runtime settings.
                env = {key: value for key, value in os.environ.items()
                       if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC",
                                          "PATHEXT", "TEMP", "TMP"}}
                env.update(CODEX_HOME=scratch, HOME=scratch, USERPROFILE=scratch)
                origin = f"http://127.0.0.1:{server.server_port}"
                env["TINYASSETS_ENGINE_MCP_BEARER"] = "smoke-fixture-not-a-credential"
                disabled = ["--disable", "apps", "--disable", "plugins",
                            "--disable", "remote_plugin", "--disable", "shell_tool",
                            "--disable", "unified_exec"]
                features = subprocess.run(
                    [*command, *disabled, "features", "list"], env=env, cwd=scratch,
                    capture_output=True, text=True, timeout=20, check=True,
                )
                feature_states = {parts[0]: parts[-1] for line in features.stdout.splitlines()
                                  if len(parts := line.split()) >= 3}
                for name in ("apps", "plugins", "remote_plugin", "shell_tool"):
                    if feature_states.get(name) != "false":
                        raise RuntimeError(f"Codex no longer disables {name}")
                args = [
                    *command, "exec", "--sandbox", "workspace-write",
                    "--ignore-user-config", "--ignore-rules", *disabled, "--json",
                    "--ephemeral", "--skip-git-repo-check", "-c", 'web_search="cached"',
                    "-c", 'model_provider="cli_smoke"',
                    "-c", 'model_providers.cli_smoke={'
                    f'name="CLI smoke",base_url="{origin}/v1",'
                    'wire_api="responses",requires_openai_auth=true}',
                    "-c",
                    f'projects.{json.dumps(Path(scratch).as_posix())}.trust_level="untrusted"',
                    "-c", 'mcp_servers.tinyassets={'
                    f'url="{origin}/mcp",bearer_token_env_var="TINYASSETS_ENGINE_MCP_BEARER",'
                    'required=true,default_tools_approval_mode="approve",'
                    'enabled_tools=["read_graph","write_graph","run_graph",'
                    '"read_page","write_page","converse","get_status"]}',
                    "-C", scratch, "-",
                ]
                result = subprocess.run(
                    args, input="Credential-free launch check; no response is expected.",
                    env=env, cwd=scratch, capture_output=True, text=True, timeout=45,
                )
                events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
                failures = [event.get("error", {}).get("message", "") for event in events
                            if event.get("type") == "turn.failed"]
                required = {"initialize", "tools/list", "model-auth-refused",
                            "model-tools-inspected", "native-model-resolved"}
                # CLI defers MCP specs to tool discovery. Classic requests name
                # the engine in tool_search; code-mode-only requests can hide
                # all deferred names in the isolate's ALL_TOOLS. This startup
                # check cannot prove invocation there; rendered app proof must.
                if "code-mode-encoding" in seen:
                    required.add("code-mode-executor-advertised")
                else:
                    required.add("engine-source-discoverable")
                if (result.returncode != 1 or not failures or "401" not in failures[-1]
                        or violations or not required <= seen):
                    raise RuntimeError(
                        f"Codex startup did not reach the expected auth refusal: "
                        f"exit={result.returncode}, observed={sorted(seen)}, "
                        f"violations={sorted(violations)}, "
                        f"models={sorted(resolved_models)}, "
                        f"stdout_tail={result.stdout[-500:]!r}, "
                        f"stderr_tail={result.stderr[-500:]!r}"
                    )
        finally:
            server.shutdown()
            worker.join(timeout=5)
    discovery = ("visible" if "engine-source-discoverable" in seen
                 else "unobserved-code-mode-deferred")
    print("Codex startup PASS: native model resolved, MCP bearer delivered, "
          "no shell specs in initial request, fake auth refused; "
          f"models={sorted(resolved_models)}; "
          f"engine_discovery={discovery}; "
          f"native_file_patch_advertised={'native-file-patch-advertised' in seen}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    run_smoke(parser.parse_args().command or ["codex"])
