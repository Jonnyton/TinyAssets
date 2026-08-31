"""Admission grammar for workspace provisioning manifests (OpenSpec ``workspace-node``, D3).

Admission here is a *grammar*: a manifest line is admitted only when it parses as one
of the small number of shapes the platform is willing to resolve, and everything else
is refused by construction. A denylist is the inverse and is always wrong for this job,
because it has to enumerate every way a manifest can name something other than a pinned
registry artifact -- and manifest formats keep inventing new ones (``pip`` option lines,
PEP 508 direct references, ``npm`` aliases, workspace protocols), so each new spelling
is a silent admission until somebody notices. Here the parser knows one Python record
shape (``name[extras]==version ; marker --hash=sha256:...``) and one Node resolution
shape (a ``registry.npmjs.org`` tarball with a ``sha512-`` digest), so an unknown
spelling fails to parse and is refused with a named reason rather than passed through.

Python records are parsed by ``packaging`` -- the same library the index and the
installer use -- so admission cannot disagree with pip about what a line means. The
pre-checks (option lines, includes, direct references, paths, VCS schemes, ``${VAR}``)
run *before* that parse so each one keeps its precise reason, and the marker allowlist
runs *after* it, because ``packaging`` accepts PEP 508 variables this sink cannot reason
about. The pinned version is validated by ``packaging`` and then kept **verbatim** --
rewriting it would hand pip a string the manifest never wrote -- while the marker is
re-serialised from this module's own parse tree, which is what makes two spellings of
one condition one digest. Node manifests are parsed as JSON with duplicate keys and
non-finite numbers refused, since either lets the admitted document differ from the
installed one.

The module is pure: it parses text and returns an admitted plan or raises
:class:`ProvisionRefused`. No process is started, no network address is opened, no file
is read, and no configuration is consulted -- ``urllib.parse`` appears only to split a
``resolved`` URL, which does no I/O. The caller reads the manifests through the held
lease directory handle and hands the decoded text here.

The resolver stages **only** the normalized text this module returns
(:attr:`PythonPlan.normalized_text`, :attr:`NodePlan.normalized_package_json`,
:attr:`NodePlan.normalized_lockfile`); the original file text never reaches pip or npm.
The digest covers exactly those bytes, which is what binds the later offline install to
what was admitted.

Refusal reasons are a closed set (:data:`REFUSAL_REASONS`) so the sink can map each one
to one actionable failure class (design D6). ``not_regular_file`` is raised by the
manifest reader, not by this module; it is listed here so the reason vocabulary has a
single home.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, NoReturn
from urllib.parse import urlsplit

from packaging.markers import InvalidMarker, Marker
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

__all__ = [
    "REFUSAL_REASONS",
    "NodePackage",
    "NodePlan",
    "ProvisionRefused",
    "PythonPlan",
    "PythonRecord",
    "admit_manifest_bytes",
    "admit_node",
    "admit_requirements",
]

REFUSAL_CODE: Final[str] = "workspace_provision_refused"

REFUSAL_REASONS: Final[frozenset[str]] = frozenset(
    {
        # Python requirement grammar
        "option_line",
        "include",
        "direct_url",
        "local_path",
        "vcs",
        "unpinned",
        "missing_hash",
        "bad_marker",
        "bad_name",
        "env_reference",
        # Node manifest / lockfile grammar
        "bad_json",
        "non_registry_resolution",
        "missing_lockfile",
        "git_dependency",
        "file_dependency",
        "url_dependency",
        "workspace_dependency",
        "bundled_dependency",
        "lockfile_version",
        # Shared byte-level admission
        "too_large",
        "not_utf8",
        # Raised by the manifest reader (lease dirfd), never by this module.
        "not_regular_file",
    }
)

MAX_DETAIL_CHARS: Final[int] = 200

_REGISTRY_NETLOC: Final[str] = "registry.npmjs.org"
_NPM_DEPENDENCY_FIELDS: Final[tuple[str, ...]] = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
)
# Fields whose names must have a top-level ``node_modules/<name>`` lockfile entry.
_NPM_INSTALLED_FIELDS: Final[tuple[str, ...]] = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
)
#: Fields carried from a lockfile entry into the rebuilt lockfile. Everything
#: else is dropped: the staged file holds what admission validated and nothing
#: it merely tolerated.
_LOCK_ENTRY_FLAGS: Final[tuple[str, ...]] = (
    "dev",
    "optional",
    "peer",
    "hasInstallScript",
)
_LOCK_ENTRY_MAPS: Final[tuple[str, ...]] = ("engines", "bin")

# Dependency maps that may appear *inside* a lockfile entry.
_NPM_ENTRY_FIELDS: Final[tuple[str, ...]] = (
    "dependencies",
    "optionalDependencies",
    "peerDependencies",
)

_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s/@]+@")
_PEP508_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_HEAD = re.compile(r"^(?P<name>[^\[\]\s]+)\s*(?:\[(?P<extras>[^\[\]]*)\])?$")
_SHA256_HASH = re.compile(r"^[0-9a-f]{64}$")
_MAX_NAME_CHARS: Final[int] = 128

_VCS_SCHEMES: Final[tuple[str, ...]] = ("git+", "hg+", "svn+", "bzr+")
_INCLUDE_OPTIONS: Final[frozenset[str]] = frozenset(
    {"-r", "--requirement", "-c", "--constraint"}
)
_LOCAL_PREFIXES: Final[tuple[str, ...]] = ("./", "../", ".\\", "..\\", "/", "\\", "~")
_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")

# ``packaging`` accepts every PEP 508 variable. These are the ones the sink can reason
# about; ``extra``, ``platform_release``, ``platform_version`` and friends are refused
# even though they parse, which is why this allowlist runs after the packaging parse.
_MARKER_VARIABLES: Final[frozenset[str]] = frozenset(
    {
        "python_version",
        "python_full_version",
        "sys_platform",
        "platform_machine",
        "platform_system",
        "implementation_name",
        "os_name",
    }
)
_MARKER_FLIP: Final[Mapping[str, str]] = {
    "==": "==",
    "!=": "!=",
    ">=": "<=",
    "<=": ">=",
    "<": ">",
    ">": "<",
}
_MARKER_KEYWORDS: Final[frozenset[str]] = frozenset({"and", "or", "not", "in"})
_MARKER_TOKEN = re.compile(
    r"(?P<lparen>\()"
    r"|(?P<rparen>\))"
    r"|(?P<op>==|!=|>=|<=|>|<)"
    r"|(?P<string>'[^'\\\x00-\x1f]{0,64}'|\"[^\"\\\x00-\x1f]{0,64}\")"
    r"|(?P<word>[A-Za-z_][A-Za-z0-9_]*)"
)
_MAX_MARKER_CHARS: Final[int] = 512

# npm allows legacy mixed-case names; it forbids a leading ``.``/``_`` and caps at 214.
_NPM_NAME = re.compile(r"^(?:@[A-Za-z0-9][A-Za-z0-9._-]*/)?[A-Za-z0-9][A-Za-z0-9._-]*$")
_MAX_NPM_NAME_CHARS: Final[int] = 214
# node-semver's own range grammar, not a charset: a charset admits `latest`,
# `not-a-range` and `1.2.3.4`, none of which npm would resolve the way the
# lockfile claims. Built up from the pieces the grammar names so each one is
# legible: nr < xr < partial < primitive/tilde/caret < simple < range < set.
_SV_NR = r"(?:0|[1-9][0-9]*)"
_SV_XR = r"(?:x|X|\*|" + _SV_NR + r")"
_SV_PART = r"(?:[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)"
_SV_QUALIFIER = r"(?:-" + _SV_PART + r")?(?:\+" + _SV_PART + r")?"
_SV_PARTIAL = (
    _SV_XR + r"(?:\." + _SV_XR + r"(?:\." + _SV_XR + _SV_QUALIFIER + r")?)?"
)
_SV_PRIMITIVE = r"(?:(?:<=|>=|<|>|=)\s*" + _SV_PARTIAL + r")"
_SV_TILDE = r"(?:~>?\s*" + _SV_PARTIAL + r")"
_SV_CARET = r"(?:\^\s*" + _SV_PARTIAL + r")"
_SV_SIMPLE = (
    r"(?:" + _SV_PRIMITIVE + r"|" + _SV_TILDE + r"|" + _SV_CARET
    + r"|" + _SV_PARTIAL + r")"
)
_SV_HYPHEN = r"(?:" + _SV_PARTIAL + r"\s+-\s+" + _SV_PARTIAL + r")"
_SV_RANGE = (
    r"(?:" + _SV_HYPHEN + r"|" + _SV_SIMPLE + r"(?:\s+" + _SV_SIMPLE + r")*)"
)
_SEMVER_RANGE = re.compile(
    r"^" + _SV_RANGE + r"(?:\s*\|\|\s*" + _SV_RANGE + r")*$"
)
_MAX_RANGE_CHARS: Final[int] = 128
_NPM_VERSION = re.compile(r"^[0-9][0-9A-Za-z.+\-]*$")
_SRI_SHA512 = re.compile(r"^sha512-[A-Za-z0-9+/]{86}==$")


class ProvisionRefused(Exception):
    """A manifest line or lockfile entry outside the admitted grammar.

    ``code`` is the sink's failure class; ``reason`` is the machine string the
    evidence records; ``line_no`` is the 1-based physical line the record started on
    (``None`` when the refusal is not about one line); ``detail`` is the offending
    text, redacted and truncated -- never a token and never a host path.
    """

    code: Final[str] = REFUSAL_CODE

    def __init__(self, reason: str, detail: str = "", *, line_no: int | None = None) -> None:
        if reason not in REFUSAL_REASONS:
            raise ValueError(f"unknown provisioning refusal reason: {reason!r}")
        self.reason = reason
        self.line_no = line_no
        self.detail = _safe_detail(detail)
        where = "" if line_no is None else f" (line {line_no})"
        suffix = f": {self.detail}" if self.detail else ""
        super().__init__(f"{REFUSAL_CODE}: {reason}{where}{suffix}")


def _safe_detail(text: str) -> str:
    """Redact URL userinfo, drop control characters, truncate to the detail cap."""
    redacted = _USERINFO.sub(r"\1[redacted]@", str(text))
    printable = "".join(ch if ch.isprintable() else "?" for ch in redacted)
    return printable[:MAX_DETAIL_CHARS]


def _refuse(reason: str, detail: str = "", line_no: int | None = None) -> NoReturn:
    raise ProvisionRefused(reason, detail, line_no=line_no)


# --------------------------------------------------------------------------------------
# Shared byte-level admission
# --------------------------------------------------------------------------------------


def admit_manifest_bytes(data: bytes, *, max_bytes: int) -> str:
    """Decode manifest bytes read from the lease into text, or refuse.

    Refuses anything over ``max_bytes``, anything holding a NUL byte (a text manifest
    never does; a NUL is how binary content and truncated UTF-16 arrive), and anything
    that is not strictly valid UTF-8. A leading BOM is stripped. Both the NUL and the
    decode failure are reported as ``not_utf8`` -- one reason for "these bytes are not
    admissible manifest text".
    """
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError(f"manifest bytes expected, got {type(data).__name__}")
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if len(data) > max_bytes:
        _refuse("too_large", f"{len(data)} bytes exceeds {max_bytes}")
    offset = bytes(data).find(b"\x00")
    if offset >= 0:
        _refuse("not_utf8", f"NUL byte at offset {offset}")
    try:
        text = bytes(data).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        _refuse("not_utf8", f"invalid UTF-8 at offset {exc.start}")
    return text[1:] if text.startswith(chr(0xFEFF)) else text


def _check_text_size(text: str, max_bytes: int, label: str) -> None:
    if not isinstance(text, str):
        raise TypeError(f"{label} must be str, got {type(text).__name__}")
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    size = len(text.encode("utf-8"))
    if size > max_bytes:
        _refuse("too_large", f"{label}: {size} bytes exceeds {max_bytes}")


# --------------------------------------------------------------------------------------
# Python requirements
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PythonRecord:
    """One admitted requirement: pinned, hashed, and normalized."""

    name: str
    extras: tuple[str, ...]
    version: str
    marker: str | None
    hashes: tuple[str, ...]

    def canonical(self) -> str:
        """The single canonical line this record contributes to the normalized text."""
        extras = f"[{','.join(self.extras)}]" if self.extras else ""
        marker = f" ; {self.marker}" if self.marker else ""
        hashes = "".join(f" --hash={value}" for value in self.hashes)
        return f"{self.name}{extras}=={self.version}{marker}{hashes}"


@dataclass(frozen=True, slots=True)
class PythonPlan:
    """The admitted requirement set, its normalized text, and the digest binding them.

    ``normalized_text`` is the only text the resolver may pass to pip: one canonical
    record per line, sorted. ``digest`` is sha256 over exactly those bytes.
    """

    records: tuple[PythonRecord, ...]
    digest: str
    normalized_text: str


def admit_requirements(text: str, *, max_bytes: int = 256 * 1024) -> PythonPlan:
    """Admit a ``requirements.txt`` body, or refuse with the offending line.

    The only admitted shape is ``name[extras]==version ; marker --hash=sha256:<64 hex>``
    with optional extras and marker and one or more hashes. Comments and blank lines are
    stripped; a physical line ending in a backslash continues onto the next, as ``pip``
    joins them, and the refusal's ``line_no`` is the line the record started on.

    Checks run in a fixed order so one input always produces one reason: ``${VAR}``
    references, option lines, VCS schemes, direct references, local paths, then the
    name/extras, then the marker, then the ``packaging`` parse, then the pin, then the
    hashes.
    """
    _check_text_size(text, max_bytes, "requirements")
    records: list[PythonRecord] = []
    # (name, marker) -> (line_no, canonical) -- the pin must be unambiguous per marker.
    seen: dict[tuple[str, str | None], tuple[int, str]] = {}
    for line_no, line in _logical_lines(text):
        record = _parse_requirement(line, line_no)
        key = (record.name, record.marker)
        previous = seen.get(key)
        if previous is not None:
            if previous[1] == record.canonical():
                continue
            _refuse(
                "unpinned",
                f"{record.name} already pinned on line {previous[0]}",
                line_no,
            )
        seen[key] = (line_no, record.canonical())
        records.append(record)

    canonical_lines = sorted(record.canonical() for record in records)
    normalized = "".join(f"{value}\n" for value in canonical_lines)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    ordered = tuple(sorted(records, key=lambda record: record.canonical()))
    return PythonPlan(records=ordered, digest=digest, normalized_text=normalized)


def _strip_comment(line: str) -> str:
    """Drop a ``#`` comment, ignoring a ``#`` inside a quoted marker literal."""
    quote: str | None = None
    for index, char in enumerate(line):
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in "'\"":
            quote = char
            continue
        if char == "#":
            return line[:index]
    return line


def _logical_lines(text: str) -> Iterable[tuple[int, str]]:
    """Yield ``(first physical line number, joined content)`` for non-empty records."""
    pending: list[str] = []
    start: int | None = None
    for offset, raw in enumerate(text.splitlines()):
        line_no = offset + 1
        content = _strip_comment(raw.replace("\r", ""))
        if content.rstrip().endswith("\\"):
            if start is None:
                start = line_no
            pending.append(content.rstrip()[:-1])
            continue
        if pending:
            joined = "".join([*pending, content])
            pending = []
            first = start if start is not None else line_no
            start = None
            if joined.strip():
                yield first, joined.strip()
            continue
        if content.strip():
            yield line_no, content.strip()
    if pending:
        joined = "".join(pending).strip()
        if joined:
            yield (start if start is not None else 1), joined


def _parse_requirement(line: str, line_no: int) -> PythonRecord:
    if "${" in line or "$(" in line:
        _refuse("env_reference", line, line_no)
    if line.startswith("-"):
        token = line.split(maxsplit=1)[0].split("=", 1)[0]
        reason = "include" if token in _INCLUDE_OPTIONS else "option_line"
        _refuse(reason, line, line_no)
    lowered = line.lower()
    for scheme in _VCS_SCHEMES:
        if scheme in lowered:
            _refuse("vcs", line, line_no)
    if "://" in line or "@" in line:
        _refuse("direct_url", line, line_no)
    if line.startswith(_LOCAL_PREFIXES) or _DRIVE_PATH.match(line):
        _refuse("local_path", line, line_no)

    spec, hash_text = _split_hashes(line)
    body, marker_text = _split_marker(spec)
    # Name and marker are checked before the packaging parse purely so that an invalid
    # requirement reports which half was wrong; packaging reports one error for all.
    head, _tail = _split_operator(body.strip())
    _check_head(head.strip(), line, line_no)
    if marker_text is not None and not marker_text.strip():
        _refuse("bad_marker", line, line_no)

    try:
        requirement = Requirement(spec)
    except InvalidRequirement:
        if marker_text is not None and not _marker_parses(marker_text):
            _refuse("bad_marker", marker_text, line_no)
        _refuse("unpinned", line, line_no)

    if requirement.url is not None:
        _refuse("direct_url", line, line_no)
    version = _admitted_version(requirement, line, line_no)
    marker = None
    if requirement.marker is not None:
        # The ORIGINAL text, never ``str(requirement.marker)``: packaging
        # re-quotes every literal with double quotes, so a literal holding a
        # double quote comes back with its clause boundaries moved -- one
        # comparison arrives as two. Its *parse* is right; its output is not.
        marker = _canonical_marker(marker_text or "", line_no)
    extras = tuple(sorted(canonicalize_name(extra) for extra in requirement.extras))
    hashes = _parse_hashes(hash_text, line, line_no)
    return PythonRecord(
        name=canonicalize_name(requirement.name),
        extras=extras,
        version=version,
        marker=marker,
        hashes=hashes,
    )


def _split_hashes(line: str) -> tuple[str, str]:
    """Split a joined line into its requirement part and its ``--hash`` part."""
    for index in range(len(line)):
        if not line.startswith("--hash", index):
            continue
        if index == 0 or line[index - 1].isspace():
            return line[:index], line[index:]
    return line, ""


def _split_marker(spec: str) -> tuple[str, str | None]:
    """Split at the first ``;`` that is not inside a quoted literal."""
    quote: str | None = None
    for index, char in enumerate(spec):
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in "'\"":
            quote = char
            continue
        if char == ";":
            return spec[:index], spec[index + 1 :]
    return spec, None


def _split_operator(body: str) -> tuple[str, str]:
    """Split ``name[extras]`` from the version specifier, ignoring extras brackets."""
    depth = 0
    for index, char in enumerate(body):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        elif depth == 0 and char in "=<>!~":
            return body[:index], body[index:]
    return body, ""


def _check_head(head: str, line: str, line_no: int) -> None:
    """Validate ``name[extras]`` so a malformed name reports ``bad_name``, not a pin."""
    match = _HEAD.match(head)
    if match is None or not head:
        _refuse("bad_name", line, line_no)
    name = match.group("name")
    if len(name) > _MAX_NAME_CHARS or not _PEP508_NAME.match(name):
        _refuse("bad_name", name, line_no)
    raw_extras = match.group("extras")
    if raw_extras is None:
        return
    parts = [part.strip() for part in raw_extras.split(",")]
    if not parts or any(not part for part in parts):
        _refuse("bad_name", line, line_no)
    for part in parts:
        if len(part) > _MAX_NAME_CHARS or not _PEP508_NAME.match(part):
            _refuse("bad_name", part, line_no)


def _admitted_version(requirement: Requirement, line: str, line_no: int) -> str:
    """Require exactly one ``==`` specifier holding a wildcard-free PEP 440 version.

    The version is *validated* by ``Version`` and then returned **verbatim**.
    Rewriting it to its normalized form would hand pip a string the manifest never
    wrote, and the wheel filename the hash pins is built from the version as the
    project published it.
    """
    specifiers = list(requirement.specifier)
    if len(specifiers) != 1:
        _refuse("unpinned", line, line_no)
    specifier = specifiers[0]
    if specifier.operator != "==" or "*" in specifier.version:
        _refuse("unpinned", line, line_no)
    try:
        Version(specifier.version)
    except InvalidVersion:
        _refuse("unpinned", line, line_no)
    return specifier.version


def _parse_hashes(hash_text: str, line: str, line_no: int) -> tuple[str, ...]:
    """Collect the sha256 hex digests; any other algorithm names itself in the detail."""
    tokens = hash_text.split()
    values: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("--hash="):
            value = token[len("--hash=") :]
        elif token == "--hash":
            if index + 1 >= len(tokens):
                _refuse("missing_hash", line, line_no)
            index += 1
            value = tokens[index]
        else:
            _refuse("missing_hash", token, line_no)
        algorithm, _, digest = value.partition(":")
        if algorithm != "sha256":
            _refuse("missing_hash", f"unsupported hash algorithm: {algorithm}", line_no)
        if not _SHA256_HASH.match(digest):
            _refuse("missing_hash", f"malformed sha256 digest: {digest}", line_no)
        values.append(f"sha256:{digest}")
        index += 1
    if not values:
        _refuse("missing_hash", line, line_no)
    return tuple(sorted(set(values)))


# --------------------------------------------------------------------------------------
# PEP 508 markers: packaging parses, then a conservative allowlist walk
# --------------------------------------------------------------------------------------


def _marker_parses(text: str) -> bool:
    try:
        Marker(text)
    except (InvalidMarker, ValueError):
        return False
    return True


def _canonical_marker(text: str, line_no: int) -> str:
    """Refuse a marker outside the sink's subset and return its canonical text.

    ``packaging`` has already accepted the marker by this point, but it admits every
    PEP 508 variable -- including ``extra`` and the ``platform_*`` strings the
    resolver jail cannot answer for. This re-reads it with a small recursive-descent
    parser -- never interpreting it as Python -- requires every comparison to put one
    allowed variable against one plain ASCII literal, and re-serialises the tree: a
    comparison written literal-first is flipped to variable-first with the operator
    inverted, and commutative operands are ordered, so two spellings of one condition
    produce one digest.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > _MAX_MARKER_CHARS:
        _refuse("bad_marker", text, line_no)
    if not _marker_parses(stripped):
        _refuse("bad_marker", text, line_no)
    tokens = _tokenise_marker(stripped, line_no)
    tree = _MarkerParser(tokens, stripped, line_no).parse()
    canonical = _marker_text(tree)
    # Mandatory postcondition. The canonical text must still parse under
    # ``packaging``, and OUR parse of it must be the identical tree -- so a
    # literal whose quoting moved a clause boundary is refused here instead of
    # being handed to pip as a different condition. The comparison is against
    # our tree rather than ``Marker.__eq__`` because canonicalisation flips and
    # orders operands on purpose; both trees are normalised the same way, so
    # equality here is exactly 'means the same thing'.
    if not _marker_parses(canonical):
        _refuse("bad_marker", text, line_no)
    round_trip = _MarkerParser(
        _tokenise_marker(canonical, line_no), canonical, line_no
    ).parse()
    if round_trip != tree:
        _refuse("bad_marker", text, line_no)
    return canonical


def _tokenise_marker(text: str, line_no: int) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    position = 0
    while position < len(text):
        if text[position].isspace():
            position += 1
            continue
        match = _MARKER_TOKEN.match(text, position)
        if match is None:
            _refuse("bad_marker", text[position:], line_no)
        kind = match.lastgroup
        if kind is None:
            _refuse("bad_marker", text[position:], line_no)
        tokens.append((kind, match.group()))
        position = match.end()
    return tokens


class _MarkerParser:
    """Recursive descent over ``or`` > ``and`` > parenthesised term > comparison."""

    def __init__(self, tokens: Sequence[tuple[str, str]], text: str, line_no: int) -> None:
        self._tokens = tokens
        self._text = text
        self._line_no = line_no
        self._index = 0

    def parse(self) -> tuple[Any, ...]:
        node = self._or()
        if self._peek() is not None:
            _refuse("bad_marker", self._text, self._line_no)
        return node

    def _peek(self) -> tuple[str, str] | None:
        if self._index >= len(self._tokens):
            return None
        return self._tokens[self._index]

    def _take(self) -> tuple[str, str]:
        token = self._peek()
        if token is None:
            _refuse("bad_marker", self._text, self._line_no)
        self._index += 1
        return token

    def _or(self) -> tuple[Any, ...]:
        parts = [self._and()]
        while self._peek() == ("word", "or"):
            self._index += 1
            parts.append(self._and())
        return _combine("or", parts)

    def _and(self) -> tuple[Any, ...]:
        parts = [self._term()]
        while self._peek() == ("word", "and"):
            self._index += 1
            parts.append(self._term())
        return _combine("and", parts)

    def _term(self) -> tuple[Any, ...]:
        if self._peek() == ("lparen", "("):
            self._index += 1
            node = self._or()
            if self._peek() != ("rparen", ")"):
                _refuse("bad_marker", self._text, self._line_no)
            self._index += 1
            return node
        return self._comparison()

    def _comparison(self) -> tuple[Any, ...]:
        left = self._operand()
        operator = self._take()
        if operator[0] != "op":
            _refuse("bad_marker", operator[1], self._line_no)
        right = self._operand()
        # One side must be a literal: variable-to-variable says nothing the sink can act
        # on, and the resolver jail would have to answer for both sides.
        if left[0] == "var" and right[0] == "lit":
            return ("cmp", left[1], operator[1], right[1])
        if left[0] == "lit" and right[0] == "var":
            return ("cmp", right[1], _MARKER_FLIP[operator[1]], left[1])
        _refuse("bad_marker", self._text, self._line_no)

    def _operand(self) -> tuple[str, str]:
        kind, value = self._take()
        if kind == "string":
            literal = value[1:-1]
            if any(not 32 <= ord(char) < 127 for char in literal):
                _refuse("bad_marker", value, self._line_no)
            return ("lit", literal)
        if kind == "word":
            if value in _MARKER_KEYWORDS or value not in _MARKER_VARIABLES:
                _refuse("bad_marker", value, self._line_no)
            return ("var", value)
        _refuse("bad_marker", value, self._line_no)


def _combine(kind: str, parts: Sequence[tuple[Any, ...]]) -> tuple[Any, ...]:
    """Flatten same-kind children and order them: ``and``/``or`` are commutative."""
    if len(parts) == 1:
        return parts[0]
    flattened: list[tuple[Any, ...]] = []
    for part in parts:
        if part[0] == kind:
            flattened.extend(part[1])
        else:
            flattened.append(part)
    return (kind, tuple(sorted(flattened, key=_marker_text)))


def _quote_literal(value: str) -> str:
    """Quote with a character the literal does not hold.

    Always possible today: :data:`_MARKER_TOKEN` excludes a literal's own
    delimiter from its body, so a literal holds at most one kind of quote and
    the other is always free. PEP 508 has no escape sequence, so if that ever
    stops being true there is no correct output and the round-trip check in
    :func:`_canonical_marker` is what refuses -- not a guess here.
    """
    if '"' in value:
        return "'" + value + "'"
    return '"' + value + '"'


def _marker_text(node: tuple[Any, ...]) -> str:
    """Serialise the tree: variable, operator, quoted literal, minimal parens."""
    if node[0] == "cmp":
        return f"{node[1]} {node[2]} " + _quote_literal(node[3])
    joiner = " and " if node[0] == "and" else " or "
    parts = []
    for child in node[1]:
        text = _marker_text(child)
        if node[0] == "and" and child[0] == "or":
            text = f"({text})"
        parts.append(text)
    return joiner.join(parts)


# --------------------------------------------------------------------------------------
# Node: package.json + package-lock.json
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NodePackage:
    """One admitted lockfile entry: a registry tarball with a sha512 SRI digest."""

    name: str
    version: str
    resolved: str
    integrity: str


@dataclass(frozen=True, slots=True)
class NodePlan:
    """The admitted Node install, its normalized manifests, and the digest binding them.

    ``normalized_package_json`` and ``normalized_lockfile`` are canonical JSON and are
    the only texts the resolver may stage; ``digest`` is sha256 over the two joined by a
    NUL byte.
    """

    packages: tuple[NodePackage, ...]
    digest: str
    lockfile_version: int
    normalized_package_json: str
    normalized_lockfile: str


def admit_node(
    package_json_text: str,
    lockfile_text: str | None,
    *,
    max_bytes: int = 4 * 1024 * 1024,
) -> NodePlan:
    """Admit a ``package.json`` plus its ``package-lock.json``, or refuse.

    A lockfile is required: without one there is nothing pinned to admit. Every entry
    other than the root must resolve to a ``registry.npmjs.org`` tarball over HTTPS with
    a ``sha512-`` SRI digest, and every dependency the manifest names must have a
    top-level lockfile entry. Refusals carry no ``line_no`` -- JSON has no line the sink
    can act on, so the detail names the offending key.

    The two normalized texts are **rebuilt from validated fields**, never the
    admitted text passed through: a v2 lockfile carries a second, v1-shaped
    ``dependencies`` graph that no amount of validating the ``packages`` map
    touches, and forwarding the original would stage whatever it said.
    """
    _check_text_size(package_json_text, max_bytes, "package.json")
    if lockfile_text is None or not lockfile_text.strip():
        _refuse("missing_lockfile", "package-lock.json is required")
    _check_text_size(lockfile_text, max_bytes, "package-lock.json")

    manifest = _load_json(package_json_text, "package.json")
    lockfile = _load_json(lockfile_text, "package-lock.json")

    declared = _admit_manifest_dependencies(manifest)
    version, packages, lock_names, rebuilt_lockfile = _admit_lockfile(lockfile)

    optional_peers = _optional_peers(manifest)
    for field in _NPM_DEPENDENCY_FIELDS:
        if field == "peerDependencies":
            required = [name for name in declared.get(field, ()) if name not in optional_peers]
        elif field in _NPM_INSTALLED_FIELDS:
            required = list(declared.get(field, ()))
        else:
            required = []
        for name in required:
            if name not in lock_names:
                _refuse("non_registry_resolution", f"{field} {name}: not in lockfile")

    normalized_manifest = _canonical_json(_normalized_manifest(manifest, declared))
    normalized_lockfile = _canonical_json(rebuilt_lockfile)
    digest = hashlib.sha256(
        normalized_manifest.encode("utf-8") + b"\x00" + normalized_lockfile.encode("utf-8")
    ).hexdigest()
    return NodePlan(
        packages=packages,
        digest=digest,
        lockfile_version=version,
        normalized_package_json=normalized_manifest,
        normalized_lockfile=normalized_lockfile,
    )


def _reject_constant(value: str) -> NoReturn:
    _refuse("bad_json", f"non-finite number: {value}")


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _refuse("bad_json", f"duplicate key: {key}")
        result[key] = value
    return result


def _load_json(text: str, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(
            text, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_constant
        )
    except ProvisionRefused:
        raise
    except (ValueError, RecursionError) as exc:
        _refuse("bad_json", f"{label}: {exc}")
    if not isinstance(parsed, dict):
        _refuse("bad_json", f"{label}: top level is not an object")
    return parsed


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _check_no_workspaces(container: Mapping[str, Any], label: str) -> None:
    """A ``workspaces`` key anywhere means a local package tree this slice cannot pin."""
    if "workspaces" in container:
        _refuse("workspace_dependency", f"{label} declares workspaces")


def _optional_peers(manifest: Mapping[str, Any]) -> frozenset[str]:
    meta = manifest.get("peerDependenciesMeta")
    if not isinstance(meta, dict):
        return frozenset()
    return frozenset(
        name
        for name, entry in meta.items()
        if isinstance(entry, dict) and entry.get("optional") is True
    )


def _check_dependency_map(
    container: Mapping[str, Any], fields: Sequence[str], label: str
) -> dict[str, dict[str, str]]:
    """Every value in each named map must be a plain semver range.

    Returns the validated maps themselves, not just the names: they are what
    the rebuilt manifest and lockfile carry, so nothing reaches npm that this
    function did not read.
    """
    declared: dict[str, dict[str, str]] = {}
    for field in fields:
        block = container.get(field)
        if block is None:
            continue
        if not isinstance(block, dict):
            _refuse("bad_json", f"{label}{field} is not an object")
        validated: dict[str, str] = {}
        for name, spec in block.items():
            _check_npm_name(name, f"{label}{field} {name}")
            if not isinstance(spec, str):
                _refuse("bad_json", f"{label}{field} {name}: version is not a string")
            _check_range(name, spec, f"{label}{field}")
            validated[name] = spec
        declared[field] = validated
    return declared


def _admit_manifest_dependencies(
    manifest: Mapping[str, Any],
) -> dict[str, dict[str, str]]:
    _check_no_workspaces(manifest, "package.json")
    for field in ("bundleDependencies", "bundledDependencies"):
        if field in manifest:
            # Its own class: a bundled dependency ships inside another tarball, so
            # it is neither pinned by the lockfile nor fetched from the registry.
            _refuse("bundled_dependency", f"package.json declares {field}")
    return _check_dependency_map(manifest, _NPM_DEPENDENCY_FIELDS, "")


def _check_npm_name(name: str, label: str) -> None:
    if not isinstance(name, str) or len(name) > _MAX_NPM_NAME_CHARS or not _NPM_NAME.match(name):
        _refuse("bad_name", label)


def _check_range(name: str, spec: str, field: str) -> None:
    """Admit only a semver range; the pin itself comes from the lockfile."""
    label = f"{field} {name}: {spec}"
    value = spec.strip()
    lowered = value.lower()
    if not value:
        _refuse("non_registry_resolution", label)
    if lowered.startswith("workspace:") or lowered.startswith("link:"):
        _refuse("workspace_dependency", label)
    if lowered.startswith("file:") or value.startswith(("./", "../", "/", "~/")):
        _refuse("file_dependency", label)
    if lowered.startswith(("git+", "git:", "git@", "github:", "gitlab:", "bitbucket:", "gist:")):
        _refuse("git_dependency", label)
    if lowered.startswith(("http://", "https://")):
        _refuse("url_dependency", label)
    if lowered.startswith("npm:"):
        _refuse("non_registry_resolution", f"{label}: npm: alias")
    if "/" in value:
        _refuse("git_dependency", label)
    if ":" in value:
        _refuse("url_dependency", label)
    if len(value) > _MAX_RANGE_CHARS or not _SEMVER_RANGE.match(value):
        # A dist-tag (`latest`, `next`) lands here too: it is a name npm resolves
        # at install time, not a range the lockfile can be checked against.
        _refuse("non_registry_resolution", f"{label}: not a semver range")


def _carry_string(source_map: Mapping[str, Any], field: str, target: dict[str, Any]) -> None:
    """Carry a string field when it is a string; drop it otherwise."""
    value = source_map.get(field)
    if isinstance(value, str) and value:
        target[field] = value


def _carry_string_map(
    source_map: Mapping[str, Any], field: str, target: dict[str, Any]
) -> None:
    """Carry a ``{str: str}`` map (or a bare string, which ``bin`` may be)."""
    value = source_map.get(field)
    if isinstance(value, str):
        target[field] = value
        return
    if isinstance(value, dict) and all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        target[field] = dict(value)


def _normalized_entry(
    entry: Mapping[str, Any],
    nested: Mapping[str, dict[str, str]],
    *,
    root: bool,
    version: str = "",
    resolved: str = "",
    integrity: str = "",
) -> dict[str, Any]:
    """One lockfile entry, rebuilt from validated fields only."""
    rebuilt: dict[str, Any] = {}
    if root:
        _carry_string(entry, "name", rebuilt)
        _carry_string(entry, "version", rebuilt)
    else:
        rebuilt["version"] = version
        rebuilt["resolved"] = resolved
        rebuilt["integrity"] = integrity
    for flag in _LOCK_ENTRY_FLAGS:
        if entry.get(flag) is True:
            rebuilt[flag] = True
    _carry_string(entry, "license", rebuilt)
    for field in _LOCK_ENTRY_MAPS:
        _carry_string_map(entry, field, rebuilt)
    _carry_string_map(entry, "funding", rebuilt)
    for field, specs in nested.items():
        if specs:
            rebuilt[field] = dict(specs)
    return rebuilt


def _normalized_manifest(
    manifest: Mapping[str, Any], declared: Mapping[str, dict[str, str]]
) -> dict[str, Any]:
    """The package.json the resolver stages: name, version, the validated maps.

    ``scripts`` is deliberately not carried. The offline install may run
    lifecycle scripts, and the root manifest is the one file admission could
    hand it a command through, so it hands it none.
    """
    rebuilt: dict[str, Any] = {}
    name = manifest.get("name")
    if name is not None:
        _check_npm_name(name, "package.json name")
        rebuilt["name"] = name
    _carry_string(manifest, "version", rebuilt)
    for field, specs in declared.items():
        if specs:
            rebuilt[field] = dict(specs)
    optional = _optional_peers(manifest)
    if optional:
        rebuilt["peerDependenciesMeta"] = {
            name: {"optional": True} for name in sorted(optional)
        }
    return rebuilt


def _admit_lockfile(
    lockfile: Mapping[str, Any],
) -> tuple[int, tuple[NodePackage, ...], frozenset[str], dict[str, Any]]:
    version = lockfile.get("lockfileVersion")
    if not isinstance(version, int) or isinstance(version, bool) or version not in (2, 3):
        _refuse("lockfile_version", f"lockfileVersion={version!r}; only 2 and 3 are admitted")
    _check_no_workspaces(lockfile, "package-lock.json")
    entries = lockfile.get("packages")
    if not isinstance(entries, dict):
        _refuse("lockfile_version", "lockfile has no packages map")

    packages: set[NodePackage] = set()
    top_level: set[str] = set()
    rebuilt_entries: dict[str, Any] = {}
    for key, entry in entries.items():
        if not isinstance(entry, dict):
            _refuse("bad_json", f"{key}: entry is not an object")
        label = "root entry" if key == "" else key
        _check_no_workspaces(entry, label)
        nested = _check_dependency_map(entry, _NPM_ENTRY_FIELDS, f"{label} ")
        if key == "":
            rebuilt_entries[key] = _normalized_entry(entry, nested, root=True)
            continue
        if entry.get("link") is True:
            _refuse("workspace_dependency", f"{key}: link")
        if not key.startswith("node_modules/"):
            _refuse("workspace_dependency", f"{key}: not under node_modules/")
        name = key.rsplit("node_modules/", 1)[1]
        _check_npm_name(name, key)
        if key == f"node_modules/{name}":
            top_level.add(name)
        package = NodePackage(
            name=name,
            version=_entry_version(key, entry),
            resolved=_entry_resolved(key, entry),
            integrity=_entry_integrity(key, entry),
        )
        packages.add(package)
        rebuilt_entries[key] = _normalized_entry(
            entry,
            nested,
            root=False,
            version=package.version,
            resolved=package.resolved,
            integrity=package.integrity,
        )
    ordered = tuple(
        sorted(packages, key=lambda item: (item.name, item.version, item.resolved))
    )
    # Rebuilt, never forwarded, and always v3: a v2 document also carries a
    # second v1-shaped `dependencies` graph, and forwarding the original text
    # would stage whatever THAT said -- a URL the packages map never mentioned.
    rebuilt: dict[str, Any] = {}
    _carry_string(lockfile, "name", rebuilt)
    _carry_string(lockfile, "version", rebuilt)
    rebuilt["lockfileVersion"] = 3
    if lockfile.get("requires") is True:
        rebuilt["requires"] = True
    rebuilt["packages"] = rebuilt_entries
    return version, ordered, frozenset(top_level), rebuilt


def _entry_version(key: str, entry: Mapping[str, Any]) -> str:
    value = entry.get("version")
    if not isinstance(value, str) or len(value) > _MAX_RANGE_CHARS or not _NPM_VERSION.match(value):
        _refuse("unpinned", f"{key}: version={value!r}")
    return value


def _entry_resolved(key: str, entry: Mapping[str, Any]) -> str:
    """Require an HTTPS ``registry.npmjs.org`` tarball, decided by parsing the URL."""
    value = entry.get("resolved")
    if value is None:
        _refuse("non_registry_resolution", f"{key}: no resolved")
    if not isinstance(value, str) or not value:
        _refuse("non_registry_resolution", f"{key}: resolved={value!r}")
    lowered = value.lower()
    if lowered.startswith("file:") or value.startswith(("./", "../", "/", "~/")):
        _refuse("file_dependency", f"{key}: {value}")
    if lowered.startswith(("git+", "git:", "git@", "github:", "gitlab:", "bitbucket:", "gist:")):
        _refuse("git_dependency", f"{key}: {value}")
    if lowered.startswith("http://"):
        _refuse("url_dependency", f"{key}: {value}")
    try:
        parts = urlsplit(value)
    except ValueError as exc:
        _refuse("url_dependency", f"{key}: {exc}")
    if parts.scheme != "https":
        _refuse("url_dependency", f"{key}: scheme {parts.scheme!r}")
    # Checked before the host comparison so the credential is never echoed in a detail.
    if "@" in parts.netloc:
        _refuse("non_registry_resolution", f"{key}: resolved carries userinfo")
    # netloc, not hostname: a port belongs to a different address.
    if parts.netloc != _REGISTRY_NETLOC:
        _refuse("non_registry_resolution", f"{key}: host {parts.netloc!r}")
    if not parts.path.endswith(".tgz"):
        _refuse("non_registry_resolution", f"{key}: path {parts.path!r}")
    if parts.query or parts.fragment:
        _refuse("non_registry_resolution", f"{key}: resolved carries a query or fragment")
    return value


def _entry_integrity(key: str, entry: Mapping[str, Any]) -> str:
    """Require ``sha512-``; a weaker algorithm names itself in the detail."""
    value = entry.get("integrity")
    if value is None:
        _refuse("non_registry_resolution", f"{key}: no integrity")
    if not isinstance(value, str) or "-" not in value:
        _refuse("non_registry_resolution", f"{key}: integrity={value!r}")
    algorithm = value.split("-", 1)[0]
    if algorithm != "sha512":
        _refuse("non_registry_resolution", f"{key}: integrity algorithm {algorithm!r}")
    if not _SRI_SHA512.match(value):
        _refuse("non_registry_resolution", f"{key}: integrity={value!r}")
    return value
