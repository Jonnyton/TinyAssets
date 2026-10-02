"""Where every entry of a command center's home belongs after the cutover.

`openspec/changes/command-center-cutover` design E6, agreed with
`target-architecture` D8a (#4263). One rule decides: anything the daemon TRUSTS
(authority, identity, owner settings, records) is ``platform`` state and moves
to ``.platform/cc-<ulid>/``; anything the person or their agent may write is
``user`` content and stays in ``cc-<ulid>/`` (the future box volume), read by the
daemon as untrusted.

`classify` is the one table both the read-only inventory and the migration use.
An entry it does not know returns ``None``: the inventory reports it, and the
migration refuses to run until it is classified here, so nothing is guessed into
the box. Extend the table; never add a default.
"""

from __future__ import annotations

import re

USER = "user"
PLATFORM = "platform"

#: Agent- or person-written content (exact entry names in a home).
USER_NAMES = frozenset({
    # brain and harness (AGENT_BRAIN_FILES / AGENT_HARNESS_DIRS)
    "AGENTS.md", "soul.md", "soul_versions", "voice.md", "identity.md", "founder.md",
    "origin.md", "body.md", "orgchart.md", "projects.md", "goals.md", "index.md",
    "log.md", "skills", "prompts", "extensions", "workflows", "bin", "notes",
    "notes.json", "wiki",
    # agent-editable settings; its authority fields move out (design E6)
    "config.yaml",
    # content the agent or a run wrote, uploads, permanent workspaces
    "workspaces", "canon", "output", "artifacts", "PROGRAM.md", "progress.md",
    "design-proposals", "feature-requests", "patch-requests",
    # fiction-domain brain data the agent maintains
    "timeline.json", "promises.json", "facts.json", "characters.json",
})

#: State the daemon trusts (exact entry names in a home).
PLATFORM_NAMES = frozenset({
    # trusted policies
    "soul.edit.md", "dispatcher_config.yaml",
    # records, ledgers, status, assignment and routing
    "activity.log", "status.json", "universe.json", "work_targets.json",
    "ledger.json", "provider_definitions.json", "hard_priorities.json",
    "requests.json", "subscriptions.json", "branch_tasks.json",
    "branch_tasks_archive.json", "auto_ship_attempts.jsonl", "bid_ledger.json",
    "bid_execution_log.json", "enrichment_signals.json", "worldbuild_signals.json",
    "platform-expected-instance.json", "uptime-probe", "executions", "runs",
    "reviews", "settlements", "discarded_targets", "archived",
    "app_refresh_sessions", "import", "import-verify", "verify",
    # stores
    "lancedb", "rules.db",
    # credentials and runtime
    ".credentials", ".credential-vault.json", ".oauth-refresh", ".runtime",
    ".runtime_status.json", ".engine_mcp_config.json", ".engine_mcp_http_routes.json",
    ".pause", ".agent-sessions", ".consumer_liveness", ".quarantine",
    ".workspace-staging", ".authoring_blobs", ".tinyassets_auth_probe.json",
    ".idle_cycle_stamp.json",
})

#: Name patterns for platform bookkeeping: databases and their WAL family,
#: locks, worker-supervisor state, id markers.
_PLATFORM_PATTERNS = (
    re.compile(r".+\.db(?:-wal|-shm|-journal)?$"),
    re.compile(r".+\.db\.bak-.+$"),  # migration backups of a database, with their WAL
    re.compile(r".+\.lock$"),
    re.compile(r"^\.worker_supervisor(?:\..+)?\.json$"),
    re.compile(r"^\.(?:universe|command_center)_id$"),
)

#: Top-level markdown the agent writes (notes, reports) is content.
_USER_PATTERNS = (re.compile(r"^[^.].*\.md$"),)

#: Authority fields that must leave the agent-editable config.yaml (#4263 D8a):
#: config.py:60-66 and the routing ceiling the router enforces.
CONFIG_AUTHORITY_FIELDS = (
    "engine_assignment_state",
    "engine_assignment_generation",
    "provider_authority_bindings",
    "allowed_providers",
)


def classify(name: str) -> str | None:
    """``user``, ``platform``, or ``None`` when this table does not know it."""
    if name in PLATFORM_NAMES:
        return PLATFORM
    if name in USER_NAMES:
        return USER
    if any(pattern.match(name) for pattern in _PLATFORM_PATTERNS):
        return PLATFORM
    if any(pattern.match(name) for pattern in _USER_PATTERNS):
        return USER
    return None
