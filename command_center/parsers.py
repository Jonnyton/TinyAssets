"""Pure parsers for the Agent Village collector.

Every function here is side-effect free and independently testable: they take
text/JSON in and return plain dicts. Provider-specific transcript formats:

- Claude Code: ``~/.claude/projects/<slug>/*.jsonl`` — one JSON object per
  line with ``type`` (assistant/user/last-prompt), ``timestamp``, ``cwd``,
  ``sessionId``, ``isSidechain`` (True inside Task-subagent turns), and
  ``message.content[]`` blocks (tool_use / text / thinking).
- Codex CLI: ``~/.codex/sessions/**/rollout-*.jsonl`` — lines with
  ``timestamp``, ``type`` (``response_item`` / ``session_meta`` …) and a
  ``payload`` (``function_call`` items carry shell commands).
- Kimi CLI: ``~/.kimi-code/session_index.jsonl`` maps sessionId → sessionDir /
  workDir; each session dir has ``state.json`` and an ``agents/`` subdir whose
  children are subagent runs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Generic helpers


def slugify(text: str, max_len: int = 40) -> str:
    """Filesystem/URL-safe slug for agent ids and inbox files."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].strip("-") or "agent"


def tail_jsonl(path: Path, max_lines: int = 60, max_bytes: int = 262_144) -> list[dict]:
    """Parse the last ``max_lines`` JSON lines of a transcript file.

    Reads at most ``max_bytes`` from the end so multi-MB transcripts are cheap.
    Malformed lines are skipped, never fatal.
    """
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            fh.seek(max(0, size - max_bytes))
            raw = fh.read()
    except OSError:
        return []
    lines = raw.split(b"\n")[-max_lines:]
    out: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def head_jsonl(path: Path, max_lines: int = 30, max_bytes: int = 65_536) -> list[dict]:
    """Parse the first ``max_lines`` JSON lines — where a session's opening

    prompt lives (queue-operation enqueue / first user message)."""
    try:
        with path.open("rb") as fh:
            raw = fh.read(max_bytes)
    except OSError:
        return []
    out: list[dict] = []
    for line in raw.split(b"\n")[:max_lines]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


_PROMPT_SKIP = ("<", "caveat:", "[{", "system-reminder", "caveat")


def make_label(text: object, max_len: int = 34) -> str:
    """Turn a raw prompt/task into a short human label for a sprite name tag."""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    lowered = cleaned.lower()
    if not cleaned or any(lowered.startswith(skip) for skip in _PROMPT_SKIP):
        return ""
    cleaned = cleaned.strip('"\'`')
    if len(cleaned) <= max_len:
        return cleaned
    cut = cleaned[: max_len + 1]
    if " " in cut:
        cut = cut[: cut.rindex(" ")]
    return cut.rstrip(".,;:") + "…"


def iso_to_epoch(ts: object) -> float | None:
    """Best-effort ISO-8601 → epoch seconds. None when unparseable."""
    if not isinstance(ts, str) or len(ts) < 10:
        return None
    from datetime import datetime, timezone

    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


# ---------------------------------------------------------------------------
# STATUS.md Work table

_STATUS_RE = re.compile(r"^(claimed:[\w.-]+|in-flight)\b")


def parse_status_claims(status_md: str) -> list[dict]:
    """Extract active (claimed/in-flight) rows from the STATUS.md Work table."""
    rows: list[dict] = []
    in_table = False
    for line in status_md.splitlines():
        if line.startswith("| Task "):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                in_table = False
                continue
            if line.startswith("|--") or line.startswith("|-"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 4:
                continue
            task, files, depends, status = cells[0], cells[1], cells[2], cells[3]
            m = _STATUS_RE.match(status)
            if not m:
                continue
            provider = status.split(":", 1)[1].split()[0] if ":" in status else ""
            rows.append(
                {
                    "task": re.sub(r"\*\*", "", task),
                    "files": [f.strip() for f in re.split(r"[,;]", files) if f.strip()],
                    "depends": depends,
                    "status": status,
                    "provider": provider,
                    "active": "ACTIVE" in status,
                }
            )
    return rows


# ---------------------------------------------------------------------------
# Claude Code transcripts

_VERB_BY_TOOL = {
    "Edit": "editing",
    "Write": "writing",
    "Read": "reading",
    "NotebookEdit": "editing notebook",
    "Bash": "running",
    "Grep": "searching",
    "Glob": "mapping files in",
    "Agent": "dispatching a subagent",
    "Task": "dispatching a subagent",
    "WebSearch": "searching the web for",
    "FetchURL": "fetching",
    "TodoWrite": "replanning",
    "Skill": "loading skill",
    "mcp__wiki__wiki_write": "writing wiki page",
    "mcp__wiki__wiki_search": "searching the wiki",
}


def _tool_action(name: str, tool_input: dict) -> tuple[str, str | None]:
    """Humanize one tool_use block → (action text, file path if any)."""
    verb = _VERB_BY_TOOL.get(name, f"using {name} on")
    target = (
        tool_input.get("file_path")
        or tool_input.get("path")
        or tool_input.get("pattern")
        or tool_input.get("command")
        or tool_input.get("prompt")
        or tool_input.get("description")
        or ""
    )
    target = str(target).replace("\n", " ").strip()
    if len(target) > 80:
        target = target[:77] + "…"
    file_path = tool_input.get("file_path") or tool_input.get("path") or None
    action = f"{verb} {target}".strip()
    return action, file_path


def parse_claude_transcript(entries: list[dict]) -> dict:
    """Summarize a Claude Code transcript (head + tail entries together).

    Returns cwd, session id, git branch, last epoch, current action + file,
    sidechain (subagent) activity, the session's opening prompt, and the last
    user prompt.
    """
    info: dict = {
        "cwd": None,
        "session_id": None,
        "branch": None,
        "ts": None,
        "action": None,
        "file": None,
        "sidechain": False,
        "first_prompt": None,
        "last_prompt": None,
        "model": None,
    }
    for entry in entries:
        ts = iso_to_epoch(entry.get("timestamp"))
        if ts:
            info["ts"] = ts
        if entry.get("cwd") and not info["cwd"]:
            info["cwd"] = entry["cwd"]
        if entry.get("sessionId") and not info["session_id"]:
            info["session_id"] = entry["sessionId"]
        if entry.get("gitBranch") and not info["branch"]:
            info["branch"] = entry["gitBranch"]
        if entry.get("isSidechain"):
            info["sidechain"] = True
        etype = entry.get("type")
        if etype == "last-prompt" and entry.get("lastPrompt"):
            info["last_prompt"] = str(entry["lastPrompt"])[:200]
        if etype == "queue-operation" and entry.get("operation") == "enqueue":
            content = str(entry.get("content") or "")
            if content and not info["first_prompt"]:
                info["first_prompt"] = content[:300]
            if content:
                info["last_prompt"] = info["last_prompt"] or content[:200]
        message = entry.get("message") or {}
        if not info["model"] and isinstance(message, dict) and message.get("model"):
            info["model"] = message["model"]
        content = message.get("content") if isinstance(message, dict) else None
        if etype == "user" and isinstance(content, str) and content.strip():
            if not info["first_prompt"]:
                info["first_prompt"] = content.strip()[:300]
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text" and etype == "user":
                    text = str(block.get("text") or "").strip()
                    if text and not info["first_prompt"]:
                        info["first_prompt"] = text[:300]
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    action, file_path = _tool_action(
                        str(block.get("name") or ""), block.get("input") or {}
                    )
                    info["action"], info["file"] = action, file_path
    return info


# ---------------------------------------------------------------------------
# Codex CLI rollout transcripts


def parse_codex_rollout(entries: list[dict]) -> dict:
    """Summarize a Codex CLI rollout tail (same shape as the Claude one)."""
    info: dict = {
        "cwd": None,
        "session_id": None,
        "branch": None,
        "ts": None,
        "action": None,
        "file": None,
        "sidechain": False,
        "first_prompt": None,
        "last_prompt": None,
        "model": None,
    }
    for entry in entries:
        ts = iso_to_epoch(entry.get("timestamp"))
        if ts:
            info["ts"] = ts
        payload = entry.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        ptype = payload.get("type")
        if ptype == "session_meta" or entry.get("type") == "session_meta":
            meta = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
            info["cwd"] = info["cwd"] or meta.get("cwd")
            info["session_id"] = info["session_id"] or meta.get("id")
            continue
        if ptype == "function_call":
            args = payload.get("arguments") or ""
            command = args
            try:
                parsed = json.loads(args)
                if isinstance(parsed, dict):
                    cmd = parsed.get("command")
                    command = (
                        " ".join(str(c) for c in cmd) if isinstance(cmd, list) else str(cmd or args)
                    )
            except (ValueError, TypeError):
                pass
            command = str(command).replace("\n", " ").strip()
            if len(command) > 80:
                command = command[:77] + "…"
            info["action"] = f"running {command}"
            info["file"] = None
        elif ptype == "message" and payload.get("role") == "user":
            content = payload.get("content") or []
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("text"):
                        text = str(block["text"])
                        if not info["first_prompt"]:
                            info["first_prompt"] = text[:300]
                        info["last_prompt"] = text[:200]
                        break
    return info


# ---------------------------------------------------------------------------
# .agents/activity.log

_ACTIVITY_RE = re.compile(
    r"^-?\s*\[?(?P<date>\d{4}-\d{2}-\d{2}(?:[T ][0-9:.-]+(?:[+-]\d{2}:?\d{2}|Z)?)?)\]?"
    r"\s*(?:\[?(?P<actor>[A-Za-z][\w-]{1,30})\]?:?)?\s*(?P<text>.+)$"
)


def parse_activity_log(text: str, limit: int = 40) -> list[dict]:
    """Parse the heterogeneous .agents/activity.log into feed events."""
    events: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 12:
            continue
        m = _ACTIVITY_RE.match(line)
        if not m:
            continue
        text_part = m.group("text").strip()
        if len(text_part) > 160:
            text_part = text_part[:157] + "…"
        events.append(
            {
                "ts": iso_to_epoch(m.group("date")),
                "actor": (m.group("actor") or "someone").lower(),
                "kind": "note",
                "text": text_part,
            }
        )
    return events[-limit:]


# ---------------------------------------------------------------------------
# Zones

_DIR_PRUNE = {
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".svelte-kit",
    "dist",
    "build",
    "codex-tmp",
    ".pytest-tmp",
    ".codex-test-tmp",
    ".workflow-test-data",
}


def norm_rel(path: str, root: Path) -> str | None:
    """Absolute path → repo-relative POSIX path, or None when outside root."""
    try:
        rel = Path(path).resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return rel.as_posix()


def zone_for_relpath(relpath: str, zone_dirs: dict[str, str]) -> str:
    """Map a repo-relative path to a zone id.

    ``zone_dirs`` maps zone id → directory prefix ("" for the repo-root zone).
    Longest prefix wins; falls back to the root zone.
    """
    best, best_len = "square", -1
    for zone_id, prefix in zone_dirs.items():
        if not prefix:
            continue
        if relpath == prefix or relpath.startswith(prefix + "/"):
            if len(prefix) > best_len:
                best, best_len = zone_id, len(prefix)
    return best
