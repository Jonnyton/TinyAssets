"""Tests for Row K log aggregation sidecar (deploy/compose.yml + deploy/vector.yaml)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE = REPO_ROOT / "deploy" / "compose.yml"
VECTOR_YAML = REPO_ROOT / "deploy" / "vector.yaml"
VECTOR_BETTERSTACK_YAML = REPO_ROOT / "deploy" / "vector-betterstack.yaml"
VECTOR_ENTRYPOINT = REPO_ROOT / "deploy" / "vector-entrypoint.sh"
JOURNALD_DROPIN = REPO_ROOT / "deploy" / "journald-tinyassets.conf"
INSTALLER = REPO_ROOT / "deploy" / "install-host-uptime-services.sh"
BACKUP_SH = REPO_ROOT / "deploy" / "backup.sh"
RUNBOOK = REPO_ROOT / "docs" / "ops" / "log-aggregation-runbook.md"


# ---------------------------------------------------------------------------
# compose.yml — sidecar service assertions
# ---------------------------------------------------------------------------


def _load_compose() -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_logs_service_defined():
    data = _load_compose()
    assert "logs" in data["services"], "compose.yml must have a 'logs' sidecar service"


def test_logs_service_uses_vector_image():
    data = _load_compose()
    image = data["services"]["logs"]["image"]
    assert image.startswith("timberio/vector:"), f"unexpected image: {image}"


def test_logs_service_restart_policy():
    data = _load_compose()
    restart = data["services"]["logs"].get("restart")
    assert restart == "unless-stopped", f"restart policy should be unless-stopped, got: {restart}"


def test_logs_service_has_no_docker_socket_or_container_control():
    data = _load_compose()
    volumes = data["services"]["logs"].get("volumes", [])
    socket_mounts = [v for v in volumes if "/var/run/docker.sock" in str(v)]
    assert not socket_mounts, "logging sidecar must not receive Docker control access"


def test_runtime_containers_forward_logs_without_docker_socket():
    data = _load_compose()
    services = data["services"]
    # Derived, not listed: the four `worker*` services were deleted 2026-08-29
    # with the host-run fleet (nothing runs outside a user's universe --
    # PLAN.md), and deriving means a NEW long-running container inherits the
    # forwarding requirement instead of silently escaping this test.
    forwarding_services = [
        name for name, service in services.items()
        if name != "logs" and service.get("logging") is not None
    ]
    assert set(forwarding_services) == {"daemon", "cloudflared", "slack-agent"}, (
        f"unexpected forwarding service set: {sorted(forwarding_services)}"
    )
    for name in forwarding_services:
        logging = services[name].get("logging") or {}
        assert logging.get("driver") == "fluentd", name
        options = logging.get("options") or {}
        assert options.get("fluentd-address") == "127.0.0.1:24224", name
        assert str(options.get("fluentd-async")).lower() == "true", name

    ports = services["logs"].get("ports") or []
    assert "127.0.0.1:24224:24224" in ports


def test_sidecars_receive_only_their_required_secret():
    services = _load_compose()["services"]
    expected = {
        "cloudflared": {"CLOUDFLARE_TUNNEL_TOKEN"},
        "logs": {"BETTERSTACK_SOURCE_TOKEN"},
    }
    for name, allowed in expected.items():
        service = services[name]
        assert not (service.get("env_file") or []), name
        environment = service.get("environment") or {}
        assert set(environment) == allowed, name
        assert all("${" in str(value) for value in environment.values()), name


def test_logs_service_mounts_vector_config():
    data = _load_compose()
    volumes = data["services"]["logs"].get("volumes", [])
    config_mounts = [v for v in volumes if "vector.yaml" in str(v)]
    assert config_mounts, "logs service must mount vector.yaml config"


def test_logs_service_depends_on_daemon():
    data = _load_compose()
    deps = data["services"]["logs"].get("depends_on", [])
    if isinstance(deps, dict):
        dep_names = list(deps.keys())
    else:
        dep_names = list(deps)
    assert "daemon" in dep_names, "logs service must depend on daemon"


# ---------------------------------------------------------------------------
# vector.yaml — source / transform / sink assertions
# ---------------------------------------------------------------------------


def _load_vector() -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(VECTOR_YAML.read_text(encoding="utf-8"))


def test_vector_fluent_source_has_no_docker_api_dependency():
    data = _load_vector()
    sources = data.get("sources", {})
    assert all(source.get("type") != "docker_logs" for source in sources.values())
    fluent = next((v for v in sources.values() if v.get("type") == "fluent"), None)
    assert fluent is not None
    assert fluent.get("address") == "0.0.0.0:24224"
    assert fluent.get("mode") == "tcp"


def test_vector_classifies_forwarded_runtime_tags():
    data = _load_vector()
    transform = data["transforms"]["enriched"]
    source = transform.get("source", "")
    assert "tinyassets-daemon" in source
    assert "tinyassets-tunnel" in source
    # The host-run worker fleet was deleted 2026-08-29; a `worker` role that no
    # container can carry would be a stale classification, not coverage.
    assert "tinyassets-worker" not in source


def test_vector_has_stdout_sink():
    data = _load_vector()
    sinks = data.get("sinks", {})
    console_sinks = [v for v in sinks.values() if v.get("type") == "console"]
    assert console_sinks, "vector.yaml must have a console/stdout sink (always-on fallback)"


def test_vector_base_has_no_betterstack_sink():
    """Base vector.yaml must NOT contain the betterstack sink — it lives in the
    separate vector-betterstack.yaml fragment to silence 401 errors when the
    token is unset."""
    data = _load_vector()
    sinks = data.get("sinks", {})
    http_sinks = [v for v in sinks.values() if v.get("type") == "http"]
    assert not http_sinks, (
        "base vector.yaml must not contain an http sink — betterstack belongs "
        "in vector-betterstack.yaml (loaded conditionally by vector-entrypoint.sh)"
    )


def test_vector_betterstack_fragment_exists():
    assert VECTOR_BETTERSTACK_YAML.exists(), (
        "deploy/vector-betterstack.yaml must exist (conditional betterstack sink)"
    )


def test_vector_betterstack_fragment_has_http_sink():
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load(VECTOR_BETTERSTACK_YAML.read_text(encoding="utf-8"))
    sinks = data.get("sinks", {})
    http_sinks = [v for v in sinks.values() if v.get("type") == "http"]
    assert http_sinks, "vector-betterstack.yaml must have an HTTP sink"


def test_vector_betterstack_fragment_uses_token_env():
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load(VECTOR_BETTERSTACK_YAML.read_text(encoding="utf-8"))
    sinks = data.get("sinks", {})
    http_sinks = [v for v in sinks.values() if v.get("type") == "http"]
    assert http_sinks
    auth_header = http_sinks[0].get("request", {}).get("headers", {}).get("Authorization", "")
    assert "BETTERSTACK_SOURCE_TOKEN" in auth_header


def test_vector_entrypoint_exists():
    assert VECTOR_ENTRYPOINT.exists(), "deploy/vector-entrypoint.sh must exist"


def test_vector_entrypoint_conditional_betterstack():
    text = VECTOR_ENTRYPOINT.read_text(encoding="utf-8")
    assert "BETTERSTACK_SOURCE_TOKEN" in text
    assert "vector-betterstack.yaml" in text


def test_vector_entrypoint_exec_vector():
    text = VECTOR_ENTRYPOINT.read_text(encoding="utf-8")
    assert "exec vector" in text


def test_compose_mounts_entrypoint():
    data = _load_compose()
    volumes = data["services"]["logs"].get("volumes", [])
    entrypoint_mounts = [v for v in volumes if "vector-entrypoint.sh" in str(v)]
    assert entrypoint_mounts, "compose must mount vector-entrypoint.sh"


def test_compose_mounts_betterstack_fragment():
    data = _load_compose()
    volumes = data["services"]["logs"].get("volumes", [])
    bs_mounts = [v for v in volumes if "vector-betterstack.yaml" in str(v)]
    assert bs_mounts, "compose must mount vector-betterstack.yaml"


def test_vector_yaml_parses_cleanly():
    yaml = pytest.importorskip("yaml")
    # Should not raise
    data = yaml.safe_load(VECTOR_YAML.read_text(encoding="utf-8"))
    assert isinstance(data, dict)




# ---------------------------------------------------------------------------
# Where the forwarded lines come to rest — the journal, not a container
# ---------------------------------------------------------------------------
#
# Regression cover for the 2026-09-26 finding (docs/ops/log-aggregation-runbook.md). The
# `logs` container is the one place every forwarded line exists on this host
# (Vector's console sink re-emits them), so ITS logging driver decides whether a
# deploy erases the evidence. It used to be Docker's default json-file, which
# lives in the container's own directory and dies with it.


def test_logs_service_output_lands_in_the_journal():
    logging = _load_compose()["services"]["logs"].get("logging") or {}
    assert logging.get("driver") == "journald", (
        "the logs sidecar re-emits every forwarded line on its stdout; with a "
        "container-scoped driver (json-file is Docker's default) that copy is "
        "deleted when the container is recreated, which every deploy does"
    )


def test_logs_service_carries_a_stable_journal_tag():
    """Without an explicit tag, Docker's journald driver uses a truncated
    container id, which changes on every recreate — so the query that is
    supposed to read ACROSS recreates would need a different value per
    generation."""
    options = (_load_compose()["services"]["logs"].get("logging") or {}).get("options") or {}
    assert options.get("tag") == "tinyassets-logs"


def test_logs_service_does_not_forward_to_its_own_listener():
    """A `logs` container using the fluent anchor would ship its own stdout into
    the listener that produced it."""
    logging = _load_compose()["services"]["logs"].get("logging") or {}
    assert logging.get("driver") != "fluentd"
    assert "fluentd-address" not in (logging.get("options") or {})


def test_journald_dropin_bounds_retention_in_bytes_and_time():
    """Pointing a chatty container at journald is only safe with caps, and the
    caps are what decide how much history survives."""
    text = JOURNALD_DROPIN.read_text(encoding="utf-8")
    assert "[Journal]" in text
    # Persistent, or the journal is a tmpfs that a reboot empties.
    assert "Storage=persistent" in text
    settings = dict(
        line.split("=", 1)
        for line in text.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    )
    assert settings["SystemMaxUse"] == "1G"
    assert settings["MaxRetentionSec"] == "14day"
    assert settings["SystemKeepFree"] == "2G"
    # Rate limiting drops messages to protect the journal, and a dropped line
    # during an incident is the evidence this whole change exists to keep.
    assert settings["RateLimitBurst"] == "0"


def test_installer_owns_the_journald_dropin():
    text = INSTALLER.read_text(encoding="utf-8")
    assert "deploy/journald-tinyassets.conf" in text
    # Shipped by the manifest, or the file never reaches the droplet: the install
    # workflow builds its bundle from `git archive` over the
    # TINYASSETS_PRINT_MANIFEST output, so a file missing from the manifest is
    # one the installer then refuses on.
    manifest_block = text.split('if [[ "${PRINT_MANIFEST}" == "1" ]]; then', 1)[1]
    manifest_block = manifest_block.split("exit 0", 1)[0]
    assert "JOURNALD_DROPIN_SOURCE" in manifest_block
    assert "restart systemd-journald" in text


def test_log_retention_window_covers_the_offsite_bundle_window():
    """The journal has to hold at least as much history as the nightly bundle
    claims to ship, or the bundle is silently shorter than advertised."""
    dropin = JOURNALD_DROPIN.read_text(encoding="utf-8")
    retention_days = int(
        next(
            line.split("=", 1)[1].removesuffix("day")
            for line in dropin.splitlines()
            if line.startswith("MaxRetentionSec=")
        )
    )
    backup = BACKUP_SH.read_text(encoding="utf-8")
    bundle_days = int(
        next(
            line for line in backup.splitlines() if "BACKUP_LOG_SINCE:-" in line
        ).split("BACKUP_LOG_SINCE:-", 1)[1].split()[0]
    )
    assert retention_days > bundle_days, (
        f"journal keeps {retention_days}d but the nightly tier asks for "
        f"{bundle_days}d"
    )


# ---------------------------------------------------------------------------
# ship-logs retirement
# ---------------------------------------------------------------------------
#
# Retired 2026-09-26. It could not have worked as deployed: it read logs with
# `docker logs`, and Docker refuses that on a container using the fluentd driver
# that compose.yml has given the daemon since Row K. So the hourly
# `ERROR: LOG_DEST is required` was not one missing setting away from shipping
# anything. The nightly backup's logs tier replaces it on a credential the box
# already holds (deploy/backup.sh).


@pytest.mark.parametrize(
    "relative",
    [
        "deploy/ship-logs.sh",
        "deploy/tinyassets-ship-logs.service",
        "deploy/tinyassets-ship-logs.timer",
    ],
)
def test_ship_logs_files_are_gone(relative):
    assert not (REPO_ROOT / relative).exists(), (
        f"{relative} was retired; a copy left in the tree gets re-installed"
    )


def test_installer_removes_the_retired_units_from_the_host():
    """Deleting the files is not the fix on its own. The enabled copies in
    /etc/systemd/system keep firing, which is how this timer logged an ERROR
    hourly for months."""
    text = INSTALLER.read_text(encoding="utf-8")
    assert "RETIRED_UNITS=(" in text
    retired = text.split("RETIRED_UNITS=(", 1)[1].split(")", 1)[0]
    assert "tinyassets-ship-logs.timer" in retired
    assert "tinyassets-ship-logs.service" in retired
    # The timer must be disabled before the service, and both before the unlink.
    assert retired.index("timer") < retired.index("service")
    assert 'disable --now "${unit}"' in text


def test_installer_no_longer_ships_or_enables_ship_logs():
    text = INSTALLER.read_text(encoding="utf-8")
    timers = text.split("TIMERS=(", 1)[1].split(")", 1)[0]
    runtime = text.split("RUNTIME_FILES=(", 1)[1].split(")", 1)[0]
    assert "ship-logs" not in timers
    assert "ship-logs" not in runtime
    # ...and it ships what replaced it.
    assert "scripts/backup_log_tier.py" in runtime
    assert "scripts/redact_log_bundle.py" in runtime


def test_retirement_is_visible_to_the_idempotence_gate():
    """The gate exits before the first mutation when everything looks converged,
    so a retired unit it does not check is a unit that is never removed."""
    text = INSTALLER.read_text(encoding="utf-8")
    gate = text.split("current_release_is_exact() {", 1)[1]
    gate = gate.split("\nif current_release_is_exact", 1)[0]
    assert "RETIRED_UNITS" in gate
    assert "JOURNALD_DROPIN" in gate


def test_nothing_live_still_reads_a_log_dest():
    """LOG_DEST was the host decision this retirement removes: a destination plus
    a credential, for a second off-box log path. A surviving *use* of the
    variable would mean the requirement came back by another name. Naming it in
    a comment is how the retirement stays legible, so match uses, not mentions.
    """
    uses = re.compile(r"\$\{?LOG_DEST|^\s*LOG_DEST=", re.MULTILINE)
    for path in (INSTALLER, BACKUP_SH, COMPOSE):
        found = uses.search(path.read_text(encoding="utf-8"))
        assert found is None, f"{path} still reads LOG_DEST: {found.group(0)!r}"


def test_runbook_leads_with_the_query_that_survives_a_deploy():
    """The runbook is read mid-incident. `docker logs` is scoped to the current
    container, so a responder who reaches for it after a deploy finds nothing --
    which is how the 2026-09-26 evidence was declared lost."""
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "journalctl CONTAINER_NAME=tinyassets-logs" in text
    assert "--output=short-iso-precise" in text
    assert "deploy/journald-tinyassets.conf" in text
    # The off-box path, by the name an operator can actually list.
    assert "Jonnyton/tinyassets-backups" in text
    assert "backup_log_tier.py" in text


def test_runbook_does_not_instruct_a_retired_procedure():
    """A runbook step for a removed unit sends a responder down a dead path."""
    text = RUNBOOK.read_text(encoding="utf-8")
    for stale in (
        "bash /opt/tinyassets-host-uptime/current/deploy/ship-logs.sh",
        "systemctl enable --now tinyassets-ship-logs.timer",
        "LOG_DEST=sftp:",
        "LOG_RETAIN_DAYS",
        "docker-compose@workflow",
        '.service = "workflow"',
    ):
        assert stale not in text, f"runbook still instructs: {stale}"
    # The retirement itself has to be stated, or the next reader re-adds it.
    assert "retired" in text.lower()


def test_runbook_keeps_the_fluentd_drop_visible():
    """The one gap this design leaves: while Vector is down the fluentd driver
    buffers in memory and then drops, so nothing reaches the journal. A runbook
    that omits it invites 'the journal is complete' as an assumption."""
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "drop" in text.lower()
    troubleshooting = text.split("## Troubleshooting", 1)[1]
    assert "Vector container not running" in troubleshooting


def test_the_journald_dropin_is_pinned_to_lf():
    """`git archive` ships this file to /etc/systemd/journald.conf.d/ verbatim,
    and it was authored on Windows. `.gitattributes` already pins `*.service`
    and `*.timer` for exactly this reason; `*.conf` was missing, so the first
    build of this change handed the droplet a CRLF drop-in. systemd happens to
    strip `\r` as whitespace, so it parsed -- which is why nothing would have
    failed loudly, and why this needs a test rather than a reader's attention.
    """
    attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    rules = [
        line.split()
        for line in attributes.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    conf = [rule for rule in rules if rule[0] == "*.conf"]
    assert conf, "*.conf is not pinned in .gitattributes"
    assert "eol=lf" in conf[0], conf[0]
    assert JOURNALD_DROPIN.suffix == ".conf", (
        "the drop-in must keep the .conf suffix the pinned rule matches"
    )
