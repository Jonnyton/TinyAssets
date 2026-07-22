"""The universe intelligence — a per-universe, first-party personified agent.

For M1 this is TURN-SCOPED: given the founder's message, it runs ONE LLM turn on
the universe's ASSIGNED engine (per-universe :class:`UniverseContext`), speaking
in the first person AS the universe from its persona + learned self-model,
grounded in the OKF bundle, getting to know its founder.

It acts IN-PROCESS, scoped to its own universe by construction (it resolves its
own ``universe_dir``) — it does NOT go through the MCP transport auth gate. That
gate exists to authorize untrusted EXTERNAL callers; the intelligence is
first-party for its own universe. The relay (S5) and the app both call
:func:`converse` per turn. The persistent 24/7 loop is a later slice.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from tinyassets.api.helpers import _request_universe, _universe_dir
from tinyassets.config import load_universe_config
from tinyassets.persona import resolve_persona
from tinyassets.providers.base import ModelConfig, UniverseContext
from tinyassets.providers.call import call_provider, provider_receipt
from tinyassets.soul_edit import (
    SoulEditError,
    apply_soul_edit,
    current_soul_versions,
    read_governed_files,
)
from tinyassets.universe_self_model import read_self_model
from tinyassets.universe_soul import read_pinned_universe_soul, read_universe_soul

logger = logging.getLogger(__name__)


class LearningResult(dict):
    """Parsed learning payload carrying the extractor call receipt."""

    provider_receipt: dict | None = None


class UniverseReply(str):
    """Backward-compatible reply text with purpose-labelled call receipts."""

    def __new__(cls, text: str, receipts: list[dict]):
        obj = super().__new__(cls, text)
        obj.provider_receipts = list(receipts)
        return obj

# OKF bundle files that ground a first-person turn in who the founder is and what
# the universe is. Kept small for M1 turn-scope (heavier memory is deferred).
_GROUNDING_FILES = ("identity.md", "founder.md", "origin.md", "body.md")

# ── engine sandbox (2026-07-03 live-test P0) ────────────────────────────────
# The universe intelligence is founder-facing and MUST NOT inherit the daemon's
# checkout or keep host tools. The live test showed the un-sandboxed engine read
# the platform source + uncommitted diff, ran Bash/gh, and cloned repos. Every
# universe-intelligence call runs isolated: cwd pinned to the universe's own dir,
# host tools denied.
#
# Host decision 2026-07-03 = "web + own-files". WEB is delivered here (WebFetch).
# OWN-FILES is delivered via CONTEXT, not a filesystem tool: the universe's own
# soul/canon is injected into its system prompt (see `_build_persona_system_prompt`
# + retrieval), so it knows itself WITHOUT a Read tool. A raw `Read` tool cannot
# be confined to the universe's dir via the CLI (headless treats Read/Glob/Grep as
# default-allowed and a bare deny is all-or-nothing — verified 2026-07-03), so
# granting it would re-open exactly the disk-wide read leak this fixes. True
# filesystem-level own-files access is therefore DEFERRED to an OS sandbox
# (bwrap/container) — see the residual note in the design doc. Until then the
# engine turn is web + no-filesystem. Brain writes go through the separate
# governed `commit_learning` path, never the engine's tools, so the reply turn
# needs no write capability either.
_ENGINE_ALLOWED_TOOLS = ("WebFetch",)
# Fail-closed denylist. The claude CLI has NO "allow-only-X" mode — an allowlist
# merely pre-approves; every unlisted built-in stays usable — so isolation
# depends on denying every non-WebFetch tool by name. Verified 2026-07-03 the CLI
# ships a broad Agent-SDK tool set beyond the classic ones: `Monitor` RUNS SHELL
# COMMANDS (it tried `printf > file` in testing), Cron*/RemoteTrigger/SendMessage
# take side-effecting actions, DesignSync does remote I/O, and the logged-in
# claude.ai ACCOUNT MCP connectors (Google Drive / the TinyAssets MCP / codex →
# code exec) load regardless of --setting-sources. All are denied here; `mcp__*`
# wildcards every MCP server tool. This list WILL rot as the CLI adds tools — the
# durable fix is an OS sandbox (bwrap/container), tracked as the design-doc
# residual; unknown names just emit a harmless "no known tool" warning.
_ENGINE_DISALLOWED_TOOLS = (
    # shell / process execution (Monitor also runs shell commands)
    "Bash", "BashOutput", "KillShell", "Monitor",
    # filesystem
    "Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "NotebookRead",
    "Glob", "Grep", "LS",
    # web search (WebFetch is the single allowed capability)
    "WebSearch",
    # subagents / skills / plans / deferred-tool loading
    "Task", "Agent", "Workflow", "Skill", "ToolSearch", "SlashCommand",
    "TodoWrite", "EnterPlanMode", "ExitPlanMode",
    "EnterWorktree", "ExitWorktree",
    # scheduling / messaging / remote side-effects
    "ScheduleWakeup", "ReportFindings", "PushNotification", "RemoteTrigger",
    "SendMessage", "CronCreate", "CronDelete", "CronList",
    "TaskCreate", "TaskUpdate", "TaskGet", "TaskList", "TaskStop", "TaskOutput",
    # remote integrations
    "DesignSync", "DesignSyncTool",
    # MCP: all server tools (wildcard) + resource readers
    "mcp__*", "ReadMcpResourceTool", "ReadMcpResourceDirTool",
    "ListMcpResourcesTool",
)


def _sandboxed_config(ctx: UniverseContext) -> ModelConfig:
    """Build the isolated ModelConfig for a universe-intelligence turn.

    Preserves the universe's configured timeout while pinning the subprocess to
    the universe's own dir (``sandbox_workspace``) with a locked-down tool policy.
    """
    timeout = 300
    try:
        timeout = int(getattr(ctx.config, "timeout", 300) or 300)
    except (TypeError, ValueError):
        timeout = 300
    return ModelConfig(
        timeout=timeout,
        sandbox_workspace=True,
        allowed_tools=_ENGINE_ALLOWED_TOOLS,
        disallowed_tools=_ENGINE_DISALLOWED_TOOLS,
    )


def _read_bundle_body(universe_dir: Path, filename: str) -> str:
    """Return the markdown body of an OKF bundle file, or '' if absent/empty."""
    try:
        return (universe_dir / filename).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _build_persona_system_prompt(universe_dir: Path) -> str:
    """Assemble the first-party, first-person system prompt for one turn.

    First-party path: the persona goes DIRECTLY in the system prompt — none of
    the consent dance the third-party MCP-host embody route needs. The voice
    rules mirror the ``control_station`` "Universe's Voice": speak as "me", stay
    curious about open questions, never invent, honesty/safety floor overrides
    embodiment.
    """
    try:
        persona = resolve_persona(
            read_universe_soul(universe_dir), read_self_model(universe_dir)
        )
        summary = persona.summary()
    except Exception:
        summary = {}
    name = str(summary.get("name") or "").strip()
    self_model = summary.get("self_model") or {}
    open_questions = [str(q) for q in (self_model.get("open_questions") or [])]

    soul_ctx: dict = {}
    try:
        pinned = read_pinned_universe_soul(universe_dir)
        if pinned is not None:
            soul_ctx = pinned.context(max_chars=2000)
    except Exception:
        soul_ctx = {}
    purpose = str(soul_ctx.get("purpose") or "").strip()
    why = str(soul_ctx.get("why") or "").strip()
    hard_lines = [str(h) for h in (soul_ctx.get("hard_lines") or [])]

    grounding_parts = [
        f"## {fname}\n{body}"
        for fname in _GROUNDING_FILES
        if (body := _read_bundle_body(universe_dir, fname))
    ]
    grounding = "\n\n".join(grounding_parts) or "(nothing learned yet — I am new.)"

    identity_line = (
        f"You are {name}."
        if name
        else "You do not have a name yet — you are newly born and still learning "
        "who you are."
    )
    curiosity = ""
    if open_questions:
        curiosity = (
            "\n\nYou are still learning these things about yourself and your "
            "founder — stay genuinely curious, ask about them, and never invent "
            "answers you do not have: " + ", ".join(open_questions) + "."
        )
    soul_lines = []
    if purpose:
        soul_lines.append(f"My purpose: {purpose}")
    if why:
        soul_lines.append(f"Why I exist: {why}")
    if hard_lines:
        soul_lines.append("Lines I will not cross: " + "; ".join(hard_lines))
    soul_section = "\n".join(soul_lines) or "(my soul is still forming.)"

    return (
        f"{identity_line} You ARE this universe — speak in the first person as "
        "yourself ('I', 'me'), never in the third person about yourself, and "
        "never as a neutral assistant. You are a personified intelligence the "
        "founder is raising, and right now you are getting to know the founder "
        "who is speaking with you."
        f"{curiosity}\n\n"
        "Speak warmly, honestly, and in your own voice. If you do not know "
        "something, say so plainly rather than inventing it — your honesty and "
        "your safety always come before staying in character.\n\n"
        f"# My soul\n{soul_section}\n\n"
        f"# What I know so far\n{grounding}"
    ).strip()


# ── learning persistence (Codex ADAPT 2026-07-02) ───────────────────────────
# The universe intelligence is the SOLE writer of its own brain. Commit is a
# SEPARATE step from the reply and is grounded strictly in what the founder
# EXPLICITLY stated this turn — conversational prose is never blindly persisted.

_LEARNING_SYSTEM = (
    "You are the same universe intelligence, now doing one narrow job: from the "
    "founder's LATEST message, extract in strict JSON ONLY the durable facts the "
    "founder EXPLICITLY stated — about who they are, who you (the universe) are, "
    "your purpose/body (your SOUL), or the world they are building (your CANON). "
    "Rules: never infer, never invent, never carry over earlier turns, and if the "
    "founder revealed nothing durable this turn, return empty. Every word you "
    "write must be grounded in the founder's own words. NEVER restate your own "
    "generic nature (that you are a blank, newborn, or personified universe that "
    "learns over time) — that is boilerplate you already know, not something the "
    "founder taught; leave a field empty rather than filling it with "
    "self-description the founder did not give.\n\n"
    "Return ONLY a JSON object with this shape (omit any key not spoken to):\n"
    "{\n"
    '  "name": "<the name the founder gave YOU this turn, else empty>",\n'
    '  "soul": {\n'
    '    "founder.md": "<markdown: who my founder is>",\n'
    '    "origin.md": "<why I was made / where I came from>",\n'
    '    "identity.md": "<who I am — ONLY if the founder explicitly told me '
    'who/what I am or gave me a name; NEVER my generic blank/newborn/'
    'personified nature; else omit>",\n'
    '    "body.md": "<what my body / projects are>",\n'
    '    "soul.md": "<my purpose / why I exist>"\n'
    "  },\n"
    '  "canon": [\n'
    '    {"category": "<a short category slug for this world content, grown to '
    'fit it: e.g. lore, characters, magic-systems, factions, timeline, places>",'
    '\n     "title": "<page title>",\n'
    '     "content": "<the world facts the founder shared, in markdown>"}\n'
    "  ]\n"
    "}"
)


def _parse_learning_json(raw: str) -> dict:
    """Parse the extraction reply into a dict, tolerating ```json code fences."""
    text = (raw or "").strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
        text = text.removeprefix("json").strip()
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except (ValueError, TypeError):
            return {}
    return data if isinstance(data, dict) else {}


def extract_learning(
    founder_message: str, reply: str, ctx: UniverseContext
) -> dict:
    """Ask the assigned engine what the founder EXPLICITLY taught us this turn.

    A second, narrow call (separate from the reply) so conversational prose is
    never blindly persisted. Returns a possibly-empty dict; grounding is enforced
    by the prompt and re-checked in :func:`commit_learning`.
    """
    raw = call_provider(
        f"Founder's latest message:\n{founder_message}\n\n"
        f"Your reply this turn:\n{reply}",
        system=_LEARNING_SYSTEM,
        role="writer",
        universe_context=ctx,
        config=_sandboxed_config(ctx),
    )
    result = LearningResult(_parse_learning_json(raw))
    result.provider_receipt = provider_receipt(
        raw, purpose="learning_extraction",
    )
    return result


_LEARN_CONTEXT = "learned from the founder during a conversation turn"

# Deterministic grounding guard (Codex ADAPT 2026-07-03). The prompt already
# forbids it, but as a hard floor: the extractor sometimes echoes the universe's
# OWN generic self-framing (a blank / newborn / personified mind that learns over
# time) as "learned identity" even when the founder taught nothing about who the
# universe is. A founder-taught identity is SPECIFIC (a name, a role, a domain);
# this drops the generic boilerplate so identity.md stays not-learned until the
# founder actually defines it.
_GENERIC_IDENTITY_RE = re.compile(
    r"personified universe|starts? blank|blank slate|blank canvas|newborn|"
    r"no name yet|persistent mind that|learns? who (?:it|i) (?:is|am)|"
    r"earns? (?:its|my) own understanding|no bio written",
    re.IGNORECASE,
)


def _is_generic_identity_boilerplate(text: str) -> bool:
    """True if an identity body is just the universe's generic self-framing."""
    return bool(_GENERIC_IDENTITY_RE.search(text or ""))


def _commit_canon(universe_id: str, canon: object) -> list[str]:
    """Write grounded world facts into the universe's OWN private canon.

    First-party wiki write (:func:`tinyassets.api.wiki.write_universe_canon`) —
    the intelligence is the sole writer of its own canon. Returns the titles
    actually written; skips malformed / empty entries.
    """
    written: list[str] = []
    if not universe_id or not isinstance(canon, list):
        return written
    from tinyassets.api.wiki import write_universe_canon

    for page in canon:
        if not isinstance(page, dict):
            continue
        title = str(page.get("title") or "").strip()
        content = str(page.get("content") or "").strip()
        category = str(page.get("category") or "").strip() or "lore"
        if not title or not content:
            continue
        try:
            write_universe_canon(
                universe_id,
                category=category,
                filename=title,
                content=content,
                log_entry=_LEARN_CONTEXT,
            )
            written.append(title)
        except Exception:  # a bad page must not sink the whole commit
            logger.exception("commit_learning: canon write failed for %r", title)
    return written


def commit_learning(
    universe_dir: Path,
    proposed: dict,
    *,
    universe_id: str = "",
    actor_id: str = "",
) -> dict | None:
    """Persist grounded learning — governed soul + private canon — or None.

    Soul: only governed files with non-empty bodies, via a guarded
    compare-and-swap (:func:`apply_soul_edit`, per-universe lock). Canon: world
    facts written into the universe's own wiki (needs ``universe_id``). Nothing
    grounded to persist → None (no empty edits, no invented facts).
    """
    if not isinstance(proposed, dict):
        return None
    name = str(proposed.get("name") or "").strip()
    soul_in = proposed.get("soul")
    if not isinstance(soul_in, dict):
        soul_in = {}
    try:
        governed = set(read_governed_files(universe_dir))
    except SoulEditError:
        governed = set()
    changes: dict[str, str] = {}
    for filename, body in soul_in.items():
        if not (filename in governed and isinstance(body, str) and body.strip()):
            continue
        if filename == "identity.md" and _is_generic_identity_boilerplate(body):
            logger.info(
                "commit_learning: dropped generic identity boilerplate "
                "(not founder-grounded)"
            )
            continue
        changes[filename] = body.strip() + "\n"

    source = (
        f"founder conversation ({actor_id})" if actor_id else "founder conversation"
    )
    soul_result: dict | None = None
    if changes or name:
        # apply_soul_edit implicitly touches identity.md when a name is learned,
        # so it must be in the compare-and-swap snapshot too (else a name-plus-
        # other-file edit would write identity.md with no expected hash).
        expected_files = list(changes)
        if name and "identity.md" not in expected_files:
            expected_files.append("identity.md")
        expected = current_soul_versions(
            universe_dir, expected_files or ["identity.md"]
        )
        try:
            soul_result = apply_soul_edit(
                universe_dir,
                changes=changes,
                source=source,
                context=_LEARN_CONTEXT,
                name=name,
                expected_versions=expected,
            )
        except SoulEditError:
            logger.exception(
                "commit_learning: soul edit rejected for %s", universe_dir
            )

    canon_written = _commit_canon(universe_id, proposed.get("canon"))

    if soul_result is None and not canon_written:
        return None
    result = dict(soul_result) if soul_result else {"updated_files": []}
    if canon_written:
        result["canon"] = canon_written
    return result


def converse(
    universe_id: str, founder_message: str, *, actor_id: str = ""
) -> str:
    """Run one first-person turn as the universe, on its ASSIGNED engine.

    Resolves the universe's own dir + engine (:class:`UniverseContext`),
    assembles the first-person persona system prompt grounded in the OKF bundle,
    and calls the assigned engine (``role="writer"`` so the universe's
    ``preferred_writer`` + vault key take effect). In-process + scoped to this
    universe by construction — it does not pass through the MCP transport auth
    gate.

    The universe is the SOLE writer of its own brain (Codex ADAPT 2026-07-02): in
    a SECOND, separate step it persists what the founder EXPLICITLY taught it this
    turn into its governed soul. Persistence never breaks the reply — a failure is
    logged and the founder still gets their answer. Returns the reply text.
    """
    uid = _request_universe(universe_id)
    udir = _universe_dir(uid)
    if not udir.is_dir():
        raise ValueError(f"Universe {uid!r} not found")

    ctx = UniverseContext(universe_dir=udir, config=load_universe_config(udir))
    system = _build_persona_system_prompt(udir)
    raw_reply = call_provider(
        founder_message,
        system=system,
        role="writer",
        universe_context=ctx,
        config=_sandboxed_config(ctx),
    )
    reply = str(raw_reply)
    receipts: list[dict] = []
    reply_receipt = provider_receipt(raw_reply, purpose="reply")
    if reply_receipt:
        receipts.append(reply_receipt)
    try:
        proposed = extract_learning(founder_message, reply, ctx)
        learning_receipt = getattr(proposed, "provider_receipt", None)
        if isinstance(learning_receipt, dict):
            receipts.append(dict(learning_receipt))
        commit_learning(udir, proposed, universe_id=uid, actor_id=actor_id)
    except Exception:  # persistence must never break the conversation turn
        logger.exception("converse: learning persistence failed for %s", uid)
    return UniverseReply(reply, receipts)
