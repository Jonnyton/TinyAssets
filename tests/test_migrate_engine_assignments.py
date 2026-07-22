"""Offline migration proofs for the provider-assignment writer fence."""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "scripts" / "migrate_engine_assignments.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _seed_assignment(
    root: Path,
    universe_id: str = "u-one",
    *,
    service: str = "anthropic",
    writer: str = "claude-code",
    source: str = "byo_api_key",
    secret: str = "top-secret-never-print",
) -> Path:
    universe = root / universe_id
    universe.mkdir(parents=True)
    (universe / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "engine_source": source,
                "preferred_writer": writer,
                "unrelated": {"keep": [1, 2, 3]},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    _write_json(
        universe / ".credential-vault.json",
        {
            "schema_version": 1,
            "credentials": [
                {
                    "credential_type": "llm_api_key",
                    "service": service,
                    "secret_b64": base64.b64encode(secret.encode()).decode(),
                },
                {
                    "credential_type": "vcs",
                    "service": "github",
                    "token": "unrelated-vcs-secret",
                },
            ],
        },
    )
    _write_json(
        universe / "ledger.json",
        [
            {
                "action": "set_engine",
                "payload": {
                    "engine_source": source,
                    "service": service,
                    "preferred_writer": writer,
                    "status": "engine_set",
                },
            }
        ],
    )
    return universe


def _inventory(root: Path, manifest: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
    result = _run(
        "inventory",
        "--data-dir",
        str(root),
        "--manifest",
        str(manifest),
    )
    payload = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
    return result, payload


def _approve(manifest: Path) -> None:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["review"] = {
        "approved": True,
        "reviewer": "offline-operator",
        "reviewed_at": "2026-07-22T20:00:00Z",
    }
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_inventory_confirms_only_exact_byo_mapping_and_never_emits_secrets(tmp_path):
    root = tmp_path / "data"
    _seed_assignment(root)
    manifest = tmp_path / "manifest.json"

    result, payload = _inventory(root, manifest)

    assert result.returncode == 0, result.stderr
    assert payload["schema_version"] == 1
    assert payload["fence_version"] == 1
    assert payload["review"]["approved"] is False
    assert payload["summary"] == {
        "candidate_count": 1,
        "fatal_count": 0,
        "needs_migration_count": 1,
    }
    entry = payload["universes"][0]
    assert entry["universe_id"] == "u-one"
    assert entry["classification"] == "confirmed_byo"
    assert entry["target"] == {
        "engine_assignment_state": "ready",
        "allowed_providers": ["claude-code"],
    }
    serialized = json.dumps(payload) + result.stdout + result.stderr
    assert "top-secret-never-print" not in serialized
    assert "unrelated-vcs-secret" not in serialized
    assert "secret_b64" not in serialized
    assert "api_key" not in serialized


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda universe: _replace_service(universe, "claude"), "noncanonical_key_service"),
        (lambda universe: _append_openai_key(universe), "multiple_key_providers"),
        (lambda universe: _replace_ledger_writer(universe, "codex"), "ledger_mismatch"),
        (lambda universe: _remove_ledger(universe), "missing_set_engine_ledger"),
    ],
)
def test_ambiguous_byo_evidence_is_quarantined(tmp_path, mutate, reason):
    root = tmp_path / "data"
    universe = _seed_assignment(root)
    mutate(universe)

    result, payload = _inventory(root, tmp_path / "manifest.json")

    assert result.returncode == 0, result.stderr
    entry = payload["universes"][0]
    assert entry["classification"] == "hold"
    assert entry["target"]["allowed_providers"] == []
    assert reason in entry["reason_codes"]


def _replace_service(universe: Path, service: str) -> None:
    path = universe / ".credential-vault.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["credentials"][0]["service"] = service
    _write_json(path, value)


def _append_openai_key(universe: Path) -> None:
    path = universe / ".credential-vault.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["credentials"].append(
        {
            "credential_type": "llm_api_key",
            "service": "openai",
            "secret_b64": base64.b64encode(b"other-secret").decode(),
        }
    )
    _write_json(path, value)


def _replace_ledger_writer(universe: Path, writer: str) -> None:
    path = universe / "ledger.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value[-1]["payload"]["preferred_writer"] = writer
    _write_json(path, value)


def _remove_ledger(universe: Path) -> None:
    (universe / "ledger.json").unlink()


@pytest.mark.parametrize("source", ["self_hosted_endpoint", "market_rented", "host_daemon"])
def test_incomplete_non_byo_sources_are_explicit_holds(tmp_path, source):
    root = tmp_path / "data"
    universe = root / source
    universe.mkdir(parents=True)
    (universe / "config.yaml").write_text(
        yaml.safe_dump({"engine_source": source, "preferred_writer": "codex"}),
        encoding="utf-8",
    )

    result, payload = _inventory(root, tmp_path / "manifest.json")

    assert result.returncode == 0, result.stderr
    entry = payload["universes"][0]
    assert entry["classification"] == "hold"
    assert entry["target"]["allowed_providers"] == []
    assert "incomplete_engine_source" in entry["reason_codes"]


@pytest.mark.parametrize("filename", ["config.yaml", ".credential-vault.json", "ledger.json"])
def test_unreadable_state_is_fatal_and_inventory_never_rewrites_it(tmp_path, filename):
    root = tmp_path / "data"
    universe = _seed_assignment(root)
    path = universe / filename
    before = path.read_bytes()
    path.write_text("{ definitely: [not valid", encoding="utf-8")
    corrupt = path.read_bytes()

    result, payload = _inventory(root, tmp_path / "manifest.json")

    assert result.returncode == 2
    assert payload["summary"]["fatal_count"] == 1
    assert payload["universes"][0]["classification"] == "fatal"
    assert path.read_bytes() == corrupt
    assert path.read_bytes() != before


def test_apply_requires_explicit_review_metadata(tmp_path):
    root = tmp_path / "data"
    _seed_assignment(root)
    manifest = tmp_path / "manifest.json"
    inventory, _ = _inventory(root, manifest)
    assert inventory.returncode == 0

    result = _run("apply", "--data-dir", str(root), "--manifest", str(manifest))

    assert result.returncode == 3
    assert "review" in result.stderr.lower()
    raw = yaml.safe_load((root / "u-one" / "config.yaml").read_text(encoding="utf-8"))
    assert "engine_assignment_state" not in raw
    assert "allowed_providers" not in raw


def test_apply_preserves_unrelated_config_and_exact_vault_and_ledger_bytes(tmp_path):
    root = tmp_path / "data"
    universe = _seed_assignment(root)
    manifest = tmp_path / "manifest.json"
    inventory, _ = _inventory(root, manifest)
    assert inventory.returncode == 0
    _approve(manifest)
    vault_before = (universe / ".credential-vault.json").read_bytes()
    ledger_before = (universe / "ledger.json").read_bytes()

    result = _run("apply", "--data-dir", str(root), "--manifest", str(manifest))

    assert result.returncode == 0, result.stderr
    config = yaml.safe_load((universe / "config.yaml").read_text(encoding="utf-8"))
    assert config["engine_assignment_state"] == "ready"
    assert config["allowed_providers"] == ["claude-code"]
    assert config["unrelated"] == {"keep": [1, 2, 3]}
    assert (universe / ".credential-vault.json").read_bytes() == vault_before
    assert (universe / "ledger.json").read_bytes() == ledger_before
    marker = json.loads((root / ".engine-assignment-migration-v1.json").read_text())
    assert marker["fence_version"] == 1
    assert "top-secret-never-print" not in json.dumps(marker)


def test_apply_rejects_stale_or_incomplete_manifest_before_any_write(tmp_path):
    root = tmp_path / "data"
    first = _seed_assignment(root, "u-one")
    second = _seed_assignment(root, "u-two")
    manifest = tmp_path / "manifest.json"
    inventory, _ = _inventory(root, manifest)
    assert inventory.returncode == 0
    _approve(manifest)
    first_before = (first / "config.yaml").read_bytes()
    second_config = yaml.safe_load((second / "config.yaml").read_text(encoding="utf-8"))
    second_config["preferred_writer"] = "codex"
    (second / "config.yaml").write_text(yaml.safe_dump(second_config), encoding="utf-8")

    result = _run("apply", "--data-dir", str(root), "--manifest", str(manifest))

    assert result.returncode == 4
    assert "stale" in result.stderr.lower()
    assert (first / "config.yaml").read_bytes() == first_before


def test_apply_and_marker_are_idempotent_and_verify_reports_zero_residual(tmp_path):
    root = tmp_path / "data"
    universe = _seed_assignment(root)
    manifest = tmp_path / "manifest.json"
    inventory, _ = _inventory(root, manifest)
    assert inventory.returncode == 0
    _approve(manifest)

    first = _run("apply", "--data-dir", str(root), "--manifest", str(manifest))
    assert first.returncode == 0, first.stderr
    config_before = (universe / "config.yaml").read_bytes()
    marker_before = (root / ".engine-assignment-migration-v1.json").read_bytes()
    second = _run("apply", "--data-dir", str(root), "--manifest", str(manifest))
    verify = _run("verify", "--data-dir", str(root))

    assert second.returncode == 0, second.stderr
    assert verify.returncode == 0, verify.stderr
    assert json.loads(verify.stdout)["summary"]["needs_migration_count"] == 0
    assert (universe / "config.yaml").read_bytes() == config_before
    assert (root / ".engine-assignment-migration-v1.json").read_bytes() == marker_before


def test_manifest_may_not_omit_or_duplicate_a_candidate(tmp_path):
    root = tmp_path / "data"
    _seed_assignment(root, "u-one")
    _seed_assignment(root, "u-two")
    manifest = tmp_path / "manifest.json"
    inventory, payload = _inventory(root, manifest)
    assert inventory.returncode == 0
    payload["universes"] = [payload["universes"][0], payload["universes"][0]]
    payload["review"] = {
        "approved": True,
        "reviewer": "offline-operator",
        "reviewed_at": "2026-07-22T20:00:00Z",
    }
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = _run("apply", "--data-dir", str(root), "--manifest", str(manifest))

    assert result.returncode == 4
    assert "duplicate" in result.stderr.lower() or "stale" in result.stderr.lower()


def test_support_probe_and_docker_image_copy_are_versioned():
    supported = _run("supports-fence-version", "1")
    unsupported = _run("supports-fence-version", "2")
    dockerfile = (_REPO / "Dockerfile").read_text(encoding="utf-8")

    assert supported.returncode == 0
    assert unsupported.returncode != 0
    assert "COPY scripts/migrate_engine_assignments.py" in dockerfile
    assert "/app/scripts/migrate_engine_assignments.py" in dockerfile


def test_atomic_config_failure_leaves_original_and_cleans_temp(tmp_path, monkeypatch):
    assert _SCRIPT.is_file(), "migration command must exist before loading it"
    spec = importlib.util.spec_from_file_location("migrate_engine_assignments", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "config.yaml"
    path.write_text("keep: original\n", encoding="utf-8")

    def fail_replace(_source, _target):
        raise OSError("injected replace failure")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected replace failure"):
        module._write_config_atomic(path, {"keep": "new"})

    assert path.read_text(encoding="utf-8") == "keep: original\n"
    assert list(tmp_path.glob(".config.*.tmp")) == []


def test_symlinked_assignment_file_fails_closed(tmp_path):
    root = tmp_path / "data"
    universe = _seed_assignment(root)
    outside = tmp_path / "outside.yaml"
    outside.write_text("engine_source: byo_api_key\n", encoding="utf-8")
    (universe / "config.yaml").unlink()
    try:
        os.symlink(outside, universe / "config.yaml")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")

    result, payload = _inventory(root, tmp_path / "manifest.json")

    assert result.returncode == 2
    assert payload["universes"][0]["classification"] == "fatal"
    assert "symlink" in " ".join(payload["universes"][0]["reason_codes"])


def test_inventory_is_byte_and_directory_entry_immutable(tmp_path):
    root = tmp_path / "data"
    universe = _seed_assignment(root)
    before = {
        path.name: (path.stat().st_mode, path.read_bytes())
        for path in universe.iterdir()
        if path.is_file()
    }

    result, _ = _inventory(root, tmp_path / "manifest.json")

    assert result.returncode == 0, result.stderr
    after = {
        path.name: (path.stat().st_mode, path.read_bytes())
        for path in universe.iterdir()
        if path.is_file()
    }
    assert after == before


@pytest.mark.parametrize(
    "content",
    [
        "engine_source: byo_api_key\nengine_source: market_rented\n",
        "base: &base\n  engine_source: byo_api_key\n<<: *base\n",
        "engine_source: byo_api_key\n---\npreferred_writer: claude-code\n",
    ],
)
def test_yaml_duplicate_merge_and_multidocument_shapes_are_fatal(tmp_path, content):
    root = tmp_path / "data"
    universe = _seed_assignment(root)
    (universe / "config.yaml").write_text(content, encoding="utf-8")

    result, payload = _inventory(root, tmp_path / "manifest.json")

    assert result.returncode == 2
    assert payload["universes"][0]["classification"] == "fatal"


@pytest.mark.parametrize("filename", [".credential-vault.json", "ledger.json"])
def test_json_duplicate_keys_and_nonfinite_numbers_are_fatal(tmp_path, filename):
    root = tmp_path / "data"
    universe = _seed_assignment(root)
    (universe / filename).write_text(
        '{"duplicate": 1, "duplicate": 2, "nonfinite": NaN}',
        encoding="utf-8",
    )

    result, payload = _inventory(root, tmp_path / "manifest.json")

    assert result.returncode == 2
    assert payload["universes"][0]["classification"] == "fatal"


def test_preference_and_privacy_allowlist_alone_are_not_assignment_evidence(tmp_path):
    root = tmp_path / "data"
    universe = root / "ordinary-routing"
    universe.mkdir(parents=True)
    (universe / "config.yaml").write_text(
        yaml.safe_dump(
            {"preferred_writer": "claude-code", "allowed_providers": ["claude-code"]}
        ),
        encoding="utf-8",
    )

    result, payload = _inventory(root, tmp_path / "manifest.json")

    assert result.returncode == 0, result.stderr
    assert payload["universes"] == []


def test_missing_explicit_engine_source_cannot_auto_confirm_singleton(tmp_path):
    root = tmp_path / "data"
    universe = _seed_assignment(root)
    config = yaml.safe_load((universe / "config.yaml").read_text(encoding="utf-8"))
    del config["engine_source"]
    (universe / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")

    result, payload = _inventory(root, tmp_path / "manifest.json")

    assert result.returncode == 0, result.stderr
    entry = payload["universes"][0]
    assert entry["classification"] == "hold"
    assert "missing_explicit_engine_source" in entry["reason_codes"]


def test_hardlinked_assignment_file_fails_closed(tmp_path):
    root = tmp_path / "data"
    universe = _seed_assignment(root)
    outside = tmp_path / "outside.yaml"
    outside.write_bytes((universe / "config.yaml").read_bytes())
    (universe / "config.yaml").unlink()
    try:
        os.link(outside, universe / "config.yaml")
    except OSError:
        pytest.skip("hardlink creation unavailable")

    result, payload = _inventory(root, tmp_path / "manifest.json")

    assert result.returncode == 2
    assert payload["universes"][0]["classification"] == "fatal"
    assert "hardlink" in " ".join(payload["universes"][0]["reason_codes"])


def test_apply_has_bounded_lock_wait_and_zero_mutation(tmp_path):
    assert _SCRIPT.is_file(), "migration command must exist before lock proof"
    from tinyassets.config import engine_assignment_lock

    root = tmp_path / "data"
    universe = _seed_assignment(root)
    manifest = tmp_path / "manifest.json"
    inventory, _ = _inventory(root, manifest)
    assert inventory.returncode == 0
    _approve(manifest)
    before = (universe / "config.yaml").read_bytes()

    with engine_assignment_lock(universe):
        result = _run(
            "apply",
            "--data-dir",
            str(root),
            "--manifest",
            str(manifest),
            "--lock-timeout",
            "0.2",
        )

    assert result.returncode == 5
    assert "lock" in result.stderr.lower()
    assert (universe / "config.yaml").read_bytes() == before


@pytest.mark.parametrize(
    ("state", "ceiling"),
    [
        ("pending", []),
        ("ready", []),
        ("invalid", ["claude-code"]),
        ("ready", None),
        ("ready", ["codex"]),
    ],
)
def test_existing_quarantine_or_invalid_explicit_state_never_auto_confirms(
    tmp_path, state, ceiling
):
    root = tmp_path / "data"
    universe = _seed_assignment(root)
    config_path = universe / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["engine_assignment_state"] = state
    config["allowed_providers"] = ceiling
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    manifest = tmp_path / "manifest.json"

    result, payload = _inventory(root, manifest)

    assert result.returncode == 0, result.stderr
    entry = payload["universes"][0]
    assert entry["classification"] == "hold"
    assert entry["target"] == {
        "engine_assignment_state": "ready",
        "allowed_providers": [],
    }
    _approve(manifest)
    apply = _run("apply", "--data-dir", str(root), "--manifest", str(manifest))
    assert apply.returncode == 0, apply.stderr
    applied = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert applied["engine_assignment_state"] == "ready"
    assert applied["allowed_providers"] == []


@pytest.mark.parametrize("failure_phase", ["second_config", "marker"])
def test_apply_failure_restores_all_config_bytes_and_same_manifest_retries(
    tmp_path, monkeypatch, failure_phase
):
    root = tmp_path / "data"
    first = _seed_assignment(root, "u-one")
    second = _seed_assignment(root, "u-two")
    manifest = tmp_path / "manifest.json"
    inventory, _ = _inventory(root, manifest)
    assert inventory.returncode == 0
    _approve(manifest)
    before = {
        first / "config.yaml": (first / "config.yaml").read_bytes(),
        second / "config.yaml": (second / "config.yaml").read_bytes(),
    }

    spec = importlib.util.spec_from_file_location("migration_failure_test", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_config_write = module._write_config_atomic
    original_json_write = module._write_json_atomic

    def injected_config_write(path, data):
        if failure_phase == "second_config" and path.parent.name == "u-two":
            raise OSError("injected second config failure")
        original_config_write(path, data)

    def injected_json_write(path, value):
        if failure_phase == "marker" and path.name == module.MARKER_FILENAME:
            raise OSError("injected marker failure")
        original_json_write(path, value)

    monkeypatch.setattr(module, "_write_config_atomic", injected_config_write)
    monkeypatch.setattr(module, "_write_json_atomic", injected_json_write)
    with pytest.raises(Exception, match="config|marker"):
        module._apply(module._validated_data_dir(root), manifest, lock_timeout=0.2)

    assert {path: path.read_bytes() for path in before} == before
    assert not (root / module.MARKER_FILENAME).exists()

    monkeypatch.setattr(module, "_write_config_atomic", original_config_write)
    monkeypatch.setattr(module, "_write_json_atomic", original_json_write)
    assert module._apply(
        module._validated_data_dir(root), manifest, lock_timeout=0.2
    ) == 0


def test_apply_locks_noncandidate_direct_child_before_any_write(tmp_path):
    from tinyassets.config import engine_assignment_lock

    root = tmp_path / "data"
    candidate = _seed_assignment(root)
    ordinary = root / "ordinary-routing"
    ordinary.mkdir()
    (ordinary / "config.yaml").write_text(
        yaml.safe_dump({"preferred_writer": "codex"}), encoding="utf-8"
    )
    manifest = tmp_path / "manifest.json"
    inventory, _ = _inventory(root, manifest)
    assert inventory.returncode == 0
    _approve(manifest)
    before = (candidate / "config.yaml").read_bytes()

    with engine_assignment_lock(ordinary):
        result = _run(
            "apply",
            "--data-dir",
            str(root),
            "--manifest",
            str(manifest),
            "--lock-timeout",
            "0.2",
        )

    assert result.returncode == 5
    assert "lock" in result.stderr.lower()
    assert (candidate / "config.yaml").read_bytes() == before


def test_apply_does_not_create_assignment_locks_in_hidden_auth_homes(tmp_path):
    root = tmp_path / "data"
    _seed_assignment(root)
    auth_home = root / ".codex"
    auth_home.mkdir()
    (auth_home / "auth.json").write_text("{}", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    inventory, _ = _inventory(root, manifest)
    assert inventory.returncode == 0
    _approve(manifest)

    apply = _run("apply", "--data-dir", str(root), "--manifest", str(manifest))

    assert apply.returncode == 0, apply.stderr
    assert not (auth_home / ".engine-assignment.lock").exists()


def test_manifest_path_must_resolve_outside_data_root(tmp_path):
    root = tmp_path / "data"
    universe = _seed_assignment(root)
    before = (universe / "config.yaml").read_bytes()
    inside = root / "manifest.json"

    inventory = _run(
        "inventory", "--data-dir", str(root), "--manifest", str(inside)
    )

    assert inventory.returncode != 0
    assert not inside.exists()
    assert (universe / "config.yaml").read_bytes() == before

    outside = tmp_path / "manifest.json"
    good_inventory, _ = _inventory(root, outside)
    assert good_inventory.returncode == 0
    _approve(outside)
    inside.write_bytes(outside.read_bytes())
    apply = _run("apply", "--data-dir", str(root), "--manifest", str(inside))

    assert apply.returncode == 4
    assert (universe / "config.yaml").read_bytes() == before


def test_manifest_parent_symlink_into_data_root_is_rejected(tmp_path):
    root = tmp_path / "data"
    _seed_assignment(root)
    alias = tmp_path / "data-alias"
    try:
        os.symlink(root, alias, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlink creation unavailable")

    result = _run(
        "inventory",
        "--data-dir",
        str(root),
        "--manifest",
        str(alias / "manifest.json"),
    )

    assert result.returncode != 0
    assert not (root / "manifest.json").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX uid/gid semantics")
def test_config_replacement_preserves_posix_owner_group_and_mode(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("migration_metadata_test", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "config.yaml"
    path.write_text("keep: original\n", encoding="utf-8")
    path.chmod(0o640)
    before = path.stat()
    calls = []
    original_fchown = module.os.fchown

    def recording_fchown(target, uid, gid):
        calls.append((uid, gid))
        original_fchown(target, uid, gid)

    monkeypatch.setattr(module.os, "fchown", recording_fchown)
    module._write_config_atomic(path, {"keep": "new"})

    after = path.stat()
    assert (after.st_uid, after.st_gid) == (before.st_uid, before.st_gid)
    assert after.st_mode & 0o777 == 0o640
    assert (before.st_uid, before.st_gid) in calls


def test_verify_allows_new_valid_post_cutover_assignment(tmp_path):
    root = tmp_path / "data"
    _seed_assignment(root, "u-one")
    manifest = tmp_path / "manifest.json"
    inventory, _ = _inventory(root, manifest)
    assert inventory.returncode == 0
    _approve(manifest)
    assert _run(
        "apply", "--data-dir", str(root), "--manifest", str(manifest)
    ).returncode == 0

    new_universe = _seed_assignment(root, "u-two")
    config_path = new_universe / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["engine_assignment_state"] = "ready"
    config["allowed_providers"] = ["claude-code"]
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    verify = _run("verify", "--data-dir", str(root))
    retry_old_manifest = _run(
        "apply", "--data-dir", str(root), "--manifest", str(manifest)
    )

    assert verify.returncode == 0, verify.stderr
    assert json.loads(verify.stdout)["marker_decisions_match"] is False
    assert retry_old_manifest.returncode == 4


def test_hard_crash_journal_resumes_same_manifest_without_secrets(tmp_path):
    root = tmp_path / "data"
    first = _seed_assignment(root, "u-one")
    second = _seed_assignment(root, "u-two")
    manifest = tmp_path / "manifest.json"
    inventory, _ = _inventory(root, manifest)
    assert inventory.returncode == 0
    _approve(manifest)
    before = {
        first / "config.yaml": (first / "config.yaml").read_bytes(),
        second / "config.yaml": (second / "config.yaml").read_bytes(),
    }
    child_code = """
import importlib.util
import os
import sys
from pathlib import Path

script, data_dir, manifest = sys.argv[1:]
spec = importlib.util.spec_from_file_location("migration_crash_child", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
original = module._write_config_atomic
write_count = 0

def crash_after_first(path, data):
    global write_count
    original(path, data)
    write_count += 1
    if write_count == 1:
        os._exit(91)

module._write_config_atomic = crash_after_first
module._apply(module._validated_data_dir(data_dir), Path(manifest), lock_timeout=2.0)
"""

    crashed = subprocess.run(
        [sys.executable, "-c", child_code, str(_SCRIPT), str(root), str(manifest)],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )

    journal = root / ".engine-assignment-migration-transaction-v1.json"
    assert crashed.returncode == 91
    assert (first / "config.yaml").read_bytes() != before[first / "config.yaml"]
    assert (second / "config.yaml").read_bytes() == before[second / "config.yaml"]
    journal_bytes = journal.read_bytes()
    for forbidden in (
        b"top-secret-never-print",
        b"unrelated-vcs-secret",
        b"secret_b64",
        b"api_key",
    ):
        assert forbidden not in journal_bytes
    verify_during_recovery = _run("verify", "--data-dir", str(root))
    assert verify_during_recovery.returncode != 0

    resumed = _run(
        "apply", "--data-dir", str(root), "--manifest", str(manifest)
    )

    assert resumed.returncode == 0, resumed.stderr
    for universe in (first, second):
        config = yaml.safe_load((universe / "config.yaml").read_text(encoding="utf-8"))
        assert config["engine_assignment_state"] == "ready"
        assert config["allowed_providers"] == ["claude-code"]
    assert not journal.exists()
    assert (root / ".engine-assignment-migration-v1.json").is_file()
    assert _run("verify", "--data-dir", str(root)).returncode == 0


def test_marker_committed_journal_cleanup_failure_resumes_cleanup(tmp_path, monkeypatch):
    root = tmp_path / "data"
    universe = _seed_assignment(root)
    manifest = tmp_path / "manifest.json"
    inventory, _ = _inventory(root, manifest)
    assert inventory.returncode == 0
    _approve(manifest)
    spec = importlib.util.spec_from_file_location("migration_cleanup_test", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_unlink = module._unlink_regular_file_durable

    def fail_journal_cleanup(path):
        if path.name == module.JOURNAL_FILENAME:
            raise OSError("injected journal cleanup failure")
        original_unlink(path)

    monkeypatch.setattr(module, "_unlink_regular_file_durable", fail_journal_cleanup)
    with pytest.raises(module.MigrationError, match="marker committed"):
        module._apply(
            module._validated_data_dir(root), manifest, lock_timeout=0.2
        )

    marker = root / module.MARKER_FILENAME
    journal = root / module.JOURNAL_FILENAME
    assert marker.is_file()
    assert journal.is_file()
    assert _run("verify", "--data-dir", str(root)).returncode != 0
    config_after_marker = (universe / "config.yaml").read_bytes()
    marker_before_retry = marker.read_bytes()

    monkeypatch.setattr(
        module, "_unlink_regular_file_durable", original_unlink
    )
    assert module._apply(
        module._validated_data_dir(root), manifest, lock_timeout=0.2
    ) == 0
    assert not journal.exists()
    assert marker.read_bytes() == marker_before_retry
    assert (universe / "config.yaml").read_bytes() == config_after_marker
    assert _run("verify", "--data-dir", str(root)).returncode == 0


def test_incomplete_catchable_rollback_keeps_resumable_journal(tmp_path, monkeypatch):
    root = tmp_path / "data"
    _seed_assignment(root, "u-one")
    _seed_assignment(root, "u-two")
    manifest = tmp_path / "manifest.json"
    inventory, _ = _inventory(root, manifest)
    assert inventory.returncode == 0
    _approve(manifest)
    spec = importlib.util.spec_from_file_location("migration_rollback_test", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_write = module._write_config_atomic
    original_restore = module._restore_config_snapshot

    def fail_second_write(path, data):
        if path.parent.name == "u-two":
            raise OSError("injected second config failure")
        original_write(path, data)

    def fail_first_restore(path, snapshot):
        if path.parent.name == "u-one":
            raise OSError("injected rollback failure")
        original_restore(path, snapshot)

    monkeypatch.setattr(module, "_write_config_atomic", fail_second_write)
    monkeypatch.setattr(module, "_restore_config_snapshot", fail_first_restore)
    with pytest.raises(module.MigrationError, match="rollback was incomplete"):
        module._apply(
            module._validated_data_dir(root), manifest, lock_timeout=0.2
        )

    journal = root / module.JOURNAL_FILENAME
    assert journal.is_file()
    assert _run("verify", "--data-dir", str(root)).returncode != 0

    monkeypatch.setattr(module, "_write_config_atomic", original_write)
    monkeypatch.setattr(module, "_restore_config_snapshot", original_restore)
    assert module._apply(
        module._validated_data_dir(root), manifest, lock_timeout=0.2
    ) == 0
    assert not journal.exists()
    assert _run("verify", "--data-dir", str(root)).returncode == 0
