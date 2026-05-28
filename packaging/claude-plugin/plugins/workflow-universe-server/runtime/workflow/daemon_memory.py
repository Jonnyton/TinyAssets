"""Bounded memory governor for soul-bearing daemon wikis.

The daemon wiki is durable host-local storage. Runtime prompts get a bounded
memory packet built from that storage, not the entire wiki.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MIB = 1024 * 1024

DEFAULT_FIRST_MONTH_CAP_BYTES = 16 * MIB
DEFAULT_USER_PLATEAU_BYTES = 64 * MIB
DEFAULT_PROJECT_PLATEAU_BYTES = 128 * MIB
DEFAULT_FIRST_MONTH_DAYS = 30
DEFAULT_PLATEAU_DAYS = 365
DEFAULT_MEMORY_PACKET_CHARS = 8000
DEFAULT_BRAIN_PACKET_CHARS = 1600

VALID_CAP_POLICIES = {"fixed", "age_scaled", "custom"}

_PROTECTED_FILES = {
    "WIKI.md",
    "index.md",
    "log.md",
    "raw/initial-soul.md",
}
_PROTECTED_PREFIXES = (
    "pages/",
    "drafts/",
    "claim_proofs/",
    "soul_versions/",
    "status/",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _as_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _metadata_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _is_project_daemon(daemon: dict[str, Any]) -> bool:
    metadata = _metadata_dict(daemon.get("metadata"))
    return bool(
        metadata.get("project_loop_default")
        or metadata.get("project_loop_primary")
        or metadata.get("loop_primary")
        or metadata.get("project_default")
    )


def _wiki_metadata(daemon: dict[str, Any]) -> dict[str, Any]:
    return _metadata_dict(_metadata_dict(daemon.get("metadata")).get("daemon_wiki"))


def daemon_memory_policy(
    daemon: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the effective bounded-memory policy for a daemon.

    Defaults intentionally plateau. A one-year default daemon and a fifty-year
    default daemon should have the same memory footprint unless the host opted
    into a larger policy.
    """
    current = now or _utc_now()
    wiki_meta = _wiki_metadata(daemon)
    raw_policy = str(wiki_meta.get("cap_policy") or "age_scaled").strip()
    cap_policy = raw_policy if raw_policy in VALID_CAP_POLICIES else "age_scaled"

    project_daemon = _is_project_daemon(daemon)
    default_plateau = (
        DEFAULT_PROJECT_PLATEAU_BYTES
        if project_daemon
        else DEFAULT_USER_PLATEAU_BYTES
    )
    first_month_cap = _as_int(
        wiki_meta.get("first_month_cap_bytes"),
        DEFAULT_FIRST_MONTH_CAP_BYTES,
    )
    plateau_cap = _as_int(wiki_meta.get("plateau_cap_bytes"), default_plateau)
    custom_cap = _as_int(wiki_meta.get("cap_bytes"), plateau_cap)
    first_month_days = _as_int(
        wiki_meta.get("first_month_days"),
        DEFAULT_FIRST_MONTH_DAYS,
    )
    plateau_days = max(
        first_month_days,
        _as_int(wiki_meta.get("plateau_days"), DEFAULT_PLATEAU_DAYS),
    )

    created_at = _parse_datetime(daemon.get("created_at"))
    age_days: float | None = None
    if created_at is not None:
        age_days = max(0.0, (current - created_at).total_seconds() / 86400.0)

    if cap_policy == "custom":
        cap_bytes = custom_cap
    elif cap_policy == "fixed" or age_days is None:
        cap_bytes = plateau_cap
    elif age_days <= first_month_days:
        cap_bytes = min(first_month_cap, plateau_cap)
    elif age_days >= plateau_days:
        cap_bytes = plateau_cap
    else:
        span = max(1.0, float(plateau_days - first_month_days))
        fraction = (age_days - first_month_days) / span
        cap_bytes = int(first_month_cap + ((plateau_cap - first_month_cap) * fraction))

    return {
        "cap_policy": cap_policy,
        "cap_bytes": int(cap_bytes),
        "first_month_cap_bytes": int(first_month_cap),
        "plateau_cap_bytes": int(plateau_cap),
        "custom_cap_bytes": int(custom_cap),
        "first_month_days": int(first_month_days),
        "plateau_days": int(plateau_days),
        "age_days": age_days,
        "project_daemon": project_daemon,
    }


def _iter_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [path for path in root.rglob("*") if path.is_file()]


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_protected(path: Path, root: Path) -> bool:
    rel = _rel(path, root)
    if rel in _PROTECTED_FILES:
        return True
    return any(rel.startswith(prefix) for prefix in _PROTECTED_PREFIXES)


def daemon_wiki_status(
    base_path: str | Path,
    *,
    daemon_id: str,
    daemon: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return byte-level status for a daemon wiki."""
    from workflow.daemon_registry import get_daemon
    from workflow.daemon_wiki import daemon_wiki_root

    resolved_daemon = daemon or get_daemon(
        base_path,
        daemon_id=daemon_id,
        include_soul=False,
    )
    root = daemon_wiki_root(base_path, daemon_id)
    policy = daemon_memory_policy(resolved_daemon, now=now)
    files = _iter_files(root)

    total_bytes = 0
    protected_bytes = 0
    evictable_signal_bytes = 0
    evictable_signal_count = 0
    for path in files:
        size = path.stat().st_size
        total_bytes += size
        if _is_protected(path, root):
            protected_bytes += size
        elif path.parent == root / "raw" / "signals":
            evictable_signal_bytes += size
            evictable_signal_count += 1

    cap_bytes = int(policy["cap_bytes"])
    usage_ratio = (total_bytes / cap_bytes) if cap_bytes else 0.0
    return {
        "daemon_id": daemon_id,
        "host_local": True,
        "exists": root.exists(),
        "wiki_root": str(root),
        "cap_policy": policy["cap_policy"],
        "cap_bytes": cap_bytes,
        "total_bytes": total_bytes,
        "protected_bytes": protected_bytes,
        "evictable_signal_bytes": evictable_signal_bytes,
        "evictable_signal_count": evictable_signal_count,
        "file_count": len(files),
        "usage_ratio": usage_ratio,
        "pressure_level": (
            "over_cap"
            if total_bytes > cap_bytes
            else "high"
            if usage_ratio >= 0.85
            else "ok"
        ),
        "needs_compaction": total_bytes > cap_bytes,
        "policy": policy,
    }


def _signal_candidates(root: Path) -> list[Path]:
    signals = root / "raw" / "signals"
    if not signals.exists():
        return []
    return sorted(
        [path for path in signals.glob("*.md") if path.is_file()],
        key=lambda path: (path.stat().st_mtime, path.name),
    )


def _append_compaction_summary(
    root: Path,
    *,
    removed: list[Path],
    before_bytes: int,
    after_bytes: int,
    cap_bytes: int,
    now: datetime,
) -> None:
    if not removed:
        return
    summary_path = root / "pages" / "signals" / "compaction-summary.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    if not summary_path.exists():
        summary_path.write_text(
            "---\n"
            "title: Compaction Summary\n"
            "type: memory_compaction\n"
            "---\n\n"
            "# Compaction Summary\n",
            encoding="utf-8",
            newline="\n",
        )
    lines = [
        f"\n## [{stamp}] signal compaction\n",
        f"- Before bytes: {before_bytes}",
        f"- After bytes: {after_bytes}",
        f"- Cap bytes: {cap_bytes}",
        f"- Removed signal records: {len(removed)}",
    ]
    for path in removed[:20]:
        lines.append(f"  - `{path.name}`")
    if len(removed) > 20:
        lines.append(f"  - ... {len(removed) - 20} more")
    with summary_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def _trim_sectioned_page(
    path: Path,
    *,
    keep_sections: int,
    compacted_label: str,
) -> int:
    if keep_sections <= 0 or not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")
    chunks = text.split("\n## [")
    if len(chunks) <= keep_sections + 1:
        return 0
    header = chunks[0].rstrip()
    entries = ["## [" + chunk.rstrip() for chunk in chunks[1:]]
    removed_count = len(entries) - keep_sections
    compacted_note = (
        "\n\n## Compacted History\n\n"
        f"- {removed_count} older {compacted_label} were compacted out of "
        "this maintained page. Raw records may already have been pruned "
        "according to the daemon memory cap.\n"
    )
    kept = "\n\n".join(entries[-keep_sections:])
    path.write_text(
        header + compacted_note + "\n\n" + kept + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return removed_count


def compact_daemon_wiki(
    base_path: str | Path,
    *,
    daemon_id: str,
    daemon: dict[str, Any] | None = None,
    cap_bytes: int | None = None,
    min_recent_signals: int = 25,
    dry_run: bool = False,
    now: datetime | None = None,
    keep_digest_entries: int = 50,
) -> dict[str, Any]:
    """Compact evictable signal records until the wiki is within cap.

    Maintained pages, claim proofs, soul versions, and audit/status files are
    protected. This first slice only prunes raw signal files; synthesis quality
    can improve later without changing the public status/packet contract.
    """
    from workflow.daemon_wiki import daemon_wiki_root

    current = now or _utc_now()
    before = daemon_wiki_status(
        base_path,
        daemon_id=daemon_id,
        daemon=daemon,
        now=current,
    )
    root = daemon_wiki_root(base_path, daemon_id)
    if not root.exists():
        return {
            "daemon_id": daemon_id,
            "dry_run": dry_run,
            "removed": [],
            "before": before,
            "after": before,
            "note": "wiki does not exist",
        }

    effective_cap = int(cap_bytes or before["cap_bytes"])
    candidates = _signal_candidates(root)
    if min_recent_signals > 0 and len(candidates) > min_recent_signals:
        candidates = candidates[: -min_recent_signals]
    elif min_recent_signals > 0:
        candidates = []

    total = int(before["total_bytes"])
    removed: list[Path] = []
    for path in candidates:
        if total <= effective_cap:
            break
        size = path.stat().st_size
        removed.append(path)
        total -= size
        if not dry_run:
            path.unlink()

    trimmed_digest_entries = 0
    if not dry_run:
        trimmed_digest_entries = _trim_sectioned_page(
            root / "pages" / "signals" / "learning-signals.md",
            keep_sections=keep_digest_entries,
            compacted_label="learning signal digests",
        )

    after = daemon_wiki_status(
        base_path,
        daemon_id=daemon_id,
        daemon=daemon,
        now=current,
    )
    if removed and not dry_run:
        _append_compaction_summary(
            root,
            removed=removed,
            before_bytes=int(before["total_bytes"]),
            after_bytes=int(after["total_bytes"]),
            cap_bytes=effective_cap,
            now=current,
        )
        after = daemon_wiki_status(
            base_path,
            daemon_id=daemon_id,
            daemon=daemon,
            now=current,
        )

    return {
        "daemon_id": daemon_id,
        "dry_run": dry_run,
        "removed": [_rel(path, root) for path in removed],
        "trimmed_digest_entries": trimmed_digest_entries,
        "before": before,
        "after": after,
        "cap_bytes": effective_cap,
        "unresolved_over_cap": int(after["total_bytes"]) > effective_cap,
    }


def _read_section(
    root: Path,
    rel_path: str,
    *,
    remaining: int,
) -> tuple[str, bool]:
    if remaining <= 0:
        return "", True
    path = root / rel_path
    if not path.exists():
        return "", False
    text = path.read_text(encoding="utf-8")
    section = f"\n\n<!-- {rel_path} -->\n{text.strip()}\n"
    if len(section) > remaining:
        marker = "\n[truncated]\n"
        if remaining <= len(marker):
            return section[:remaining], True
        return section[: remaining - len(marker)].rstrip() + marker, True
    return section, False


def _default_brain_query(daemon: dict[str, Any]) -> str:
    claims = daemon.get("domain_claims") or []
    metadata = _metadata_dict(daemon.get("metadata"))
    role_terms = [
        str(metadata.get("loop_core_role") or ""),
        str(metadata.get("fixed_llm") or metadata.get("pinned_llm") or ""),
    ]
    return " ".join(
        item.strip()
        for item in [*role_terms, *[str(claim) for claim in claims]]
        if item and item.strip()
    )


def build_daemon_memory_packet(
    base_path: str | Path,
    *,
    daemon_id: str,
    max_chars: int = DEFAULT_MEMORY_PACKET_CHARS,
    enforce_cap: bool = True,
    include_brain: bool = True,
    brain_query: str | None = None,
    brain_max_chars: int = DEFAULT_BRAIN_PACKET_CHARS,
    brain_limit: int = 5,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the bounded soul/wiki context packet for one daemon run."""
    from workflow.daemon_registry import get_daemon
    from workflow.daemon_wiki import daemon_wiki_root, scaffold_daemon_wiki

    current = now or _utc_now()
    daemon = get_daemon(base_path, daemon_id=daemon_id, include_soul=True)
    if not daemon.get("has_soul"):
        raise ValueError("soulless daemons do not have memory packets")

    scaffold_daemon_wiki(
        base_path,
        daemon=daemon,
        soul_text=str(daemon.get("soul_text") or ""),
    )
    compaction = None
    if enforce_cap:
        compaction = compact_daemon_wiki(
            base_path,
            daemon_id=daemon_id,
            daemon=daemon,
            now=current,
        )
    status = daemon_wiki_status(
        base_path,
        daemon_id=daemon_id,
        daemon=daemon,
        now=current,
    )
    root = daemon_wiki_root(base_path, daemon_id)

    budget = max(0, int(max_chars))
    soul_text = str(daemon.get("soul_text") or "").strip()
    soul_capsule = soul_text[:1200].rstrip()
    if len(soul_text) > len(soul_capsule):
        soul_capsule += "\n[truncated]"

    header = (
        "# Daemon Memory Packet\n\n"
        f"- Daemon: {daemon.get('display_name')} ({daemon_id})\n"
        f"- Soul hash: {daemon.get('soul_hash')}\n"
        f"- Domain claims: {', '.join(daemon.get('domain_claims') or []) or 'none'}\n"
        f"- Wiki bytes: {status['total_bytes']} / {status['cap_bytes']}\n"
        f"- Pressure: {status['pressure_level']}\n\n"
        "## Soul Capsule\n\n"
        f"{soul_capsule or 'No soul text available.'}\n"
    )
    context = header[:budget]
    truncated = len(header) > budget
    reserved_brain_chars = 0
    if include_brain and brain_query is not None and not truncated:
        reserved_brain_chars = min(
            max(0, int(brain_max_chars)),
            max(0, budget - len(context)),
        )

    for rel_path in (
        "WIKI.md",
        "index.md",
        "pages/decisions/decision-policy.md",
        "pages/self-model/current-self.md",
        "pages/brain/blocked-patterns.md",
        "pages/brain/review.md",
        "pages/signals/compaction-summary.md",
        "pages/signals/learning-signals.md",
        "pages/soul-evolution/proposals.md",
    ):
        if truncated:
            break
        wiki_remaining = budget - len(context) - reserved_brain_chars
        if wiki_remaining <= 0:
            break
        section, section_truncated = _read_section(
            root,
            rel_path,
            remaining=wiki_remaining,
        )
        context += section
        truncated = section_truncated

    brain = None
    if include_brain and (not truncated or reserved_brain_chars > 0):
        remaining = budget - len(context)
        if remaining > 0:
            from workflow.daemon_brain import DaemonBrain

            brain = DaemonBrain(base_path, daemon_id=daemon_id).build_packet(
                query=brain_query if brain_query is not None else _default_brain_query(daemon),
                max_chars=min(max(0, int(brain_max_chars)), remaining),
                limit=brain_limit,
            )
            brain_section = "\n\n" + str(brain.get("context") or "")
            if len(brain_section) > remaining:
                marker = "\n[truncated]\n"
                if remaining <= len(marker):
                    brain_section = brain_section[:remaining]
                else:
                    brain_section = (
                        brain_section[: remaining - len(marker)].rstrip() + marker
                    )
                truncated = True
            context += brain_section

    return {
        "daemon_id": daemon_id,
        "host_local": True,
        "exists": root.exists(),
        "schema_version": 1,
        "context": context.strip(),
        "max_chars": budget,
        "truncated": truncated,
        "memory_status": status,
        "compaction": compaction,
        "brain": brain,
    }
