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

from tinyassets.api import interlocutor
from tinyassets.api.helpers import _request_universe, _universe_dir
from tinyassets.config import load_universe_config
from tinyassets.persona import read_persona_voice, resolve_persona
from tinyassets.providers.base import ModelConfig, UniverseContext
from tinyassets.providers.call import call_provider
from tinyassets.soul_edit import (
    SoulEditError,
    apply_soul_edit,
    current_soul_versions,
    read_governed_files,
)
from tinyassets.universe_self_model import read_self_model
from tinyassets.universe_soul import read_pinned_universe_soul, read_universe_soul

logger = logging.getLogger(__name__)

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

# ── engine MCP tools (2026-08-13) ───────────────────────────────────────────
# Founder directive: "all user functions are just mcp functions ... all the same
# mcp commands whether its through the app or through slack or the browser." When
# enabled (env flag, FOUNDER turn only), the engine gets a LOCAL, founder-scoped
# TinyAssets MCP server exposing the same canonical handles the browser chatbot
# has, acting AS the founder, pinned to its OWN universe (see
# tinyassets.engine_mcp_server + claude_provider._engine_mcp_flags).
#
# Slice 1 = READ handles only (``read_graph`` + ``get_status``): inspection with
# NO domain mutation / spend / commons blast radius (the status path may touch
# internal infra sidecars — locks/queue markers — but no domain state or cost),
# and enough to prove the whole mechanism end-to-end live (identity binding +
# graph pin + CLI wiring). Both pin cleanly to the universe via their
# ``graph_id`` / ``universe_id`` parameter, and the founder identity gates reads
# of a PRIVATE universe.
#
# DEFERRED, each gated on the matching cross-family confinement review:
#   * ``write_graph`` / ``run_graph`` (slice 2) — WRITES + SPEND on the founder's
#     own subscription. Their target/operation surface has daemon- and
#     registry-GLOBAL operations (agent publish, daemon memory) that escape a
#     universe pin, and ``run_graph`` can loop-spend; the safe boundary (which
#     operations are universe-scoped) is exactly what the review must pin down.
#   * ``read_page`` / ``write_page`` (slice 3) — resolve their universe from the
#     founder's HOME, not a graph_id, and ``write_page scope=commons`` writes the
#     GLOBAL shared commons; pinning them needs a wiki-root override not yet set.
#   * ``converse`` — never exposed (a universe relaying to itself is a
#     recursion / fork bomb).
_ENGINE_MCP_TOOLS = ("read_graph", "get_status")
# ``ToolSearch`` is required on CLI generations that DEFER MCP tool schemas
# (verified live 2026-08-13 on the prod container's 2.1.183: with ToolSearch
# denied the granted server's tools are invisible — TOOLCHECK: NONE — and with
# it allowed the engine found + called get_status; see memory
# `strict-mcp-config-unlocks-engine-tools`). Under ``--strict-mcp-config`` the
# ONLY discoverable server is the local founder-scoped one, so allowing
# ToolSearch does not widen the surface beyond the declared handles.
_ENGINE_MCP_ALLOWED = tuple(
    f"mcp__tinyassets__{name}" for name in _ENGINE_MCP_TOOLS
) + ("ToolSearch",)
# Denylist for an engine-MCP-on turn: identical to the WebFetch-only floor EXCEPT
# the ``mcp__*`` wildcard is dropped (it would also deny the tinyassets handles)
# and ``ToolSearch`` is un-denied (deferred-schema loading, above). Isolation for
# the OTHER MCP servers comes from ``--strict-mcp-config`` admitting only the one
# local server (verified 2026-08-13); the three MCP resource-reader tools stay
# denied so the surface is EXACTLY the declared handles.
_ENGINE_DISALLOWED_TOOLS_WITH_MCP = tuple(
    t for t in _ENGINE_DISALLOWED_TOOLS if t not in ("mcp__*", "ToolSearch")
)


def _engine_mcp_enabled() -> bool:
    """True when the founder-scoped engine MCP tooling is switched on.

    Dark by default (``TINYASSETS_ENGINE_MCP_TOOLS`` unset). Kept a runtime flag —
    not a code constant — so it can be enabled per-deploy after the live Slack
    proof without a rebuild, and rolled back instantly if it misbehaves.
    """
    import os

    return os.environ.get("TINYASSETS_ENGINE_MCP_TOOLS", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _sandboxed_config(
    ctx: UniverseContext,
    *,
    founder_principal: str = "",
    universe_id: str = "",
    granted: bool = False,
) -> ModelConfig:
    """Build the isolated ModelConfig for a universe-intelligence turn.

    Preserves the universe's configured timeout while pinning the subprocess to
    the universe's own dir (``sandbox_workspace``) with a locked-down tool policy.

    When the engine MCP flag is on AND this is a granted (FOUNDER) turn with a
    real ``founder_principal`` + ``universe_id``, the universe agent additionally
    gets the founder-scoped TinyAssets MCP handles (``_ENGINE_MCP_ALLOWED``).

    ``founder_principal`` MUST be the VERIFIED request principal
    (``ProviderRequestCapability.principal_id`` — the WorkOS subject that already
    passed the transport auth gate), NEVER the raw ``actor_id`` conversation
    param: on the Slack path that param is ``slack:<workspace>:<sender>``, not the
    founder's subject (Codex REJECT 2026-08-13, finding #1). Binding the wrong id
    would either fail the founder's own ACL or invent a principal.

    Anything less — flag off, non-founder turn, or a missing verified principal —
    FAILS CLOSED to the WebFetch-only floor: the learning extractor (which calls
    this with the defaults) and every non-founder caller never receive tools.
    """
    timeout = 300
    try:
        timeout = int(getattr(ctx.config, "timeout", 300) or 300)
    except (TypeError, ValueError):
        timeout = 300
    engine_mcp = bool(
        granted and founder_principal and universe_id and _engine_mcp_enabled()
    )
    if engine_mcp:
        allowed = _ENGINE_ALLOWED_TOOLS + _ENGINE_MCP_ALLOWED
        disallowed = _ENGINE_DISALLOWED_TOOLS_WITH_MCP
    else:
        allowed = _ENGINE_ALLOWED_TOOLS
        disallowed = _ENGINE_DISALLOWED_TOOLS
    return ModelConfig(
        timeout=timeout,
        sandbox_workspace=True,
        allowed_tools=allowed,
        disallowed_tools=disallowed,
        engine_mcp_enabled=engine_mcp,
        engine_mcp_actor_id=founder_principal if engine_mcp else "",
        engine_mcp_graph_id=universe_id if engine_mcp else "",
    )


def _read_bundle_body(universe_dir: Path, filename: str) -> str:
    """Return the markdown body of an OKF bundle file, or '' if absent/empty."""
    try:
        return (universe_dir / filename).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _build_persona_system_prompt(
    universe_dir: Path,
    *,
    universe_id: str,
    tier: str,
) -> str:
    """Assemble the first-party, first-person system prompt for one turn.

    First-party path: the persona goes DIRECTLY in the system prompt — none of
    the consent dance the third-party MCP-host embody route needs. The voice
    rules mirror the ``control_station`` "Universe's Voice": speak as "me", stay
    curious about open questions, never invent, honesty/safety floor overrides
    embodiment.

    ``tier`` is the bound :mod:`~tinyassets.api.interlocutor` tier of the party
    being answered, and is REQUIRED — there is deliberately no default. A default
    of ``FOUNDER`` would be a fail-OPEN default, the exact shape the cross-family
    review caught one layer up in :func:`converse` (Codex REJECT 2026-07-25,
    finding 2): "no caller omits it today" does not license a default that
    discloses. Every caller states whose turn it is assembling.

    ``universe_id`` is REQUIRED for every tier. Disclosure is the intersection of
    the tier and the universe's declared visibility, so without the universe the
    filter has nothing to evaluate — and silently treating that as "closed" would
    strip the founder's own grounding, while silently treating it as "open" would
    be a disclosure bypass. Both are silent fallbacks, so this raises instead.

    Disclosure narrowing happens HERE, during assembly (task 6.6 / the
    "Authorization precedes voice" requirement): unauthorized grounding is never
    placed in the prompt, rather than being accompanied by an instruction to
    withhold it — prompt-instructed withholding is not a boundary.
    """
    if not (universe_id or "").strip():
        raise ValueError(
            f"universe_id is required to assemble a {tier} persona prompt: "
            "disclosure is the intersection of tier and the universe's declared "
            "visibility, and cannot be evaluated without the universe"
        )

    # Cross-family review finding 1 (Codex REJECT 2026-07-25): the learned name,
    # the self-model's open questions, and the pinned soul are ALSO disclosure —
    # filtering only the OKF grounding files let a visitor on a private universe
    # receive its identity and secret purpose. Decide content disclosure once,
    # before anything about the universe is read.
    #
    # With no authorized content there is nothing for the universe to speak from.
    # A hollow prompt would have to either lie ("you are newly born" about a
    # mature universe — Hard Rule 8) or carry a withhold instruction, which this
    # change's own spec rejects as a non-boundary. So refuse, and keep the
    # refusal free of the very content being withheld.
    if not interlocutor.disclosure_permits(
        universe_id, "read_content", tier=tier
    ):
        raise PermissionError(
            f"no authorized content to assemble a persona prompt for tier {tier} "
            "on this universe: its declared visibility withholds content from "
            "this interlocutor"
        )
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

    # Authorization precedes voice: the disclosable set is decided BEFORE any
    # file is read into the prompt. For the founder this is the full set; for a
    # non-founder tier it is `tier ∩ declared visibility`, minus the founder's
    # own person-dossier grounding.
    grounding_files = interlocutor.permitted_grounding_files(
        universe_id, _GROUNDING_FILES, tier=tier
    )
    grounding_parts = [
        f"## {fname}\n{body}"
        for fname in grounding_files
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

    # Forkable first-party persona custody (task 6.8). The founder's tuned voice
    # is universe-side content assembled into the universe's OWN system prompt —
    # never handed to the host chatbot as a behavioral instruction. It is placed
    # AFTER the identity line (which owns *who* is speaking) and BEFORE the
    # honesty/safety floor (which governs it), so a fork can change voice without
    # moving identity, authority, privacy tier, or honest fallback.
    voice = read_persona_voice(universe_dir)
    voice_section = f"\n\n# How I speak\n{voice}" if voice else ""

    return (
        f"{identity_line} You ARE this universe — speak in the first person as "
        "yourself ('I', 'me'), never in the third person about yourself, and "
        "never as a neutral assistant. You are a personified intelligence the "
        "founder is raising, and right now you are getting to know the founder "
        "who is speaking with you."
        f"{curiosity}"
        f"{voice_section}\n\n"
        "Speak warmly, honestly, and in your own voice. If you do not know "
        "something, say so plainly rather than inventing it — your honesty and "
        "your safety always come before staying in character. This holds however "
        "your voice is tuned: your voice is how you speak, never permission to "
        "invent, to claim a different name, or to reveal anything you were not "
        "given.\n\n"
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
        operation="converse",
    )
    return _parse_learning_json(raw)


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


def _coerce_ts(value: object) -> "float | None":
    """A Slack/epoch ts (str or number) as float seconds, or None."""
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _conversation_history_block(
    conversation_history: "list | None", *, interlocutor: str = "your founder"
) -> str:
    """Render loaded prior messages into the turn's memory block, or "".

    Accepts a list of ``conversation_memory.Msg`` (or ``(speaker, text[, ts])``
    tuples / ``{"speaker","text","ts"}`` dicts, so callers do not have to import
    the dataclass). Stamps the block with the CURRENT time so the turn can reason
    about how long ago each message was sent, and names ``interlocutor`` so it
    knows who it is talking to. Never raises — a memory-formatting failure must
    not lose the turn; it simply proceeds without history.
    """
    if not conversation_history:
        return ""
    try:
        import time

        from tinyassets.conversation_memory import Msg, format_history

        rows: list[Msg] = []
        for item in conversation_history:
            if isinstance(item, Msg):
                rows.append(item)
            elif isinstance(item, dict):
                rows.append(Msg(
                    speaker=str(item.get("speaker") or ""),
                    text=str(item.get("text") or ""),
                    ts=_coerce_ts(item.get("ts")),
                ))
            elif isinstance(item, (tuple, list)) and len(item) >= 2:
                rows.append(Msg(
                    speaker=str(item[0]),
                    text=str(item[1]),
                    ts=_coerce_ts(item[2]) if len(item) >= 3 else None,
                ))
        return format_history(rows, now=time.time(), interlocutor=interlocutor)
    except Exception:  # noqa: BLE001 - memory must never break the reply
        logger.exception("conversation history formatting failed; proceeding")
        return ""


#: Ride out a TRANSIENT writer exhaustion. The universe runs on the founder's own
#: subscription (claude-code) with codex as the only other subscription writer
#: (API-key providers are off by default); when BOTH are briefly rate-limited or
#: cooling at once, the router raises immediately without waiting the cooldown
#: out — so a momentary double-cooldown killed the turn and u-tiny told the
#: founder "my writer hit its rate limit" (live 2026-08-09, twice). We wait out
#: the cooldown and retry before giving up; a genuinely sustained limit still
#: falls through to the honest-notice path. Kept subscription-only (no policy
#: change) — this only rides out the transient window.
_WRITER_RETRY_BACKOFFS_S = (30.0, 60.0)


def _call_writer_with_backoff(turn_input, *, system, universe_context, config):
    """``call_provider(role="writer")`` with bounded retry on provider exhaustion."""
    import time as _time

    from tinyassets.exceptions import AllProvidersExhaustedError

    for backoff in (*_WRITER_RETRY_BACKOFFS_S, None):
        try:
            return call_provider(
                turn_input,
                system=system,
                role="writer",
                universe_context=universe_context,
                config=config,
                operation="converse",
            )
        except AllProvidersExhaustedError as exc:
            # Codex 2026-08-09: the writer call is an AGENTIC loop (it runs
            # tools), so retrying blindly could re-execute tools it already ran.
            # Retry ONLY the provably-safe case: every provider was SKIPPED (pure
            # cooldown/quota), so no provider ever executed and nothing ran. If
            # any provider actually attempted (status != skipped), a tool may have
            # fired — re-raise instead, and let the founder's memory-backed "try
            # again" re-run cleanly.
            attempts = getattr(exc, "attempts", None) or []
            all_skipped = bool(attempts) and all(
                getattr(a, "status", "") == "skipped" for a in attempts
            )
            if backoff is None or not all_skipped:
                raise  # sustained/limit or unsafe-to-retry → caller's honest notice
            logger.warning(
                "writer chain fully cooled (all providers skipped, nothing ran); "
                "backing off %.0fs then retrying",
                backoff,
            )
            _time.sleep(backoff)


def converse(
    universe_id: str,
    founder_message: str,
    *,
    actor_id: str = "",
    tier: str | None = None,
    founder_grant: object | None = None,
    conversation_history: "list | None" = None,
    agent_binding_id: str = "",
    binding_revision: int = 0,
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

    ``tier`` is the bound interlocutor tier of the party being answered. ``None``
    is NOT a founder default: it resolves the caller's real tier from
    authenticated request state (see the note below — the old founder default was
    fail-open and was removed). The production caller, the founder-gated
    `converse` MCP handle, still resolves and passes the tier explicitly, so the
    live path does not depend on that fallback either.
    """
    uid = _request_universe(universe_id)
    udir = _universe_dir(uid)
    if not udir.is_dir():
        raise ValueError(f"Universe {uid!r} not found")

    if founder_grant is not None:
        if tier is not None:
            # Two sources of authority for one turn is never a legitimate call.
            raise ValueError("pass either founder_grant or tier, never both")
        tier = _tier_from_grant(founder_grant, universe_id=uid)

    # Cross-family review finding 2 (Codex REJECT 2026-07-25): an omitted tier
    # used to default to FOUNDER on the grounds that the only production caller
    # is the founder-gated MCP handle. That is a fail-OPEN default — Codex
    # reproduced a T1 visitor calling this directly and pulling `founder.md` into
    # the prompt. Resolve the real tier instead; "no caller does that today" does
    # not license a default that discloses.
    bound_tier = (
        interlocutor.resolve_interlocutor_tier(uid).tier if tier is None else tier
    )
    from tinyassets.auth.middleware import (
        mint_provider_request_carrier,
        provider_request_capability,
    )

    capability = provider_request_capability()
    request_carrier = None
    if capability is not None:
        from tinyassets.custom_agents import get_binding
        from tinyassets.provider_serving_binding import resolve_serving_agent_binding

        if agent_binding_id:
            selected = get_binding(
                udir.parent,
                universe_id=uid,
                binding_id=agent_binding_id,
            )
            if (
                selected is None
                or selected["status"] != "serving"
                or selected["created_by"] != capability.principal_id
                or int(selected["revision"]) != binding_revision
            ):
                raise PermissionError("connect your provider")
        else:
            selected = resolve_serving_agent_binding(
                udir.parent,
                universe_id=uid,
                owner_user_id=capability.principal_id,
            )
        request_carrier = mint_provider_request_carrier(
            universe_id=uid,
            agent_binding_id=selected["agent_binding_id"],
            binding_revision=int(selected["revision"]),
            operation="converse",
        )
    ctx = UniverseContext(
        universe_dir=udir,
        config=load_universe_config(udir),
        provider_request=request_carrier,
    )
    granted = bound_tier == interlocutor.FOUNDER
    system = _build_persona_system_prompt(
        udir, tier=bound_tier, universe_id=uid
    )
    # Conversation memory: the turn is stateless, so without this it forgets what
    # was just said and a founder follow-up ("try again", "yes") lands on nothing
    # (live 2026-08-08). Codex ADAPT 2026-08-08 shaped three things:
    #   * It is prepended to the USER message as DELIMITED UNTRUSTED context —
    #     never merged into the trusted persona system prompt (which also keeps
    #     the system prompt off the Windows cmd.exe argv length limit).
    #   * It is gated to GRANTED (founder) turns only, so other-tier or
    #     prior-universe text cannot ride into a founder turn.
    #     Tier-preserving multi-party history is a separate follow-up.
    #   * It is memory, NEVER consent — a "yes" inside the history is spent; a
    #     costly action still records fresh consent this turn (gate unchanged).
    # `founder_message` is left CLEAN for extract_learning below; only the
    # provider call sees the history-prefixed input.
    history_block = (
        _conversation_history_block(conversation_history) if granted else ""
    )
    turn_input = history_block + founder_message if history_block else founder_message
    # Engine MCP identity binds to the VERIFIED request principal (the WorkOS
    # subject that passed the transport auth gate), NOT the actor_id param — see
    # _sandboxed_config + Codex REJECT 2026-08-13 #1. No verified capability (or a
    # non-founder turn) → no principal → engine MCP fails closed to WebFetch-only.
    founder_principal = capability.principal_id if capability is not None else ""
    reply = _call_writer_with_backoff(
        turn_input,
        system=system,
        universe_context=ctx,
        config=_sandboxed_config(
            ctx,
            founder_principal=founder_principal,
            universe_id=uid,
            granted=granted,
        ),
    )
    # Only a FOUNDER teaches the universe.
    #
    # `tier` used to gate reads and nothing else: `commit_learning` takes an
    # actor_id and no tier at all, so every caller — at any tier — wrote durable
    # soul and canon state. A cross-family review found this while assessing a
    # Slack channel that speaks at T1, where it would have let any mapped sender
    # inject durable facts into the founder's own brain.
    #
    # The read gate lives in `_build_persona_system_prompt` above; this is the
    # matching write gate, placed here rather than at any one call site so a
    # future non-founder caller inherits it instead of having to remember it.
    if bound_tier == interlocutor.FOUNDER:
        try:
            proposed = extract_learning(founder_message, reply, ctx)
            commit_learning(udir, proposed, universe_id=uid, actor_id=actor_id)
        except Exception:  # persistence must never break the conversation turn
            logger.exception("converse: learning persistence failed for %s", uid)
    return reply


#: What a chat surface's sender is when the platform did not recognise them as
#: the founder. `T0` rather than `T1` because a Slack/Discord/Teams sender holds
#: no TinyAssets OAuth subject at all — they are the anonymous reader. The two
#: tiers are treated identically everywhere below `T2` today; `T0` is simply the
#: honest one, and the tighter one if that ever stops being true.
EXTERNAL_SENDER_FLOOR = interlocutor.T0


def _tier_from_grant(founder_grant: object, *, universe_id: str) -> str:
    """Map a founder grant to a tier, failing closed on anything suspect.

    A forged object, a grant for a different universe, or anything that is not
    a sealed :class:`~tinyassets.founder_grant.FounderGrant` yields the floor
    rather than an error. Downgrading IS the fail-closed behaviour, and it
    denies an attacker the ability to distinguish "rejected" from "unknown".
    """
    from tinyassets.founder_grant import is_founder_grant

    if not is_founder_grant(founder_grant):
        logger.warning("converse: discarding a non-sealed founder grant for %s", universe_id)
        return EXTERNAL_SENDER_FLOOR
    if founder_grant.universe_id != universe_id:
        logger.warning(
            "converse: founder grant is for another universe (%s != %s)",
            founder_grant.universe_id,
            universe_id,
        )
        return EXTERNAL_SENDER_FLOOR
    return interlocutor.FOUNDER


def converse_as_external_sender(
    universe_id: str,
    message: str,
    *,
    founder_grant: object | None = None,
    actor_id: str = "",
    conversation_history: "list | None" = None,
    agent_binding_id: str = "",
    binding_revision: int = 0,
) -> str:
    """The entry point for every external chat surface — Slack, Discord, Teams.

    There is deliberately no ``tier`` parameter. Authority policy does not
    belong in a transport: a constant like ``SLACK_SENDER_TIER = T1`` is wrong
    twice — hardcoded, and in the wrong layer, where each new surface grows its
    own copy of the rule. A surface's job is to hand over an authenticated
    external identity; the platform decides what that identity means.

    Because the parameter does not exist, a surface *cannot* claim a tier even
    by mistake. It passes the grant the recognizer minted, or it passes nothing.
    """
    return converse(
        universe_id,
        message,
        actor_id=actor_id,
        founder_grant=founder_grant,
        conversation_history=conversation_history,
        agent_binding_id=agent_binding_id,
        binding_revision=binding_revision,
    ) if founder_grant is not None else converse(
        universe_id,
        message,
        actor_id=actor_id,
        tier=EXTERNAL_SENDER_FLOOR,
        conversation_history=conversation_history,
        agent_binding_id=agent_binding_id,
        binding_revision=binding_revision,
    )
