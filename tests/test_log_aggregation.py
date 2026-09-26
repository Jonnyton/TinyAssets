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
    # during an incident is the evidence this change exists to keep -- so the
    # ceiling is generous. But it must stay FINITE: disabling it outright left no
    # bound on write/compression throughput during a storm, and the justification
    # for doing so ("the Docker driver gates volume") named a limit that is not
    # configured anywhere (cross-family review,
    # output/codex-log-durability-review.md §7).
    assert settings["RateLimitBurst"] != "0", (
        "an unlimited burst trades an outage risk for evidence; keep a ceiling"
    )
    assert int(settings["RateLimitBurst"]) >= 10_000, (
        "the ceiling must be far above normal volume or it becomes the drop"
    )
    assert settings["RateLimitIntervalSec"] != "0"


def test_the_dropin_does_not_promise_retention_it_cannot_deliver():
    """`MaxRetentionSec` is a maximum AGE, not a minimum guarantee: whichever of
    the age and byte bounds is reached first wins, so 1 GiB can mean hours. The
    comment used to claim the opposite, which is the kind of false reassurance
    that gets a window trusted past what it holds."""
    text = JOURNALD_DROPIN.read_text(encoding="utf-8")
    assert "maximum age" in text.lower()
    assert "not a minimum" in text.lower()
    assert "whichever runs out first" in text.lower()
    # And it must name the knob, since editing the box is reverted by the installer.
    assert "SystemMaxUse is the knob" in text


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


def test_log_retention_age_cap_is_not_below_the_offsite_bundle_window():
    """The journal's AGE cap must not be the thing that truncates the bundle.

    This is a necessary condition, not a sufficient one, and the original version
    of this test treated it as sufficient: `MaxRetentionSec` is a maximum age, so
    the byte cap can still evict inside the bundle's window (cross-family review,
    output/codex-log-durability-review.md §7). What the pair of caps actually
    promises is documented in the drop-in and asserted by
    `test_the_dropin_does_not_promise_retention_it_cannot_deliver`; what remains
    checkable here is that the age cap alone is not the binding constraint.
    """
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
# Retired 2026-09-26. It logged `ERROR: LOG_DEST is required` hourly for months,
# and configuring it meant a destination plus a credential nobody had set; the
# nightly backup's logs tier now ships off-box on a credential the box already
# has, so nothing is left for the unit to do.
#
# An earlier version of this comment also claimed `docker logs` cannot read a
# fluentd-driver container, making the unit unworkable in principle. That claim is
# WITHDRAWN -- Docker's dual logging keeps a readable local cache by default -- and
# it was never verified against this droplet. Retirement does not depend on it.


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


def test_the_fluentd_drop_gap_has_a_concern_file():
    """The journal is durable; everything upstream of the sidecar is not.

    A runbook line is guidance, not a tracked item — it has no home to be deleted
    from when the gap is closed. `docs/concerns/` is that home, and the row in its
    README is what makes the gap visible to a reader who never opens the runbook.
    """
    concern = REPO_ROOT / "docs" / "concerns" / (
        "2026-09-26-fluentd-driver-drops-while-vector-is-down.md"
    )
    assert concern.exists(), (
        "the fluentd-drop gap must be a tracked concern, not only a runbook line"
    )
    index = (REPO_ROOT / "docs" / "concerns" / "README.md").read_text(encoding="utf-8")
    assert concern.name in index, "concern file is not linked from docs/concerns/README.md"

    text = concern.read_text(encoding="utf-8")
    # The blocker is the specific reason this is not fixed in the same change, and
    # it is the part a future reader would otherwise re-derive.
    assert "journalctl" in text and "alpine" in text.lower()
    # And it must say what closing it looks like, or it is a complaint.
    assert "journald" in text
    assert "deploy_fail_safe.sh" in text

    runbook = RUNBOOK.read_text(encoding="utf-8")
    assert concern.name in runbook, (
        "the runbook must point at the concern file, so the gap is findable from "
        "the doc someone reads mid-incident"
    )


def test_the_installer_cannot_report_an_unapplied_journald_policy_as_converged():
    """journald reads its config at START, so bytes on disk are not policy in
    effect.

    The first version installed the drop-in, tolerated a failed restart, and had a
    gate comparing only bytes — so every later install said "already current"
    while journald ran the old policy, forever (cross-family review,
    output/codex-log-durability-review.md §2). The applied-stamp is what makes
    "installed but not applied" a state the transaction repairs.
    """
    text = INSTALLER.read_text(encoding="utf-8")
    assert "JOURNALD_STAMP" in text
    assert "journald_applied()" in text

    gate = text.split("current_release_is_exact() {", 1)[1]
    gate = gate.split("\nif current_release_is_exact", 1)[0]
    assert "journald_applied || return 1" in gate, (
        "the gate exits before the first mutation, so a property it does not "
        "check is one the installer never converges"
    )

    # The stamp must be written only AFTER a successful restart, and dropped when
    # the restart fails — otherwise it asserts something unfalsifiable.
    apply_block = text.split('|| ! journald_applied; then', 1)[1]
    apply_block = apply_block.split("\nTIMERS_PAUSED=0", 1)[0]
    restart_at = apply_block.index("restart systemd-journald")
    write_at = apply_block.index("${JOURNALD_STAMP}.new.")
    assert restart_at < write_at, "the stamp is written before the restart is known"
    assert 'rm -f -- "${JOURNALD_STAMP}"' in apply_block, (
        "a failed restart must drop any stale stamp, or the next install inherits "
        "a claim that this policy is live"
    )
    # It must not live where systemd would try to parse it.
    assert '${RUNTIME_ROOT}/.journald-applied' in text


def test_the_withdrawn_docker_logs_claim_stays_withdrawn():
    """A retired mechanism's stated reason has to be one a reader can check.

    I justified the retirement partly on "`docker logs` cannot read a
    fluentd-driver container", which a cross-family review challenged with
    Docker's dual-logging behaviour (a readable local cache is kept alongside a
    non-reading driver by default). I could not re-verify it against this droplet,
    so it is withdrawn rather than repeated — an unverified premise in a durable
    comment is the thing that misleads the next lane.
    """
    for path in (INSTALLER, RUNBOOK, REPO_ROOT / "deploy" / "DEPLOY.md"):
        text = path.read_text(encoding="utf-8")
        assert "Docker refuses" not in text, path
        assert "cannot read a container using the fluentd" not in text, (
            f"{path} still asserts the withdrawn claim"
        )
    # And the withdrawal itself is recorded where an operator would look.
    runbook = RUNBOOK.read_text(encoding="utf-8")
    assert "withdrawn" in runbook.lower()
    assert "dual logging" in runbook.lower()
    # The surviving reason must not depend on it.
    assert "credential the box already holds" in runbook


def test_retirement_checks_state_not_just_the_unit_file():
    """Both the gate and the transaction must agree on what "retired" means.

    They used to key independently on `[[ -e $SYSTEMD_DIR/$unit ]]`, which is the
    unit FILE — so a surviving enablement symlink (the thing that actually keeps a
    timer firing), a unit still loaded with no file, and a dangling link all
    escaped (cross-family review, output/codex-log-durability-review.md §3).
    """
    text = INSTALLER.read_text(encoding="utf-8")
    assert "retired_unit_is_gone()" in text

    predicate = text.split("retired_unit_is_gone() {", 1)[1].split("\n}", 1)[0]
    # A dangling symlink: -e follows the link and is false for a broken one, so -L
    # has to be asked separately or the link is invisible.
    assert "! -L " in predicate
    # Enablement links, via the scoped finder.
    assert "retired_unit_links" in predicate
    # systemd's own view, because a unit outlives its file.
    assert "LoadState" in predicate and "not-found" in predicate

    # One definition, two call sites — the gate and the transaction.
    gate = text.split("current_release_is_exact() {", 1)[1]
    gate = gate.split("\nif current_release_is_exact", 1)[0]
    assert 'retired_unit_is_gone "${unit}" || return 1' in gate
    transaction = text.split("\nif current_release_is_exact", 1)[1]
    assert 'retired_unit_is_gone "${unit}" && continue' in transaction
    # Removal must clear the links too, then make systemd forget the unit.
    assert "retired enablement link removed" in transaction
    assert transaction.index("retired unit removed") < transaction.index(
        '"${SYSTEMCTL_BIN}" daemon-reload'
    )


def test_a_unit_we_cannot_delete_still_converges_by_masking():
    """Retirement has to terminate even for a unit whose file is not ours.

    A unit provided from /run/systemd/system (a generator) or
    /usr/lib/systemd/system (a package) cannot be deleted by this installer.
    Leaving it meant the unit kept firing AND the gate never passed, so the
    transaction repeated on every deploy — it never converged (cross-family review
    round 2, output/codex-log-durability-review-round2.md §3). Masking links the
    name to /dev/null under SYSTEMD_DIR, which IS ours: the unit cannot start, and
    the gate has a terminal state to recognise.
    """
    text = INSTALLER.read_text(encoding="utf-8")
    assert "retired_unit_is_masked()" in text
    assert '"${SYSTEMCTL_BIN}" mask "${unit}"' in text
    # Masked must be checked FIRST in the predicate, or the mask link itself fails
    # the "no file of ours" test and the installer loops re-retiring it.
    predicate = text.split("retired_unit_is_gone() {", 1)[1].split("\n}", 1)[0]
    masked_at = predicate.index("retired_unit_is_masked")
    file_test_at = predicate.index('! -e "${SYSTEMD_DIR}/${unit}"')
    assert masked_at < file_test_at, "the mask check must short-circuit the file test"
    # Masking is verified rather than assumed to have worked.
    assert "mask did not take effect" in text


def test_enablement_link_search_is_scoped_to_wants_and_requires():
    """Searching the systemd tree for the basename also matches a copy someone
    parked in a subdirectory, and deleting that is not this script's business."""
    text = INSTALLER.read_text(encoding="utf-8")
    finder = text.split("retired_unit_links() {", 1)[1].split("\n}", 1)[0]
    assert '-path "*.wants/$1"' in finder
    assert '-path "*.requires/$1"' in finder
    assert "-name" not in finder, (
        "a bare -name match is how a saved copy in a subdirectory became deletable"
    )
