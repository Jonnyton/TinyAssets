"""Synthetic user graph: real spawned broker -> HTTP hops -> sandboxed code.

Only the child's network fixture is replaced. Production IPC, vault resolution,
authority, effects and code execution remain real. Loopback/plaintext
TLS is explicitly not public TLS or live deployment proof.
"""

import hashlib
import json
import multiprocessing
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from tests.test_authenticated_external_call_effector import _setup
from tests.test_effects_at_node_time import _effect_node, _linear, _provider_for
from tests.test_http_redirect_chain import (
    KEY,
    SIGNATURE,
    SOURCE,
    _driver,
    _redirect,
    chain,  # noqa: F401 -- pytest fixture
)
from tinyassets.branches import NodeDefinition
from tinyassets.effectors import EffectChain, EffectFailedError
from tinyassets.effectors import authenticated_external_call as aec
from tinyassets.graph_compiler import compile_branch
from tinyassets.storage import outbound_connections as oc


def _fixture_worker(channel, config, address):
    """Test-only spawn target; never made configurable in production."""
    fixture = SimpleNamespace(
        server_address=address,
        state={"dns": [], "sockets": []},
    )
    with patch.object(oc, "_SsrfHardenedHttpDriver", lambda: _driver(fixture)):
        oc._run_proxy_worker(channel, "credential_broker_v1", config, "grant-http", ("GET",))


def _spawn_proxy(config, address):
    context = multiprocessing.get_context("spawn")
    client, child = context.Pipe(duplex=True)
    worker = context.Process(target=_fixture_worker, args=(child, config, address), daemon=True)
    worker.start()
    child.close()
    try:
        assert client.poll(30), "fixture worker did not start"
        assert oc._receive_message(client) == {"op": "ready"}
    except BaseException:
        client.close()
        worker.terminate()
        worker.join(5)
        raise
    proxy = oc.ScopedConnectionProxy(
        grant_id="grant-http",
        provider="http",
        destination="api.example.com",
        scopes=("GET",),
        _channel=oc._ProxyChannel(client, worker),
    )
    return proxy, worker


@pytest.mark.parametrize("echo_capability", [False, True])
def test_redirect_effect_reaches_real_code_through_spawned_broker(
    tmp_path,
    monkeypatch,
    chain,  # noqa: F811 -- imported pytest fixture
    echo_capability,
):
    monkeypatch.setenv("TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED", "1")
    _, universe, database = _setup(tmp_path, endpoints=[SOURCE], scopes=("GET",), token=KEY)
    text = "".join(f"record {i}: useful downloaded text\n" for i in range(400))
    if echo_capability:
        text += SIGNATURE
    chain.state["responses"] = [
        _redirect(f"https://cdn.example.com/blob?sig={SIGNATURE}"),
        {"body": text.encode(), "headers": [("Set-Cookie", "private-cookie")]},
    ]
    runtime = tmp_path / "broker-runtime"
    config = {
        "allow_test_fixtures": False,
        "allow_http_connections": True,
        "ledger_db_path": str(database),
        "universe_dir": str(universe),
        "provider": "http",
        "destination": "api.example.com",
        "connection_type": "http",
        "owner_user_id": "user-1",
        "runtime_root": str(runtime),
    }
    processes = []
    proxies = []

    def open_proxy(**kwargs):
        proxy, worker = _spawn_proxy(config, chain.server_address)
        processes.append(worker)
        proxies.append(proxy)
        return proxy

    monkeypatch.setattr(aec, "_open_connection_proxy", open_proxy)
    packet = json.dumps(
        {
            "sink": "authenticated_external_call",
            "connection_id": "conn-http",
            "grant_id": "grant-http",
            "verb": "GET",
            "request": {"method": "GET", "url": "https://api.example.com/download"},
        }
    )
    code = NodeDefinition(
        node_id="analyse",
        display_name="analyse",
        input_keys=[],
        output_keys=["digest", "length"],
        source_code=(
            "import hashlib\n"
            "def run(state, effects):\n"
            "    fetched = effects['fetch']\n"
            "    assert set(fetched) == {'status', 'body'}\n"
            "    body = fetched['body']\n"
            "    digest = hashlib.sha256(body.encode()).hexdigest()\n"
            "    return {'digest': digest, 'length': len(body)}\n"
        ),
    )
    branch = _linear(_effect_node("fetch"), code)
    branch.state_schema += [{"name": "digest", "type": "str"}, {"name": "length", "type": "int"}]
    effects = EffectChain(run_id="redirect-composition", base_path=str(universe))
    compiled = compile_branch(
        branch, provider_call=_provider_for({"fetch": packet}), effect_chain=effects
    )
    graph = compiled.graph.compile(checkpointer=InMemorySaver())
    try:
        if echo_capability:
            with pytest.raises(EffectFailedError) as failure:
                graph.invoke({}, config={"configurable": {"thread_id": "redirect-composition"}})
            assert SIGNATURE not in str(failure.value)
            assert KEY not in str(failure.value)
        else:
            result = graph.invoke(
                {}, config={"configurable": {"thread_id": "redirect-composition"}}
            )
            assert result["digest"] == hashlib.sha256(text.encode()).hexdigest()
            assert result["length"] == len(text) > 4096
            assert effects.delivered_nodes() == ["fetch"]
            assert effects.fired == [("authenticated_external_call", "GET")]
            response = effects.evidence["fetch"]["authenticated_external_call"]["response"]
            assert response["body_truncated"] and len(response["body"]) == 4096
        assert len(processes) == 1
        assert len(chain.state["requests"]) == 2
        assert "Authorization" not in chain.state["requests"][1]["headers"]
        # Serialized effect evidence and child audit artifacts must not expose
        # the redirected destination/capability, connection key or cookies.
        evidence = json.dumps(effects.evidence)
        audit = "\n".join(p.read_text(encoding="utf-8") for p in runtime.rglob("*.jsonl"))
        # Production broker audits errors only; successful effect evidence
        # is owned by the effect chain rather than by this diagnostic writer.
        assert len(audit.splitlines()) == (1 if echo_capability else 0)
        for secret in (KEY, SIGNATURE, "cdn.example.com", "private-cookie"):
            assert secret not in evidence
            assert secret not in audit
    finally:
        for proxy in proxies:
            proxy.close()
        for worker in processes:
            worker.join(5)
            assert not worker.is_alive()
