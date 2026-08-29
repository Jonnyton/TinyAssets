"""The universe's learn/write path: apply a governed soul edit.

Implements the `soul.edit` contract from the universe-creation spec: the
execution path READS AND FOLLOWS the universe's own ``soul.edit.md`` policy
(the authority lives in the file, not in a hardcoded list). An edit is a
learning event — proposed learning with source and context, never a blind
overwrite — that updates only the explicitly changed governed files, appends
``log.md``, and writes a new ``soul_versions/`` snapshot.

This is what lets a universe REMEMBER what its founder teaches it: learned
files flip ``status: not-learned`` → ``learned``, and the persona
(``tinyassets.persona.resolve_persona`` over
``tinyassets.universe_self_model.read_self_model``) voices them from then on.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import stat
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import InitVar, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from tinyassets.universe_soul import SOUL_FILENAME, SOUL_VERSIONS_DIR

SOUL_EDIT_POLICY_FILENAME = "soul.edit.md"

# Sidecar lock serializing soul edits for ONE universe. A soul edit is a
# read→modify→write→snapshot-allocate sequence; the snapshot number is derived
# from a directory listing, so concurrent edits without a lock can collide on
# the number and lose an update (Codex ADAPT 2026-07-02). One writer at a time
# per universe closes that window.
SOUL_LOCK_FILENAME = ".soul.lock"

# Files whose frontmatter records the learning event. soul.md is the
# operational entrypoint — its frontmatter (okf_source, edit_authority, …) is
# preserved verbatim and carries no learned-status flag.
_LEARNED_STATUS_EXEMPT = frozenset({SOUL_FILENAME})


class SoulEditError(ValueError):
    """A soul edit that violates the universe's soul.edit.md policy."""


# ── who is claiming this edit (2026-08-29, Codex round-2 review) ────────────
# `apply_soul_edit` used to take `source` as a free string, so it was a third
# sink for founder provenance: any caller could write
# `source="founder utterance turn_X"` and produce a section that reads as
# conversation-verified. A provenance CLAIM is authority, and authority is never
# a caller-supplied parameter (AGENTS.md / PLAN cross-cutting). So the source is
# now derived from a small typed object, and the only object that can claim a
# founder utterance is minted by the one writer that verified one.

#: Held by :func:`mint_founder_utterance_provenance` alone. Importing it is
#: possible — Python has no real privacy — which is why
#: ``test_founder_provenance_has_exactly_one_minting_call_site`` greps the tree:
#: the invariant is "one call site", enforced by a test, not by the language.
_FOUNDER_PROVENANCE_KEY = object()


@dataclass(frozen=True)
class FounderUtteranceProvenance:
    """This edit is grounded in a verified sentence of a founder's own message.

    Only ``universe_intelligence.commit_founder_learning`` may mint one, because
    it is the only code that checks a candidate against the founder's message.
    Constructing it directly raises.
    """

    turn_id: str
    digest: str
    key: InitVar[object] = None

    def __post_init__(self, key: object) -> None:
        if key is not _FOUNDER_PROVENANCE_KEY:
            raise SoulEditError(
                "FounderUtteranceProvenance is minted by the verified-founder "
                "writer, not constructed: a source is a claim about where words "
                "came from, and only the code that checked them may make it"
            )
        if not (self.turn_id or "").strip() or not (self.digest or "").strip():
            raise SoulEditError("founder provenance needs a turn id and a digest")

    def source_label(self) -> str:
        return f"founder utterance {self.turn_id}"

    def frontmatter(self) -> dict[str, str]:
        return {
            "learned_turn_id": self.turn_id,
            "learned_utterance_digest": self.digest,
        }


@dataclass(frozen=True)
class DirectEditProvenance:
    """This edit is a founder authoring their own bundle, with no utterance.

    Built by ``universe_intelligence.commit_direct_soul_edit``, which is the
    single entry point for every non-conversation edit (including the
    ``universe action=soul.edit`` surface).
    """

    actor: str
    surface: str

    def source_label(self) -> str:
        who = (self.actor or "").strip() or "unknown actor"
        where = (self.surface or "").strip() or "direct"
        return f"founder direct edit ({who}, {where})"

    def frontmatter(self) -> dict[str, str]:
        # Deliberately empty: a direct edit carries no turn and no digest, and
        # apply_soul_edit CLEARS both, so it can never inherit the attribution
        # of the conversation edit that came before it.
        return {}


def mint_founder_utterance_provenance(
    turn_id: str, digest: str
) -> FounderUtteranceProvenance:
    """Mint founder provenance. ONE call site: ``commit_founder_learning``."""
    return FounderUtteranceProvenance(turn_id, digest, _FOUNDER_PROVENANCE_KEY)


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split an OKF concept doc into (frontmatter dict, body)."""
    if not text.startswith("---"):
        raise SoulEditError("governed file is missing OKF frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SoulEditError("governed file has malformed OKF frontmatter")
    meta = yaml.safe_load(parts[1])
    if not isinstance(meta, dict):
        raise SoulEditError("governed file frontmatter is not a mapping")
    return meta, parts[2].lstrip("\n")


def _render(meta: dict[str, Any], body: str) -> str:
    fm = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
    if not body.endswith("\n"):
        body += "\n"
    return f"---\n{fm}\n---\n\n{body}"


def assert_contained(root: Path, path: Path) -> None:
    """Refuse a path that escapes ``root`` through a symlinked component.

    ``os.path.realpath`` resolves EVERY symlink in the path (the file itself AND
    any parent directory, e.g. a ``soul_versions`` symlinked to an external dir),
    so requiring both the path and its parent to resolve inside ``root`` closes
    symlink write-escape and read-through-disclosure across the soul-edit sinks
    (Codex brain-loop re-review 2026-08-22). Hardlinks (which share no distinct
    path) are handled separately by the per-file link-count guard + atomic writes.
    """
    root_r = os.path.realpath(root)
    prefix = root_r + os.sep
    for candidate in (os.path.realpath(path), os.path.realpath(Path(path).parent)):
        if candidate != root_r and not candidate.startswith(prefix):
            raise SoulEditError(
                f"path escapes the universe via a symlinked component: {path}"
            )


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Inode-safe write: write a FRESH temp file in the same dir + os.replace.

    ``os.replace`` repoints the NAME at a new inode, so a SYMLINK or HARDLINK at
    ``path`` can never redirect the write onto another inode (e.g. soul.md's
    control-plane frontmatter or an external file). This closes the inode-alias
    bypass across EVERY soul-edit sink — the governed files, log.md, the snapshot,
    and the version index — and also the check→use TOCTOU window, since the write
    itself is safe regardless of what the path pointed at a moment earlier (Codex
    brain-loop re-review 2026-08-22).
    """
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def read_governed_files(universe_dir: Path) -> tuple[str, ...]:
    """Governed files = a platform-enforced floor PLUS the universe's own extensions.

    The universe's ``soul.edit.md`` lists files it governs; a PRESENT policy is still
    required (no policy file → no soul edits, fail-closed). The returned set is the
    UNION of that list with the platform baseline (``SOUL_EDIT_GOVERNED``): the core
    grounding files are ALWAYS governable (Codex review 2026-08-23). This is
    deliberate — per-universe OMISSION of a baseline file is NOT a supported deny
    mechanism (soul.edit.md is platform-seeded from the baseline, never a
    restrictive user override), and it lets an existing universe gain a newly
    baselined grounding file (e.g. orgchart.md) without a data migration while a core
    soul file can never be silently un-governed. A universe MAY still ADD files above
    the floor by listing them. ``soul.edit.md`` itself is deliberately NOT in the
    baseline or the brain-writable mapping, so an agent cannot edit its own policy.
    """
    policy_path = universe_dir / SOUL_EDIT_POLICY_FILENAME
    try:
        policy = policy_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SoulEditError(
            f"soul edit policy missing: {SOUL_EDIT_POLICY_FILENAME} is required "
            "(the execution path reads and follows it)"
        ) from exc

    section = re.search(
        r"^##\s+Governed files\s*$(.*?)(?=^##\s|\Z)",
        policy,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not section:
        raise SoulEditError("soul.edit.md has no 'Governed files' section")
    governed = tuple(re.findall(r"^\s*-\s*`([^`]+)`", section.group(1), flags=re.MULTILINE))
    if not governed:
        raise SoulEditError("soul.edit.md governs no files")
    # Baseline migration (2026-08-23): the platform-seeded baseline of governed
    # grounding files is ALWAYS governable, even for universes whose soul.edit.md was
    # seeded before a file joined the baseline (e.g. orgchart.md). Union the parsed
    # policy list with the current baseline so an existing universe does not need a
    # data migration to gain a new baseline grounding file, while any files the
    # universe itself added to its policy are preserved. (This is what lets the live
    # universe finally record its org chart instead of re-asking every turn.)
    from tinyassets.universe_bundle import SOUL_EDIT_GOVERNED

    merged = list(governed)
    for baseline in SOUL_EDIT_GOVERNED:
        if baseline not in merged:
            merged.append(baseline)
    return tuple(merged)


@contextlib.contextmanager
def _soul_lock(universe_dir: Path) -> Iterator[None]:
    """Cross-platform exclusive lock serializing soul edits for one universe.

    Mirrors the sidecar-lock pattern in ``branch_tasks._file_lock`` (msvcrt on
    Windows, fcntl on POSIX). Held across the whole read→write→snapshot section
    of :func:`apply_soul_edit` so the snapshot-number allocation cannot race.
    """
    universe_dir = Path(universe_dir)
    universe_dir.mkdir(parents=True, exist_ok=True)
    lock_file = universe_dir / SOUL_LOCK_FILENAME
    fd = os.open(str(lock_file), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if sys.platform == "win32":
            import msvcrt

            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if sys.platform == "win32":
                import msvcrt

                try:
                    os.lseek(fd, 0, 0)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl

                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
    finally:
        os.close(fd)


def current_soul_versions(
    universe_dir: Path, filenames: Iterable[str]
) -> dict[str, str]:
    """Snapshot the current content hash of each governed file.

    A caller reads these BEFORE composing a learning edit, then passes them as
    ``expected_versions`` to :func:`apply_soul_edit`; the write is rejected if
    the file changed in between (optimistic concurrency / compare-and-swap).
    Missing files are omitted.
    """
    universe_dir = Path(universe_dir)
    out: dict[str, str] = {}
    for filename in filenames:
        try:
            raw = (universe_dir / filename).read_text(encoding="utf-8")
        except OSError:
            continue
        out[filename] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return out


def apply_soul_edit(
    universe_dir: Path,
    *,
    changes: dict[str, str] | None = None,
    provenance: "FounderUtteranceProvenance | DirectEditProvenance | None" = None,
    context: str,
    summary: str = "",
    name: str = "",
    expected_versions: dict[str, str] | None = None,
    transform: "Callable[[dict[str, str]], dict[str, str]] | None" = None,
    transform_files: tuple[str, ...] = (),
    **_rejected: Any,
) -> "dict[str, Any] | None":
    """Apply one governed learning event to the universe's soul bundle.

    ``changes`` maps governed filename → new markdown BODY (frontmatter is
    managed here: preserved, with ``status: learned`` + ``learned_from``
    recorded). ``name`` optionally records the universe's learned self-name in
    ``identity.md`` frontmatter — a name-only learning event needs no body.
    ``source`` and ``context`` are required: an edit is proposed learning, not
    a blind overwrite. ``expected_versions`` (filename → sha256 of the content
    the caller last read, from :func:`current_soul_versions`) makes the write a
    compare-and-swap: if a governed file changed since it was read the edit is
    rejected rather than clobbering the newer state. The whole read→write→
    snapshot section runs under a per-universe lock.

    ``provenance`` is a :class:`FounderUtteranceProvenance` or
    :class:`DirectEditProvenance` — never a string (2026-08-29, Codex round-2
    review: a free-form ``source`` made this a third sink through which any
    caller could stamp "founder utterance <turn>"). Its ``source_label()``
    becomes ``learned_from`` and its ``frontmatter()`` the turn/digest keys,
    which are recorded together with it and CLEARED together with it, so an edit
    made without founder provenance can never inherit the previous edit's
    attribution.

    ``transform`` closes the read→modify→write race (same review). Passing
    ``transform_files`` + a callable does the READ inside the per-universe lock
    and hands the caller the current bodies; whatever it returns is written in
    the same locked section. A caller that reads a file itself, appends, and
    passes the result as ``changes`` loses a concurrent write in the window
    between its read and its compare-and-swap capture — an append cannot be
    expressed as a compare-and-swap without dropping one of the two appends.
    Returns None when the transform decides there is nothing to write.
    """
    if _rejected:
        raise SoulEditError(
            "apply_soul_edit does not accept "
            f"{sorted(_rejected)}: pass a provenance object minted by the "
            "writer that owns the claim (source/turn_id/utterance_digest as "
            "free strings let any caller forge founder attribution)"
        )
    if not isinstance(provenance, (FounderUtteranceProvenance, DirectEditProvenance)):
        raise SoulEditError(
            "apply_soul_edit requires a provenance object "
            "(FounderUtteranceProvenance | DirectEditProvenance), not "
            f"{type(provenance).__name__}"
        )
    universe_dir = Path(universe_dir)
    source = provenance.source_label()
    provenance_fm = provenance.frontmatter()
    context = (context or "").strip()
    name = (name or "").strip()
    if not context:
        raise SoulEditError(
            "context is required — a soul edit is a learning event, not a "
            "blind overwrite"
        )

    governed = read_governed_files(universe_dir)
    changes = dict(changes or {})
    if name and "identity.md" not in changes:
        changes["identity.md"] = ""  # name-only: keep the existing body
    transform_files = tuple(transform_files or ())
    if transform is None and transform_files:
        raise SoulEditError("transform_files given without a transform")
    if not changes and not transform_files:
        raise SoulEditError("nothing to learn: provide changes and/or a name")

    for filename in list(changes) + list(transform_files):
        if filename != Path(filename).name or filename.startswith("."):
            raise SoulEditError(f"invalid governed filename: {filename!r}")
        if filename not in governed:
            raise SoulEditError(
                f"'{filename}' is not governed by {SOUL_EDIT_POLICY_FILENAME} "
                f"(governed: {', '.join(governed)})"
            )

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    expected = dict(expected_versions or {})
    updated: list[str] = []
    new_contents: dict[str, str] = {}
    # The read→write→snapshot section runs under a per-universe lock: the
    # snapshot number is allocated from a directory listing, so a concurrent
    # edit could otherwise pick the same number and lose an update. The
    # compare-and-swap check is evaluated against the same locked read.
    with _soul_lock(universe_dir):
        # Pass 1 — read current state + compare-and-swap check. All checks run
        # before any write, so a mismatch leaves the bundle untouched.
        parsed: dict[str, tuple[dict[str, Any], str]] = {}
        udir_resolved = universe_dir.resolve()
        for filename in list(changes) + [
            f for f in transform_files if f not in changes
        ]:
            path = universe_dir / filename
            # Inode-safety (Codex brain-loop review 2026-08-22): validate the
            # resolved FILE OBJECT, not just the filename string. A governed file
            # that is a SYMLINK, or a HARDLINK aliasing another inode (e.g.
            # identity.md hardlinked to soul.md or to an external file), would let
            # a whitelisted write mutate a NON-governed target — overwriting the
            # soul's executable frontmatter (loop_branch_def_id / effect_authority)
            # or a file outside the universe. That is a control-plane bypass, so
            # refuse rather than write THROUGH the aliased path. Requires a planted
            # link (crafted/restored/compromised universe), but the boundary must
            # survive that.
            try:
                st = os.lstat(path)
            except OSError as exc:
                raise SoulEditError(
                    f"governed file missing on disk: {filename}"
                ) from exc
            if stat.S_ISLNK(st.st_mode):
                raise SoulEditError(
                    f"governed file is a symlink, refusing to write: {filename}"
                )
            if st.st_nlink > 1:
                raise SoulEditError(
                    f"governed file is hardlinked (nlink={st.st_nlink}); refusing "
                    f"to write through an aliased inode: {filename}"
                )
            resolved = path.resolve()
            if resolved != udir_resolved / filename:
                raise SoulEditError(
                    f"governed file resolves outside its universe slot, refusing: "
                    f"{filename}"
                )
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise SoulEditError(
                    f"governed file missing on disk: {filename}"
                ) from exc
            want = expected.get(filename)
            if want is not None:
                actual = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                if actual != want:
                    raise SoulEditError(
                        f"stale soul edit: {filename} changed since it was read "
                        "(expected-version mismatch) — re-read and retry"
                    )
            parsed[filename] = _split_frontmatter(raw)

        # The transform runs INSIDE the lock, between the read and the write, so
        # a concurrent append cannot land in the gap. It sees the bodies just
        # read and returns the bodies to write.
        if transform is not None:
            produced = transform({f: parsed[f][1] for f in transform_files}) or {}
            for filename, body in produced.items():
                if filename not in parsed:
                    raise SoulEditError(
                        f"transform returned {filename!r}, which was not in "
                        "transform_files"
                    )
                changes[filename] = body
            if not changes:
                return None

        # Pass 2 — apply.
        for filename, new_body in changes.items():
            meta, old_body = parsed[filename]
            body = new_body if (new_body or "").strip() else old_body
            if filename not in _LEARNED_STATUS_EXEMPT:
                meta["status"] = "learned"
                meta["learned_from"] = source
                meta["learned_at"] = now
                # Provenance travels WITH learned_from, including its absence: a
                # direct edit contributes no keys and DROPS any the previous
                # edit recorded, so a section can never show provenance that
                # belongs to different words than the ones now in it.
                for key in ("learned_turn_id", "learned_utterance_digest"):
                    meta.pop(key, None)
                meta.update(provenance_fm)
            if name and filename == "identity.md":
                meta["name"] = name
            rendered = _render(meta, body)
            new_contents[filename] = rendered
            _atomic_write_text(universe_dir / filename, rendered)
            updated.append(filename)

        log_entry = summary.strip() or f"learned {', '.join(sorted(updated))}"
        _append_log(universe_dir, f"- learned: {log_entry} (source: {source})")
        snapshot_rel = _write_edit_snapshot(
            universe_dir,
            files=new_contents,
            source=source,
            context=context,
            summary=log_entry,
            stamp=now,
            provenance_fm=provenance_fm,
        )

    result: dict[str, Any] = {
        "updated_files": sorted(updated),
        "snapshot": snapshot_rel,
        "log_entry": log_entry,
        "source": source,
    }
    if isinstance(provenance, FounderUtteranceProvenance):
        result["turn_id"] = provenance.turn_id
        result["utterance_digest"] = provenance.digest
    return result


def _append_log(universe_dir: Path, line: str) -> None:
    log_path = universe_dir / "log.md"
    assert_contained(universe_dir, log_path)
    try:
        text = log_path.read_text(encoding="utf-8")
    except OSError:
        text = "# Update Log\n"
    if not text.endswith("\n"):
        text += "\n"
    _atomic_write_text(log_path, text + line + "\n")


def _write_edit_snapshot(
    universe_dir: Path,
    *,
    files: dict[str, str],
    source: str,
    context: str,
    summary: str,
    stamp: str,
    provenance_fm: "dict[str, str] | None" = None,
) -> str:
    """Write a self-describing snapshot of this edit and index it.

    Every accepted edit writes a NEW snapshot (policy), so the record embeds
    the edit metadata — two identical-content edits still produce distinct
    snapshots because each records its own event.
    """
    versions_dir = universe_dir / SOUL_VERSIONS_DIR
    # Refuse a soul_versions symlinked to an external dir BEFORE any fs op
    # (parent-directory symlink write-escape — Codex re-review). realpath of a
    # not-yet-created dir stays inside the universe; a symlink resolves out and is
    # refused.
    assert_contained(universe_dir, versions_dir)
    versions_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(versions_dir.glob("[0-9][0-9][0-9][0-9].md"))
    next_number = 1
    if existing:
        try:
            next_number = int(existing[-1].stem) + 1
        except ValueError:
            next_number = len(existing) + 1

    meta = {
        "type": "Soul Edit Snapshot",
        "title": f"Soul Edit {next_number:04d}",
        "description": summary,
        "source": source,
        "learned_at": stamp,
        "files": ", ".join(sorted(files)),
    }
    # The snapshot is the durable per-edit record, so provenance belongs on it as
    # well as on the files — a section can be edited again, the snapshot cannot.
    for key, value in (provenance_fm or {}).items():
        meta[key.removeprefix("learned_")] = value
    body_parts = [f"# Soul Edit {next_number:04d}", "", context, ""]
    for filename in sorted(files):
        body_parts += [f"## {filename}", "", "```markdown", files[filename].rstrip(), "```", ""]
    snapshot_name = f"{next_number:04d}.md"
    _atomic_write_text(
        versions_dir / snapshot_name, _render(meta, "\n".join(body_parts))
    )

    index_path = versions_dir / "index.md"
    try:
        index_text = index_path.read_text(encoding="utf-8")
    except OSError:
        index_text = "# Soul Version Index\n"
    if not index_text.endswith("\n"):
        index_text += "\n"
    _atomic_write_text(
        index_path,
        index_text
        + f"- [{next_number:04d}]({snapshot_name}) — learned: {summary}\n",
    )
    return f"{SOUL_VERSIONS_DIR}/{snapshot_name}"
