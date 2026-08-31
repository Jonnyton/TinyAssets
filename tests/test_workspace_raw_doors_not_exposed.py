"""Anything hanging off `ws` is public surface, underscore or not.

`ws` is handed to untrusted, user-authored node code. An earlier draft of the
byte-doors refactor factored the shared path/limit logic into METHODS named
`_read_raw` and `_write_raw`. A Codex refute review of PR #2738 pointed at them
and both claims reproduced in the real bubblewrap jail on the Linux oracle:

    ws._write_raw(['/tmp/escape'], b'pwned')   -> wrote 5 bytes OUTSIDE the root
    ws._read_raw('seed.txt', 10**12)           -> read with an unauthorised cap

They are closures now, so the text door and the binary one still share one
implementation without it being reachable from `ws` at all, and they take a
RELPATH rather than pre-split components -- the split IS the validation, so
there is no un-validated entry point left to hand parts to.

Driven as node code through a real child process, because the defect was
REACHABILITY: a test that called the closure directly would prove the opposite
of the point.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tinyassets.node_sandbox import (
    NodeSandbox,
    PlainSubprocessLauncher,
    WorkspaceLimits,
    WorkspaceMount,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    root.mkdir()
    (root / "seed.txt").write_text("hello")
    return root


def _run(workspace: Path, body: str, *, max_output: int = 4096):
    """Run `body` as the guts of a node, with `ws` bound to *workspace*."""
    mount = WorkspaceMount(
        bind_source=str(workspace),
        allowed_roots=(str(workspace.parent),),
        limits=WorkspaceLimits(max_output_bytes=max_output, max_read_bytes=max_output),
    )
    return NodeSandbox(
        launcher=PlainSubprocessLauncher().for_workspace(mount), timeout=60
    ).run_sync(
        node_id="ws-node",
        source_code="def run(state):\n" + body,
        input_state={},
        input_keys=[],
        output_keys=["result"],
        timeout=60,
        workspace=mount,
    )


def _probe(workspace: Path, expression: str, **kw):
    """Evaluate *expression* inside the node and return its reported outcome."""
    body = (
        "    try:\n"
        f"        value = {expression}\n"
        "        return {'result': {'ok': True, 'value': repr(value)[:200]}}\n"
        "    except Exception as exc:\n"
        "        return {'result': {'ok': False, 'exc': type(exc).__name__,\n"
        "                           'msg': str(exc)[:200]}}\n"
    )
    result = _run(workspace, body, **kw)
    assert result.success is True, result.error
    return result.output_state["result"]


@pytest.mark.parametrize("name", ["_read_raw", "_write_raw", "_cap_for", "_charge"])
def test_the_raw_doors_are_not_reachable_from_ws(workspace: Path, name: str) -> None:
    outcome = _probe(workspace, f"hasattr(ws, {name!r})")
    assert outcome["ok"] is True, outcome
    assert outcome["value"] == "False", (
        f"ws.{name} is reachable by node code; the underscore is a naming "
        "convention, not an access control"
    )


def test_the_escape_that_reproduced_no_longer_has_a_door(workspace: Path) -> None:
    """The exact call from the Codex finding, driven as node code."""
    outcome = _probe(workspace, "ws._write_raw(['/tmp/escape'], b'pwned')")
    assert outcome["ok"] is False, f"the escape still works: {outcome}"
    assert outcome["exc"] == "AttributeError", outcome


def test_the_public_doors_still_work(workspace: Path) -> None:
    """The refactor must not have closed the doors it was tidying."""
    body = (
        "    import base64\n"
        "    blob = bytes(range(256))\n"
        "    n1 = ws.write('out/note.txt', 'written')\n"
        "    n2 = ws.write_bytes('out/blob.bin', base64.b64encode(blob).decode('ascii'))\n"
        "    back = base64.b64decode(ws.read_bytes('out/blob.bin'))\n"
        "    return {'result': {'seed': ws.read('seed.txt'), 'n1': n1, 'n2': n2,\n"
        "                       'round_trip': back == blob}}\n"
    )
    result = _run(workspace, body)
    assert result.success is True, result.error
    payload = result.output_state["result"]
    assert payload == {"seed": "hello", "n1": 7, "n2": 256, "round_trip": True}


@pytest.mark.parametrize(
    "call",
    [
        "ws.write('/tmp/escape', 'x')",
        "ws.read('/etc/passwd')",
        "ws.read_bytes('/etc/passwd')",
        "ws.write('../escape', 'x')",
    ],
)
def test_a_path_escape_is_refused_through_every_door(workspace: Path, call: str) -> None:
    """The split is the validation, and every door must go through it."""
    outcome = _probe(workspace, call)
    assert outcome["ok"] is False, f"{call} was permitted: {outcome}"


def test_write_bytes_refuses_an_oversized_string_before_decoding(
    workspace: Path,
) -> None:
    """Codex #2738 Q4: charging after the decode still lets a node make the
    interpreter allocate the string plus its decoded copy first."""
    outcome = _probe(workspace, "ws.write_bytes('out/big.bin', 'A' * 40000)")
    assert outcome["ok"] is False, outcome
    assert "encoded chars" in outcome["msg"], outcome
    assert "budget" in outcome["msg"], outcome


def test_the_length_guard_does_not_shrink_what_a_node_may_write(
    workspace: Path,
) -> None:
    """Derived from max_output rather than configured separately, so a node can
    still hand in anything it could afford to write."""
    body = (
        "    import base64\n"
        "    raw = b'x' * 4096\n"
        "    encoded = base64.b64encode(raw).decode('ascii')\n"
        "    written = ws.write_bytes('out/full.bin', encoded)\n"
        "    return {'result': {'encoded_len': len(encoded), 'written': written}}\n"
    )
    result = _run(workspace, body, max_output=4096)
    assert result.success is True, result.error
    payload = result.output_state["result"]
    assert payload["encoded_len"] > 4096, "the encoded form is larger; that is the point"
    assert payload["written"] == 4096


def test_strict_base64_is_still_strict(workspace: Path) -> None:
    outcome = _probe(workspace, "ws.write_bytes('out/bad.bin', 'not base64!!')")
    assert outcome["ok"] is False, outcome
    assert "strict base64" in outcome["msg"], outcome
