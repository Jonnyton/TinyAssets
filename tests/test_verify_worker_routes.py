"""The worker-route gate must go red for a narrowed route and refuse to guess.

Written because the gate it replaces went red during a CORRECT rollout: the
end-to-end app probe in `deploy-worker.yml` needs the daemon, which ships from
another workflow, so on 2026-09-30 the route published fine and the step failed
anyway. The replacement asserts only what that workflow owns — the binding — so
these tests pin (a) that a real narrowing fails, and (b) that `unknown` is never
reported as success.
"""

from __future__ import annotations

import json

import pytest

from scripts import verify_worker_routes as vwr
from scripts.cloud_only_preflight import PASS, REFUSE, UNKNOWN

ZONE = "tinyassets.io"
WORKER = "tinyassets-mcp-proxy"

#: The as-built inventory (deploy/cloudflare-worker/wrangler.toml).
AS_BUILT = [
    {"pattern": f"{ZONE}/mcp*", "script": WORKER},
    {"pattern": f"{ZONE}/app*", "script": WORKER},
]


@pytest.fixture
def cf(monkeypatch):
    """Drive the real audit with a scripted Cloudflare route list."""
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "t")
    monkeypatch.setattr(vwr, "resolve_zone_id", lambda *a, **k: "zone-1")

    def install(routes, *, success=True):
        monkeypatch.setattr(
            vwr,
            "audit_public_worker_route",
            __import__(
                "scripts.cloud_only_preflight", fromlist=["audit_public_worker_route"]
            ).audit_public_worker_route,
        )
        import scripts.cloud_only_preflight as pf

        monkeypatch.setattr(
            pf, "_get_json", lambda *a: ({"success": success, "result": routes}, "ok")
        )

    return install


def _run(capsys) -> tuple[int, dict]:
    code = vwr.main(["--zone-name", ZONE, "--worker-name", WORKER])
    out = capsys.readouterr().out
    start = out.find("{")
    end = out.rfind("}")
    fact = json.loads(out[start : end + 1]) if start != -1 else {}
    return code, fact


def test_the_as_built_inventory_passes(cf, capsys):
    cf(AS_BUILT)
    code, fact = _run(capsys)
    assert code == 0
    assert fact["verdict"] == PASS


@pytest.mark.parametrize("dropped", [f"{ZONE}/mcp*", f"{ZONE}/app*"])
def test_a_missing_region_binding_fails(cf, capsys, dropped):
    cf([r for r in AS_BUILT if r["pattern"] != dropped])
    code, fact = _run(capsys)
    assert code == 1
    assert fact["verdict"] == REFUSE


def test_narrowing_the_app_route_to_an_exact_path_fails(cf, capsys):
    """The regression this gate exists for.

    An exact `tinyassets.io/app` route serves the bare path, so the app shell
    still loads and nothing looks broken — while every query-bearing sign-in and
    billing return matches no route and lands on the website origin.
    """
    cf([
        {"pattern": f"{ZONE}/mcp*", "script": WORKER},
        {"pattern": f"{ZONE}/app", "script": WORKER},
        {"pattern": f"{ZONE}/app/*", "script": WORKER},
    ])
    code, fact = _run(capsys)
    assert code != 0
    assert fact["verdict"] != PASS


def test_a_route_stolen_by_another_script_fails(cf, capsys):
    cf(AS_BUILT + [{"pattern": f"{ZONE}/app/me", "script": "someone-else"}])
    code, fact = _run(capsys)
    assert code != 0
    assert fact["verdict"] != PASS


def test_a_scriptless_route_suppressing_the_app_fails(cf, capsys):
    """Cloudflare: "a route can be specified without a Worker … this will act to
    negate any less specific patterns." That silently darks the path."""
    cf(AS_BUILT + [{"pattern": f"{ZONE}/app*", "script": None}])
    code, fact = _run(capsys)
    assert code != 0
    assert fact["verdict"] != PASS


def test_undecidable_is_exit_2_not_success(cf, capsys):
    """`unknown` must never read as a pass — "cannot decide" is not evidence."""
    cf(AS_BUILT + [{"pattern": "*tinyassets.io/app*", "script": WORKER}])
    code, fact = _run(capsys)
    assert fact["verdict"] == UNKNOWN
    assert code == 2


def test_a_missing_token_is_exit_2(monkeypatch, capsys):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    assert vwr.main(["--zone-name", ZONE, "--worker-name", WORKER]) == 2
    assert "CLOUDFLARE_API_TOKEN is required" in capsys.readouterr().out


def test_an_unresolvable_zone_is_exit_2(monkeypatch, capsys):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "t")
    monkeypatch.setattr(vwr, "resolve_zone_id", lambda *a, **k: None)
    assert vwr.main(["--zone-name", ZONE, "--worker-name", WORKER]) == 2
    assert "could not resolve a zone id" in capsys.readouterr().out


def test_the_printed_fact_carries_no_credential(cf, capsys):
    cf(AS_BUILT)
    vwr.main(["--zone-name", ZONE, "--worker-name", WORKER])
    out = capsys.readouterr().out
    # The token is the only secret in scope; it must not reach the log.
    assert "Bearer" not in out
    assert '"t"' not in out
