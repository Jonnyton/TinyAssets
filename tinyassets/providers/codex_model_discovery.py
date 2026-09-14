"""Bounded Codex app-server metadata protocol, never a writer or host session.

Only initialize/initialized/model/list are sent. The caller supplies an owned
credential snapshot environment and clean cwd, and retains authority checks.
No thread/turn, implicit inference, shell, stderr relay or partial catalogue.
"""

import asyncio
import json
from datetime import datetime, timezone

from tinyassets.exceptions import ProviderError
from tinyassets.providers.native_catalogue import NativeCatalogue, NativeModel

_MAX_BYTES = 4 * 1024 * 1024
_MAX_MODELS = 4096
_MAX_PAGES = 64


def parse_model_page(result):
    if type(result) is not dict or type(result.get("data")) is not list:
        raise ValueError("invalid native model page")
    cursor = result.get("nextCursor")
    if cursor is not None and (type(cursor) is not str or not cursor or len(cursor) > 4096):
        raise ValueError("invalid native model cursor")
    models, defaults = [], []
    for row in result["data"]:
        if type(row) is not dict or type(row.get("isDefault", False)) is not bool:
            raise ValueError("invalid native model entry")
        # `model` is the executable ID; `id` and displayName are not substitutes.
        # Missing modalities remain unknown, not fabricated account evidence.
        modalities = row.get("inputModalities", [])
        if type(modalities) is not list or any(type(item) is not str for item in modalities):
            raise ValueError("invalid native input modalities")
        model = NativeModel(row.get("model"), frozenset(modalities), row.get("hidden", False))
        models.append(model)
        if row.get("isDefault", False):
            defaults.append(model.model_id)
    return models, defaults, cursor


async def read_codex_catalogue(argv, *, env, cwd, timeout=30, spawn_kwargs=None):
    """Read the complete bounded list or fail with sanitized fixed prose.

    Resource ceilings are transport guards, never silent list truncation. New
    optional fields and notifications are tolerated; invalid required facts,
    duplicate models, repeated cursors and upstream errors refuse the result.
    """
    proc = None
    try:
        async with asyncio.timeout(timeout):
            proc = await asyncio.create_subprocess_exec(
                *argv, env=env, cwd=cwd, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                limit=_MAX_BYTES, **(spawn_kwargs or {}),
            )
            consumed = 0

            async def send(message):
                proc.stdin.write((json.dumps(message, separators=(",", ":")) + "\n").encode())
                await proc.stdin.drain()

            async def response(request_id):
                nonlocal consumed
                while True:
                    line = await proc.stdout.readline()
                    consumed += len(line)
                    if not line or consumed > _MAX_BYTES:
                        raise ValueError("native discovery incomplete or oversized")
                    message = json.loads(line)
                    if type(message) is not dict:
                        raise ValueError("invalid native discovery envelope")
                    if "id" not in message and type(message.get("method")) is str:
                        continue
                    if (type(message.get("id")) is not int or message["id"] != request_id
                            or "error" in message or type(message.get("result")) is not dict):
                        raise ValueError("unexpected native discovery response")
                    return message["result"]

            await send({"method": "initialize", "id": 0, "params": {
                "clientInfo": {"name": "tinyassets_model_discovery", "version": "1"},
            }})
            await response(0)
            await send({"method": "initialized", "params": {}})
            models, defaults, cursors = [], [], set()
            cursor = None
            for request_id in range(1, _MAX_PAGES + 1):
                params = {"limit": 100, "includeHidden": True}
                if cursor is not None:
                    params["cursor"] = cursor
                await send({"method": "model/list", "id": request_id, "params": params})
                page, recommended, cursor = parse_model_page(await response(request_id))
                models.extend(page)
                defaults.extend(recommended)
                if len(models) > _MAX_MODELS or len(defaults) > 1:
                    raise ValueError("native catalogue limit or conflicting defaults")
                if cursor is None:
                    return NativeCatalogue(
                        tuple(models), defaults[0] if defaults else None,
                        datetime.now(timezone.utc),
                    )
                if cursor in cursors:
                    raise ValueError("native catalogue cursor repeated")
                cursors.add(cursor)
            raise ValueError("native catalogue page limit exceeded")
    except (OSError, ValueError, TimeoutError, asyncio.LimitOverrunError):
        # Never relay process output, errors, paths or account material.
        raise ProviderError("native model discovery unavailable") from None
    finally:
        if proc is not None:
            if proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            await proc.wait()
