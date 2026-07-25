"""Minimal MCP (streamable-http) JSON-RPC client — stdlib only.

Just enough to call tools on a FastMCP server such as
``https://tinyassets.io/mcp``: initialize handshake, session-id tracking,
SSE-or-JSON response parsing. Every failure returns ``None`` — the village
treats an unreachable endpoint as "world unreachable", never as a crash.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2025-03-26"


class McpClient:
    def __init__(self, url: str, token: str | None = None, timeout: float = 8.0) -> None:
        self.url = url
        self.token = token
        self.timeout = timeout
        self.session_id: str | None = None
        self._next_id = 0

    # -- transport ------------------------------------------------------
    def _post(self, payload: dict) -> dict | None:
        body = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "agent-village/0.1",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.url, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                session = resp.headers.get("Mcp-Session-Id")
                if session:
                    self.session_id = session
                raw = resp.read().decode("utf-8", errors="replace")
                content_type = resp.headers.get("Content-Type", "")
        except (urllib.error.URLError, OSError, ValueError):
            return None
        return self._parse_body(raw, content_type)

    @staticmethod
    def _parse_body(raw: str, content_type: str) -> dict | None:
        if "text/event-stream" in content_type or raw.lstrip().startswith(("event:", "data:")):
            for line in raw.splitlines():
                if line.startswith("data:"):
                    try:
                        obj = json.loads(line[5:].strip())
                    except ValueError:
                        continue
                    if isinstance(obj, dict) and ("result" in obj or "error" in obj):
                        return obj
            return None
        try:
            obj = json.loads(raw)
        except ValueError:
            return None
        return obj if isinstance(obj, dict) else None

    # -- protocol -------------------------------------------------------
    def _request(self, method: str, params: dict | None = None) -> dict | None:
        self._next_id += 1
        return self._post(
            {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params or {}}
        )

    def initialize(self) -> bool:
        resp = self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "agent-village", "version": "0.1"},
            },
        )
        if not resp or "result" not in resp:
            return False
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return True

    def call_tool(self, name: str, arguments: dict) -> object | None:
        """Call a tool; return the parsed JSON payload (or raw text), else None."""
        if not self.session_id and not self.initialize():
            return None
        resp = self._request("tools/call", {"name": name, "arguments": arguments})
        if not resp:
            return None
        result = resp.get("result")
        if not isinstance(result, dict):
            return None
        if result.get("isError"):
            return None
        structured = result.get("structuredContent")
        if structured is not None:  # long payloads: text is truncated, this is full
            return structured
        content = result.get("content") or []
        texts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        if not texts:
            return None
        for text in texts:  # a single block is usually one valid JSON payload
            try:
                return json.loads(text)
            except ValueError:
                continue
        return "\n".join(t for t in texts if t)
