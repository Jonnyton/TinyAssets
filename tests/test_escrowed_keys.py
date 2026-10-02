"""The escrow check compares by hash and never prints a value or a hash."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import compare_escrowed_keys as cmp  # noqa: E402
import escrowed_key_hashes as hashes  # noqa: E402

SEAL = "c2VhbC1rZXktdmFsdWUtMzItYnl0ZXMtbG9uZy4uLi4="


def _h(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def test_the_host_reads_the_last_assignment_and_strips_one_quote_pair():
    text = "A=1\nTINYASSETS_SESSION_SEAL_KEY=old\nTINYASSETS_SESSION_SEAL_KEY='new'\n"
    assert hashes.host_value(text, "TINYASSETS_SESSION_SEAL_KEY") == "new"
    assert hashes.host_value("A=1\n", "TINYASSETS_SESSION_SEAL_KEY") is None


def test_a_vapid_pem_with_literal_backslash_n_is_compared_as_written():
    pem = "-----BEGIN PRIVATE KEY-----\\nABC\\n-----END PRIVATE KEY-----\\n"
    text = f"TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY={pem}\n"
    assert hashes.host_value(text, "TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY") == pem


def test_verdicts_cover_every_case():
    host = "\n".join([
        f"TINYASSETS_SESSION_SEAL_KEY {_h(SEAL)}",
        f"TINYASSETS_BILLING_ENTITLEMENT_KEY {_h('billing')}",
        "TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY ABSENT",
        f"TINYASSETS_APP_INGRESS_HMAC_KEY {_h('ingress')}",
    ])
    env = {
        "TINYASSETS_SESSION_SEAL_KEY": SEAL,
        "TINYASSETS_BILLING_ENTITLEMENT_KEY": "different",
        "TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY": "pem",
    }
    assert cmp.verdicts(host, env) == {
        "TINYASSETS_SESSION_SEAL_KEY": "match",
        "TINYASSETS_BILLING_ENTITLEMENT_KEY": "MISMATCH",
        "TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY": "not-on-host",
        "TINYASSETS_APP_INGRESS_HMAC_KEY": "not-in-github",
    }


def test_output_never_contains_a_value_or_a_hash():
    host = f"TINYASSETS_SESSION_SEAL_KEY {_h(SEAL)}\n"
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "compare_escrowed_keys.py")],
        input=host, capture_output=True, text=True,
        env={"TINYASSETS_SESSION_SEAL_KEY": SEAL, "SYSTEMROOT": ""},
    )
    assert result.returncode == 1  # the other three are not escrowed
    assert "TINYASSETS_SESSION_SEAL_KEY: match" in result.stdout
    assert SEAL not in result.stdout + result.stderr
    assert _h(SEAL) not in result.stdout + result.stderr


def test_the_workflow_is_read_only_dispatch_and_never_echoes_the_hashes():
    wf = yaml.safe_load((REPO / ".github/workflows/verify-escrowed-keys.yml").read_text())
    assert set(wf[True]) == {"workflow_dispatch"}
    step = next(s for s in wf["jobs"]["verify"]["steps"] if s.get("name", "").startswith("Compare"))
    run = step["run"]
    assert 'host_hashes="$(' in run
    assert "echo" not in run, "the host hashes must never be echoed"
    assert "<<< \"${host_hashes}\"" in run
    for name in cmp.KEYS:
        assert step["env"][name] == "${{ secrets.%s }}" % name
    assert set(cmp.KEYS) == set(hashes.ESCROWED_KEYS)
