"""Admission grammar for workspace provisioning manifests (OpenSpec ``workspace-node``, D3).

Admission here is a *grammar*: a manifest line is admitted only when it parses as one
of the small number of shapes the platform is willing to resolve, and everything else
is refused by construction. A denylist is the inverse and is always wrong for this job,
because it has to enumerate every way a manifest can name something other than a pinned
registry artifact -- and manifest formats keep inventing new ones (``pip`` option lines,
PEP 508 direct references, ``npm`` aliases, workspace protocols), so each new spelling
is a silent admission until somebody notices. Here the parser knows one Python record
shape (``name[extras]==version ; marker --hash=sha256:...``) and one Node resolution
shape (a ``https://registry.npmjs.org/`` tarball with an SRI digest), so an unknown
spelling fails to parse and is refused with a named reason rather than passed through.

The module is pure: it parses text and returns an admitted plan or raises
:class:`ProvisionRefused`. No process is started, no network address is opened, no file
is read, and no configuration is consulted -- the caller reads the manifests through the
held lease directory handle and hands the decoded text here. A separate resolver
consumes the returned plan; binding the later offline install to
:attr:`PythonPlan.digest` / :attr:`NodePlan.digest` is what makes the admitted text and
the installed text the same text.

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
        "lockfile_version",
        # Shared byte-level admission
        "too_large",
        "not_utf8",
        # Raised by the manifest reader (lease dirfd), never by this module.
        "not_regular_file",
    }
)

MAX_DETAIL_CHARS: Final[int] = 200

_REGISTRY_PREFIX: Final[str] = "https://registry.npmjs.org/"
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

_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s/@]+@")
_PEP508_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_NAME_SEPARATORS = re.compile(r"[-_.]+")
_HEAD = re.compile(r"^(?P<name>[^\[\]\s]+)\s*(?:\[(?P<extras>[^\[\]]*)\])?$")
_SHA256_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
# PEP 440, without the tolerated ``v`` prefix and without wildcards: a pin is exact.
_VERSION = re.compile(
    r"^(?:[0-9]+!)?[0-9]+(?:\.[0-9]+)*"
    r"(?:[-_.]?(?:a|b|c|rc|alpha|beta|pre|preview)[-_.]?[0-9]*)?"
    r"(?:-[0-9]+|[-_.]?(?:post|rev|r)[-_.]?[0-9]*)?"
    r"(?:[-_.]?dev[-_.]?[0-9]*)?"
    r"(?:\+[a-z0-9]+(?:[-_.][a-z0-9]+)*)?$",
    re.IGNORECASE,
)
_MAX_NAME_CHARS: Final[int] = 128
_MAX_VERSION_CHARS: Final[int] = 64

_VCS_SCHEMES: Final[tuple[str, ...]] = ("git+", "hg+", "svn+", "bzr+")
_INCLUDE_OPTIONS: Final[frozenset[str]] = frozenset(
    {"-r", "--requirement", "-c", "--constraint"}
)
_LOCAL_PREFIXES: Final[tuple[str, ...]] = ("./", "../", ".\\", "..\\", "/", "\\", "~")
_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")

_MARKER_VARIABLES: Final[frozenset[str]] = frozenset(
    {
        "python_version",
        "sys_platform",
        "platform_machine",
        "platform_system",
        "implementation_name",
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
_SEMVER_RANGE = re.compile(r"^[0-9A-Za-z.+*^~<>=|,\- ]+$")
_MAX_RANGE_CHARS: Final[int] = 128
_NPM_VERSION = re.compile(r"^[0-9][0-9A-Za-z.+\-]*$")
_SRI_SHA512 = re.compile(r"^sha512-[A-Za-z0-9+/]{86}==$")
_SRI_SHA256 = re.compile(r"^sha256-[A-Za-z0-9+/]{43}=$")


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
    """One admitted requirement: pinned, hashed, and normalised."""

    name: str
    extras: tuple[str, ...]
    version: str
    marker: str | None
    hashes: tuple[str, ...]

    def canonical(self) -> str:
        """The single canonical line this record contributes to the admitted text."""
        extras = f"[{','.join(self.extras)}]" if self.extras else ""
        marker = f" ; {self.marker}" if self.marker else ""
        hashes = "".join(f" --hash={value}" for value in self.hashes)
        return f"{self.name}{extras}=={self.version}{marker}{hashes}"


@dataclass(frozen=True, slots=True)
class PythonPlan:
    """The admitted requirement set, its canonical text, and the digest binding them."""

    records: tuple[PythonRecord, ...]
    digest: str
    normalised_text: str


def admit_requirements(text: str, *, max_bytes: int = 256 * 1024) -> PythonPlan:
    """Admit a ``requirements.txt`` body, or refuse with the offending line.

    The only admitted shape is ``name[extras]==version ; marker --hash=sha256:<64 hex>``
    with optional extras and marker and one or more hashes. Comments and blank lines are
    stripped; a physical line ending in a backslash continues onto the next, as ``pip``
    joins them, and the refusal's ``line_no`` is the line the record started on.

    Checks run in a fixed order so one input always produces one reason: ``${VAR}``
    references, option lines, VCS schemes, direct references, local paths, then the
    record grammar (name/extras, operator/version, marker, hashes).
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
    normalised = "".join(f"{value}\n" for value in canonical_lines)
    digest = hashlib.sha256(normalised.encode("utf-8")).hexdigest()
    ordered = tuple(sorted(records, key=lambda record: record.canonical()))
    return PythonPlan(records=ordered, digest=digest, normalised_text=normalised)


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
    marker_text: str | None
    body, marker_text = _split_marker(spec)
    head, tail = _split_operator(body.strip())
    name, extras = _parse_head(head.strip(), line, line_no)
    version = _parse_pin(tail.strip(), line, line_no)
    marker = _parse_marker(marker_text, line_no) if marker_text is not None else None
    hashes = _parse_hashes(hash_text, line, line_no)
    return PythonRecord(
        name=name, extras=extras, version=version, marker=marker, hashes=hashes
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


def _parse_head(head: str, line: str, line_no: int) -> tuple[str, tuple[str, ...]]:
    match = _HEAD.match(head)
    if match is None or not head:
        _refuse("bad_name", line, line_no)
    name = match.group("name")
    if len(name) > _MAX_NAME_CHARS or not _PEP508_NAME.match(name):
        _refuse("bad_name", name, line_no)
    raw_extras = match.group("extras")
    if raw_extras is None:
        return _normalise_name(name), ()
    parts = [part.strip() for part in raw_extras.split(",")]
    if not parts or any(not part for part in parts):
        _refuse("bad_name", line, line_no)
    for part in parts:
        if len(part) > _MAX_NAME_CHARS or not _PEP508_NAME.match(part):
            _refuse("bad_name", part, line_no)
    extras = tuple(sorted({_normalise_name(part) for part in parts}))
    return _normalise_name(name), extras


def _normalise_name(name: str) -> str:
    """PEP 503 normalisation -- the form the resolver and the index agree on."""
    return _NAME_SEPARATORS.sub("-", name).lower()


def _parse_pin(tail: str, line: str, line_no: int) -> str:
    # ``===`` is named explicitly rather than left to the version regex: it is a real
    # PEP 440 operator (arbitrary equality, matched as a string), so it stays refused
    # even if the version grammar below is ever loosened.
    if not tail.startswith("==") or tail.startswith("==="):
        _refuse("unpinned", line, line_no)
    version = tail[2:].strip()
    if not version or len(version) > _MAX_VERSION_CHARS or not _VERSION.match(version):
        _refuse("unpinned", line, line_no)
    return version


def _parse_hashes(hash_text: str, line: str, line_no: int) -> tuple[str, ...]:
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
        if not _SHA256_HASH.match(value):
            _refuse("missing_hash", value, line_no)
        values.append(value)
        index += 1
    if not values:
        _refuse("missing_hash", line, line_no)
    return tuple(sorted(set(values)))


# --------------------------------------------------------------------------------------
# PEP 508 markers: a recursive-descent validator over a conservative subset
# --------------------------------------------------------------------------------------


def _parse_marker(text: str, line_no: int) -> str:
    """Validate a marker and return its canonical text.

    Only the five variables the sink can reason about are allowed, compared with
    ``== != >= <= < >`` against a plain ASCII string literal, combined with ``and``/
    ``or`` and parentheses. The marker is parsed into a tree and re-serialised, never
    interpreted as Python: a comparison written literal-first is flipped to
    variable-first and commutative operands are ordered, so two spellings of one
    condition produce one digest.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > _MAX_MARKER_CHARS:
        _refuse("bad_marker", text, line_no)
    tokens = _tokenise_marker(stripped, line_no)
    parser = _MarkerParser(tokens, stripped, line_no)
    return _marker_text(parser.parse())


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
        assert kind is not None
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
    if len(parts) == 1:
        return parts[0]
    flattened: list[tuple[Any, ...]] = []
    for part in parts:
        if part[0] == kind:
            flattened.extend(part[1])
        else:
            flattened.append(part)
    return (kind, tuple(sorted(flattened, key=_marker_text)))


def _marker_text(node: tuple[Any, ...]) -> str:
    if node[0] == "cmp":
        return f'{node[1]} {node[2]} "{node[3]}"'
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
    """One admitted lockfile entry: a registry tarball with an SRI digest."""

    name: str
    version: str
    resolved: str
    integrity: str


@dataclass(frozen=True, slots=True)
class NodePlan:
    """The admitted Node install, its canonical manifests, and the digest binding them."""

    packages: tuple[NodePackage, ...]
    digest: str
    lockfile_version: int
    canonical_manifest: str
    canonical_lockfile: str


def admit_node(
    package_json_text: str,
    lockfile_text: str | None,
    *,
    max_bytes: int = 4 * 1024 * 1024,
) -> NodePlan:
    """Admit a ``package.json`` plus its ``package-lock.json``, or refuse.

    A lockfile is required: without one there is nothing pinned to admit. Every entry
    other than the root must resolve to a ``https://registry.npmjs.org/`` tarball with a
    ``sha512-``/``sha256-`` SRI digest, and every dependency the manifest names must have
    a top-level lockfile entry. Refusals carry no ``line_no`` -- JSON has no line the
    sink can act on, so the detail names the offending key.
    """
    _check_text_size(package_json_text, max_bytes, "package.json")
    if lockfile_text is None or not lockfile_text.strip():
        _refuse("missing_lockfile", "package-lock.json is required")
    _check_text_size(lockfile_text, max_bytes, "package-lock.json")

    manifest = _load_json(package_json_text, "package.json")
    lockfile = _load_json(lockfile_text, "package-lock.json")

    declared = _admit_manifest_dependencies(manifest)
    version, packages, lock_names = _admit_lockfile(lockfile)

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

    canonical_manifest = _canonical_json(manifest)
    canonical_lockfile = _canonical_json(lockfile)
    digest = hashlib.sha256(
        canonical_manifest.encode("utf-8") + b"\x00" + canonical_lockfile.encode("utf-8")
    ).hexdigest()
    return NodePlan(
        packages=packages,
        digest=digest,
        lockfile_version=version,
        canonical_manifest=canonical_manifest,
        canonical_lockfile=canonical_lockfile,
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


def _optional_peers(manifest: Mapping[str, Any]) -> frozenset[str]:
    meta = manifest.get("peerDependenciesMeta")
    if not isinstance(meta, dict):
        return frozenset()
    return frozenset(
        name
        for name, entry in meta.items()
        if isinstance(entry, dict) and entry.get("optional") is True
    )


def _admit_manifest_dependencies(manifest: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    if "workspaces" in manifest:
        _refuse("workspace_dependency", "package.json declares workspaces")
    for field in ("bundleDependencies", "bundledDependencies"):
        if field in manifest:
            _refuse("url_dependency", f"package.json declares {field}")

    declared: dict[str, tuple[str, ...]] = {}
    for field in _NPM_DEPENDENCY_FIELDS:
        block = manifest.get(field)
        if block is None:
            continue
        if not isinstance(block, dict):
            _refuse("bad_json", f"{field} is not an object")
        names: list[str] = []
        for name, spec in block.items():
            _check_npm_name(name, f"{field} {name}")
            if not isinstance(spec, str):
                _refuse("bad_json", f"{field} {name}: version is not a string")
            _check_range(name, spec, field)
            names.append(name)
        declared[field] = tuple(names)
    return declared


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
        _refuse("non_registry_resolution", f"{label}: not a semver range")


def _admit_lockfile(
    lockfile: Mapping[str, Any],
) -> tuple[int, tuple[NodePackage, ...], frozenset[str]]:
    version = lockfile.get("lockfileVersion")
    if not isinstance(version, int) or isinstance(version, bool) or version not in (2, 3):
        _refuse("lockfile_version", f"lockfileVersion={version!r}; only 2 and 3 are admitted")
    entries = lockfile.get("packages")
    if not isinstance(entries, dict):
        _refuse("lockfile_version", "lockfile has no packages map")

    packages: set[NodePackage] = set()
    top_level: set[str] = set()
    for key, entry in entries.items():
        if key == "":
            continue
        if not isinstance(entry, dict):
            _refuse("bad_json", f"{key}: entry is not an object")
        if entry.get("link") is True:
            _refuse("workspace_dependency", f"{key}: link")
        if not key.startswith("node_modules/"):
            _refuse("workspace_dependency", f"{key}: not under node_modules/")
        name = key.rsplit("node_modules/", 1)[1]
        _check_npm_name(name, key)
        if key == f"node_modules/{name}":
            top_level.add(name)
        packages.add(
            NodePackage(
                name=name,
                version=_entry_version(key, entry),
                resolved=_entry_resolved(key, entry),
                integrity=_entry_integrity(key, entry),
            )
        )
    ordered = tuple(
        sorted(packages, key=lambda item: (item.name, item.version, item.resolved))
    )
    return version, ordered, frozenset(top_level)


def _entry_version(key: str, entry: Mapping[str, Any]) -> str:
    value = entry.get("version")
    if not isinstance(value, str) or len(value) > _MAX_RANGE_CHARS or not _NPM_VERSION.match(value):
        _refuse("unpinned", f"{key}: version={value!r}")
    return value


def _entry_resolved(key: str, entry: Mapping[str, Any]) -> str:
    value = entry.get("resolved")
    if not isinstance(value, str) or not value:
        _refuse("non_registry_resolution", f"{key}: no resolved")
    lowered = value.lower()
    if lowered.startswith("file:") or value.startswith(("./", "../", "/", "~/")):
        _refuse("file_dependency", f"{key}: {value}")
    if lowered.startswith(("git+", "git:", "git@", "github:", "gitlab:", "bitbucket:", "gist:")):
        _refuse("git_dependency", f"{key}: {value}")
    if lowered.startswith("http://"):
        _refuse("url_dependency", f"{key}: {value}")
    if value.startswith(_REGISTRY_PREFIX):
        return value
    if lowered.startswith("https://"):
        _refuse("non_registry_resolution", f"{key}: {value}")
    _refuse("url_dependency", f"{key}: {value}")


def _entry_integrity(key: str, entry: Mapping[str, Any]) -> str:
    value = entry.get("integrity")
    if not isinstance(value, str) or not (_SRI_SHA512.match(value) or _SRI_SHA256.match(value)):
        _refuse("non_registry_resolution", f"{key}: integrity={value!r}")
    return value
