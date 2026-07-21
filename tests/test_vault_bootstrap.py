from __future__ import annotations

import os
from pathlib import Path

import pytest

from tinyassets import credential_broker


@pytest.mark.skipif(
    os.name != "posix" or os.geteuid() != 0,
    reason="requires root-owned POSIX KEK fixtures",
)
def test_preload_platform_keys_reads_root_only_files_before_drop(tmp_path, monkeypatch):
    keys = tmp_path / "keys"
    keys.mkdir()
    (keys / "active").write_text("k1\n", encoding="utf-8")
    (keys / "k1.bin").write_bytes(b"1" * 32)
    (keys / "k0.bin").write_bytes(b"0" * 32)
    for path in keys.iterdir():
        path.chmod(0o400)
    monkeypatch.setenv("TINYASSETS_VAULT_KEK_DIR", str(keys))
    monkeypatch.setattr(credential_broker, "_PRELOADED_KEY_PROVIDER", None, raising=False)

    provider = credential_broker.preload_platform_keys()

    assert provider.active_key_id() == "k1"
    assert provider.get_key("k0") == b"0" * 32
    assert provider.get_key("k1") == b"1" * 32
    assert credential_broker.platform_key_provider() is provider


def test_container_smoke_module_is_copied_with_runtime_package():
    smoke = Path(__file__).parents[1] / "tinyassets" / "vault_container_smoke.py"
    assert smoke.is_file()


def test_docker_ci_runs_real_vault_roundtrip_through_production_entrypoint():
    workflow = (
        Path(__file__).parents[1] / ".github" / "workflows" / "docker-build.yml"
    ).read_text(encoding="utf-8")
    assert "chmod 0400 /vault-keys/k1.bin /vault-keys/active" in workflow
    assert "exec /app/docker-entrypoint.sh" in workflow
    assert "python -m tinyassets.vault_container_smoke" in workflow
