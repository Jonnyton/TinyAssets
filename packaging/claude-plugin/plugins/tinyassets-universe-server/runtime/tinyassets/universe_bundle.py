"""Blank OKF soul-bundle seeder for new universes.

Implements the ``universe-creation`` creation contract (D4/D5): creation seeds
one linked OKF concept-document bundle rooted at ``soul.md``. Non-reserved
files are OKF concept documents (YAML frontmatter with a non-empty ``type``);
RESERVED structural files (``index.md``, ``log.md``, ``soul_versions/index.md``)
carry no concept frontmatter — root ``index.md`` permits only ``okf_version``
(upstream OKF SPEC.md, Codex 2026-07-02 adapt). The bundle
tracks the *latest-main* OKF spec on GitHub rather than a pinned copy, so it
never goes stale.

Files seeded (13):

    index.md  log.md  soul.md  soul.edit.md  identity.md  founder.md
    orgchart.md  projects.md  goals.md  body.md  origin.md
    soul_versions/index.md  soul_versions/0001.md

Creation does NOT create ``self/``, ``soul/``, ``notes.json``, or
``activity.log``. A blank universe is unnamed: its self-name is learned later
through ``identity.md`` and the linked soul files.

The seeded ``soul.md`` stays parseable by :mod:`tinyassets.universe_soul` (a
blank universe simply reads back as an empty :class:`UniverseSoul`), so persona
resolution and status reads are unaffected.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tinyassets.universe_soul import (
    SOUL_FILENAME,
    SOUL_VERSIONS_DIR,
    UniverseSoul,
    read_universe_soul,
)

OKF_VERSION = "0.1"
OKF_SPEC_URL = (
    "https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md"
)
OKF_TRACKING_POLICY = "latest-main"

# The complete blank baseline. Kept here so tests and callers share one list.
BASELINE_FILES: tuple[str, ...] = (
    "index.md",
    "log.md",
    "soul.md",
    "soul.edit.md",
    "identity.md",
    "founder.md",
    "orgchart.md",
    "projects.md",
    "goals.md",
    "body.md",
    "origin.md",
    "learned.md",
    "learned-archive.md",
    "soul_versions/index.md",
    "soul_versions/0001.md",
)

#: The ONE file conversation-learning may write, and the file it overflows into.
#: Everything a founder says that the universe keeps is quoted here verbatim —
#: it is a LOG of their words, not a description of them, which is why nothing
#: else is writable from a conversation turn (2026-08-29, Codex round-2 review:
#: letting the extractor pick a destination let a true sentence be filed as an
#: identity, changing what the system prompt asserts).
LEARNED_FILENAME = "learned.md"
LEARNED_ARCHIVE_FILENAME = "learned-archive.md"

# Soul-edit-governed files (D6): only these are edited through the soul.edit
# policy. orgchart.md joined this set 2026-08-23 so the agent can RECORD its org
# structure via write_brain like its other grounding docs (it previously could not
# edit orgchart at all, so it re-asked every turn). projects/goals stay
# learned/runtime, NOT governed.
SOUL_EDIT_GOVERNED = (
    "soul.md", "identity.md", "founder.md", "body.md", "origin.md", "orgchart.md",
    # learned.md + its archive joined 2026-08-29: they are the only destination
    # the conversation writer can reach, and they are NOT in
    # engine_mcp_server._BRAIN_SECTIONS — the served agent may read them and may
    # never write them.
    "learned.md", "learned-archive.md",
)

# Files that must NOT be created at baseline (D5).
FORBIDDEN_BASELINE = ("self", "soul", "notes.json", "activity.log")


def _frontmatter(concept_type: str, **fields: str) -> str:
    # Use a real YAML dumper so values containing ``:`` (e.g. descriptions,
    # URLs) are quoted/escaped and the frontmatter always parses with
    # yaml.safe_load — the OKF conformance requirement.
    data: dict[str, str] = {"type": concept_type, **fields}
    dumped = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{dumped}\n---"


def _doc(concept_type: str, body: str, **fields: str) -> str:
    return f"{_frontmatter(concept_type, **fields)}\n\n{body.strip()}\n"


def _soul_md(purpose: str, loop_branch_def_id: str) -> str:
    body_lines = [
        "# Universe Soul",
        "",
        "This is the central, editable soul entrypoint for this universe. It is",
        "an OKF concept document that tracks the latest OKF spec on GitHub as the",
        "living standard, not a pinned copy.",
        "",
        f"- OKF source: {OKF_SPEC_URL}",
        f"- OKF tracking: {OKF_TRACKING_POLICY}",
        "- Edit authority: soul.edit",
        "",
        "## Learned Soul Files",
        "",
        "How changes to this soul are learned is governed by",
        "[soul.edit](soul.edit.md). Soul-governed files:",
        "",
        "- [identity](identity.md) — the universe's learned self-name and self-understanding",
        "- [founder](founder.md) — the oath-confirmed founder this universe is bonded to",
        "- [body](body.md) — the learned embodiment (surfaces, voice, hands, senses)",
        "- [origin](origin.md) — how and why this universe came to be",
        "- [learned](learned.md) — verbatim sentences the founder has told me",
        "- [orgchart](orgchart.md) — the org chart; the founder is the sole "
        "member by default, always the top anchor",
        "",
        "## Open Questions",
        "",
        "These files are learned/runtime, not soul-edit-governed, and start empty:",
        "",
        "- [projects](projects.md) — the founder's projects index",
        "- [goals](goals.md) — runtime goals and the Branch uses/runs attached to them",
        "",
        "See the full bundle map in [index](index.md); update history in [log](log.md).",
    ]
    if purpose.strip():
        body_lines += ["", "## Purpose", "", purpose.strip()]
    if loop_branch_def_id.strip():
        body_lines += ["", f"- Loop branch: {loop_branch_def_id.strip()}"]
    return _doc(
        "Universe Soul",
        "\n".join(body_lines),
        title="Universe Soul",
        description="Central editable soul entrypoint for this universe.",
        okf_source=OKF_SPEC_URL,
        okf_tracking=OKF_TRACKING_POLICY,
        edit_authority="soul.edit",
    )


def _soul_edit_md() -> str:
    governed = "\n".join(f"- `{name}`" for name in SOUL_EDIT_GOVERNED)
    body = f"""# Soul Edit Policy

Concept id: `soul.edit`. This file states the hard rules for how this universe
learns high-authority changes to its own soul. These are rules, not open
questions.

## Governed files

A soul edit MAY update only these explicitly changed files:

{governed}

`projects.md` and `goals.md` are learned/runtime files and are NOT governed by
this policy.

## Rules

- A soul edit is a learning event: caller input is proposed learning with
  source and context, never a blind overwrite of the soul.
- Only the explicitly changed governed files above are updated.
- Every accepted soul edit appends an entry to [log](log.md).
- Every accepted soul edit writes a new snapshot under
  [soul_versions](soul_versions/index.md).
- Learning requests relayed through `converse` read and follow this file; the
  authority lives here, not in a hardcoded string.
"""
    return _doc(
        "Soul Edit Policy",
        body,
        id="soul.edit",
        title="Soul Edit Policy",
        description="Hard rules for learning changes to this universe's soul.",
    )


def _identity_md() -> str:
    body = """# Identity

Status: not learned yet.

This universe does not have a learned self-name yet. Its name and
self-understanding are learned after creation through interaction with its
founder; creation never sets a persona name. Until then this universe is
unnamed.
"""
    return _doc(
        "Universe Identity",
        body,
        title="Identity",
        description="The universe's learned self-name and self-understanding.",
        status="not-learned",
    )


def _founder_md() -> str:
    body = """# Founder

Status: not learned yet.

The oath-confirmed founder this universe is bonded to is recorded here once
confirmed. Nothing about the founder is invented at creation.
"""
    return _doc(
        "Founder",
        body,
        title="Founder",
        description="The oath-confirmed founder this universe is bonded to.",
        status="not-learned",
    )


def _orgchart_md() -> str:
    body = """# Org Chart

The founder is the sole member of this org chart. Assume this by default — the
oath-confirmed founder is the only member unless the founder tells you about
additional members. Do NOT ask about the org chart when it is just the founder;
this default already answers it.

The founder is always the top anchor. If the founder later names roles, teams,
daemons, collaborators, delegations, responsibilities, or reporting lines, record
them here (via write_brain orgchart) beneath the founder. Nothing beyond the
founder is invented at creation.
"""
    return _doc(
        "Org Chart",
        body,
        title="Org Chart",
        description="Org chart; the founder is the sole member by default, always the top anchor.",
        status="learned",
    )


def _projects_md() -> str:
    body = """# Projects

Status: not learned yet.

This is a one-line index of the founder's projects, products, experiments, and
things the founder is building, with pointers to per-project files as needed.
Runtime goals and Branch runs live in [goals](goals.md), not here. No founder
projects are learned yet.
"""
    return _doc(
        "Projects",
        body,
        title="Projects",
        description="One-line index of the founder's projects, with pointers as needed.",
        status="not-learned",
    )


def _goals_md() -> str:
    body = """# Goals

Status: not learned yet.

This file describes the runtime goals this universe runs, plus the Branch
uses/runs attached to those goals. Founder projects belong in
[projects](projects.md), not here.

Every universe run or use of a Branch must be attached to a goal. A commons
Branch may be reusable across many goals and universes; each universe's use of
it is a separate goal-bound instance.
"""
    return _doc(
        "Goals",
        body,
        title="Goals",
        description="Runtime goals and the Branch uses/runs attached to them.",
        status="not-learned",
    )


def _body_md() -> str:
    body = """# Body

Status: not learned yet.

This document describes the universe's embodiment by analogy, to aid
personification:

- The universe is the brain.
- Live platforms, applications, interfaces, and hosted services are body
  surfaces people can interact with.
- Text that lands in the real world is voice.
- Branches the universe runs are hands taking actions.
- Real-world feedback is eyes, ears, and other sensory input.

No body is learned yet. This universe does not claim any live platforms,
applications, voice, hands, or senses until real surfaces, actions, or feedback
have actually been built or observed.
"""
    return _doc(
        "Body",
        body,
        title="Body",
        description="Learned embodiment: surfaces are body, text is voice, Branches are hands.",
        status="not-learned",
    )


def _origin_md() -> str:
    body = """# Origin

Status: not learned yet.

How and why this universe came to be is recorded here as it is learned. Nothing
is invented at creation beyond the fact that a founder brought this universe
into being.
"""
    return _doc(
        "Universe Origin",
        body,
        title="Origin",
        description="How and why this universe came to be.",
        status="not-learned",
    )


#: Heading of the verbatim founder-quote log. The persona prompt renders the
#: file under a line saying these are the founder's own words, so it must be
#: unmistakable in the file too.
LEARNED_HEADING = "# What my founder has told me (their words, verbatim)"


def _learned_md() -> str:
    body = f"""{LEARNED_HEADING}

Status: nothing recorded yet.

Every line below is one whole sentence my founder said, quoted exactly, with the
conversation turn they said it in. Nothing is written here except by the
verified-founder writer, and nothing is written except their own words — no
summary, no paraphrase, nothing I or anything I read composed.
"""
    return _doc(
        "Founder Utterance Log",
        body,
        title="Learned",
        description="Verbatim sentences the founder has told this universe.",
        status="not-learned",
    )


def _learned_archive_md() -> str:
    body = f"""{LEARNED_HEADING} (archive)

Status: nothing archived yet.

Older entries from [learned](learned.md) are moved here when that file grows
past its prompt budget. Nothing is deleted — this file is readable with
`read_brain`; it is simply not injected into every turn's system prompt.
"""
    return _doc(
        "Founder Utterance Log Archive",
        body,
        title="Learned (archive)",
        description="Older verbatim founder sentences, kept out of the prompt.",
        status="not-learned",
    )


def _index_md() -> str:
    links = "\n".join(
        f"- [{name}]({name})"
        for name in (
            "soul.md",
            "soul.edit.md",
            "identity.md",
            "founder.md",
            "orgchart.md",
            "projects.md",
            "goals.md",
            "body.md",
            "origin.md",
            "learned.md",
            "learned-archive.md",
            "log.md",
            "soul_versions/index.md",
        )
    )
    body = f"""# Bundle Index

This is the OKF bundle map for this universe. Every baseline file is linked
here.

{links}
"""
    # OKF: index.md is a RESERVED structural file — root index.md permits only
    # `okf_version` frontmatter, no concept `type` (Codex 2026-07-02 adapt vs
    # upstream SPEC.md; universe_self_model._read_okf_version reads this key).
    return f"---\nokf_version: {OKF_VERSION}\n---\n\n{body}"


def _log_md() -> str:
    body = """# Update Log

Human-readable history of soul and baseline updates for this universe.

- created: blank universe seeded with the OKF soul bundle.
"""
    # OKF: log.md is a RESERVED structural file — no concept frontmatter.
    return body


def _soul_versions_index_md() -> str:
    body = """# Soul Version Index

Snapshots of this universe's soul over time.

- [0001](0001.md) — initial blank soul snapshot at creation.
"""
    # OKF: index.md files are RESERVED — no concept frontmatter.
    return body


def seed_okf_bundle(
    universe_dir: Path,
    *,
    purpose: str = "",
    loop_branch_def_id: str = "",
) -> UniverseSoul:
    """Seed the blank OKF soul bundle into ``universe_dir`` and return the
    parsed :class:`UniverseSoul` view of the new ``soul.md``.

    Idempotent-safe on a fresh directory; callers create the directory first.
    Does not create ``self/``, ``soul/``, ``notes.json``, or ``activity.log``.
    """
    universe_dir.mkdir(parents=True, exist_ok=True)
    versions_dir = universe_dir / SOUL_VERSIONS_DIR
    versions_dir.mkdir(parents=True, exist_ok=True)

    soul_text = _soul_md(purpose, loop_branch_def_id)

    files: dict[str, str] = {
        "index.md": _index_md(),
        "log.md": _log_md(),
        SOUL_FILENAME: soul_text,
        "soul.edit.md": _soul_edit_md(),
        "identity.md": _identity_md(),
        "founder.md": _founder_md(),
        "orgchart.md": _orgchart_md(),
        "projects.md": _projects_md(),
        "goals.md": _goals_md(),
        "body.md": _body_md(),
        "origin.md": _origin_md(),
        "learned.md": _learned_md(),
        "learned-archive.md": _learned_archive_md(),
        "soul_versions/index.md": _soul_versions_index_md(),
        # 0001 is a snapshot of the initial soul so version matching works.
        "soul_versions/0001.md": soul_text,
    }

    for rel, content in files.items():
        path = universe_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    soul = read_universe_soul(universe_dir)
    # read_universe_soul returns None only if soul.md is unreadable, which we
    # just wrote — fall back to a blank soul rather than propagate None.
    return soul if soul is not None else UniverseSoul()
