"""Credential-blind git layer for the workspace effect sink.

No credentialed git ever opens a workspace. No host-side git opens a
workspace's ``.git`` after the workspace is published to user code. A
host-side, credential-free initializer may populate a fresh, unpublished
directory from a verified bundle.

That boundary is what the pieces here exist to hold. The token never reaches
argv, an environment or a file: it lives in this process and is handed to git
one request at a time by an in-memory broker bound to exactly one
``(protocol, host, path)``. Every child runs from an environment built from
empty with system and global git configuration disabled, hooks and fsmonitor
off, redirects refused, every protocol but HTTPS refused, and the remote
address pinned in the transport to addresses the outbound driver's classifier
validated as public unicast. Bundles are the only way objects cross between a
workspace and staging, and they must be prerequisite-free so that importing
one into an empty repository is a complete transfer. Nothing returned from
here carries the secret: output is bounded, scrubbed of every registered
secret plus generic credential patterns, reduced to one fixed error class, and
the same scrubbing runs over every exception message.

This module reads no environment variables. Callers pass the environment, the
minimal ``PATH``, the resolver, the classifier and the process launcher in;
tests substitute them by parameter, never by an environment switch.
"""

from __future__ import annotations

import ipaddress
import os
import re
import shlex
import signal
import socket
import stat
import subprocess
import sys
import threading
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "CredentialBroker",
    "GitResult",
    "WorkspaceGitError",
    "classify_stderr",
    "create_bundle",
    "forced_git_options",
    "git_environment",
    "kill_git",
    "libcurl_supports_multi_resolve",
    "pin_address",
    "populate_workspace_from_bundle",
    "run_git",
    "scrub_text",
    "unbundle_into_fresh_repo",
    "verify_bundle",
]

# ---------------------------------------------------------------------------
# Platform constants. The production host is Linux; the suite also runs on
# Windows, where the null device is spelled differently and there is no
# ``/bin/false``. ``NUL`` is not an executable, so an askpass pointing at it
# fails closed exactly like ``/bin/false`` -- and terminal prompts are off.
# ---------------------------------------------------------------------------

_IS_WINDOWS = os.name == "nt"
NULL_DEVICE = "NUL" if _IS_WINDOWS else "/dev/null"
FALSE_BINARY = "NUL" if _IS_WINDOWS else "/bin/false"
# SIGKILL does not exist on Windows, where the process-group path is unreachable
# anyway. Resolved once here so referencing it cannot raise at kill time.
_KILL_SIGNAL = getattr(signal, "SIGKILL", signal.SIGTERM)

#: Every code ``WorkspaceGitError.code`` may carry.
ERROR_CODES: frozenset[str] = frozenset(
    {
        "auth",
        "not_found",
        "non_fast_forward",
        "protected",
        "transport",
        "verification",
        "other",
        "address_refused",
        "bad_argument",
        "timeout",
    }
)

#: The classes :func:`classify_stderr` may return.
STDERR_CLASSES: tuple[str, ...] = (
    "auth",
    "not_found",
    "non_fast_forward",
    "protected",
    "transport",
    "verification",
    "other",
)

_MAX_CAPTURED_BYTES = 64 * 1024
_REDACTED = "[redacted]"
_MIN_SECRET_LENGTH = 8
_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
_REF_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


# ---------------------------------------------------------------------------
# Secret registry and scrubbing
# ---------------------------------------------------------------------------

_SECRET_LOCK = threading.Lock()
_SECRETS: Counter[str] = Counter()


def _register_secret(secret: str) -> None:
    with _SECRET_LOCK:
        _SECRETS[secret] += 1


def _unregister_secret(secret: str) -> None:
    with _SECRET_LOCK:
        if _SECRETS[secret] <= 1:
            del _SECRETS[secret]
        else:
            _SECRETS[secret] -= 1


def _registered_secrets() -> list[str]:
    with _SECRET_LOCK:
        return list(_SECRETS)


_SCRUB_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # userinfo in an https URL: https://user:token@host/...
    (re.compile(r"https://[^/@\s]+@"), f"https://{_REDACTED}@"),
    # an Authorization header value, however it is spelled
    (re.compile(r"(?i)(authorization\s*:\s*)([^\r\n]+)"), r"\1" + _REDACTED),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), _REDACTED),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), _REDACTED),
)


def scrub_text(text: str, extra_secrets: Iterable[str] = ()) -> str:
    """Remove every registered secret and every generic credential pattern.

    Exact-secret removal runs first (longest first, so a secret that contains
    another is not left half-redacted), then the generic patterns catch tokens
    this process never held.
    """
    if not text:
        return text
    secrets = {s for s in (*_registered_secrets(), *extra_secrets) if s}
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, _REDACTED)
    for pattern, replacement in _SCRUB_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class WorkspaceGitError(Exception):
    """A refusal or failure in the credential-blind git layer.

    ``code`` is one of :data:`ERROR_CODES`. The message is scrubbed at
    construction, so neither ``str(exc)`` nor ``exc.args`` can carry a secret.
    """

    def __init__(self, code: str, message: str = "") -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"unknown workspace git error code: {code!r}")
        scrubbed = scrub_text(message)
        self.code = code
        self.message = scrubbed
        super().__init__(f"{code}: {scrubbed}" if scrubbed else code)


# ---------------------------------------------------------------------------
# Credential broker
# ---------------------------------------------------------------------------

# The transport half: a helper git runs as ``credential.helper=!<python>
# <script> <socket>``. It holds no secret of its own -- it forwards the request
# git wrote on stdin to the broker's unix socket and copies the answer back.
_HELPER_SCRIPT = '''\
"""git credential helper: forward the request to the broker on a unix socket.

Invoked by git as ``<python> <this script> <socket path> <operation>``. It
holds no credential; the broker decides whether to answer at all.
"""

import socket
import sys


def main() -> int:
    if len(sys.argv) < 3:
        return 1
    sock_path = sys.argv[1]
    operation = sys.argv[2]
    payload = sys.stdin.read()
    request = "operation=" + operation + "\\n" + payload
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(15.0)
        client.connect(sock_path)
        client.sendall(request.encode("utf-8"))
        client.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            block = client.recv(65536)
            if not block:
                break
            chunks.append(block)
    sys.stdout.write(b"".join(chunks).decode("utf-8", "replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

# ``sun_path`` is 108 bytes on Linux and 104 on macOS; refuse loudly rather
# than bind a silently truncated path.
_MAX_SOCKET_PATH_BYTES = 100


def _normalise_path(raw: str) -> str:
    """Apply ``useHttpPath`` comparison semantics to a credential path."""
    value = raw.strip().strip("/")
    if value.endswith(".git"):
        value = value[: -len(".git")]
    return value.strip("/")


def _split_host_port(raw: str) -> tuple[str, str | None]:
    value = raw.strip()
    if value.count(":") == 1:
        name, _, port = value.partition(":")
        return name, port
    return value, None


class CredentialBroker:
    """An in-memory git credential helper bound to one repository.

    :meth:`answer` is the whole protocol and is pure -- it takes the framed
    request text and returns the response text, so the decision logic is
    testable in-process on any platform. :meth:`serve` is the transport and is
    POSIX-only by design: the token must never cross a loopback TCP socket any
    local process could connect to.
    """

    def __init__(
        self,
        protocol: str,
        host: str,
        path: str,
        username: str,
        secret: str,
    ) -> None:
        for label, value in (
            ("protocol", protocol),
            ("host", host),
            ("path", path),
            ("username", username),
            ("secret", secret),
        ):
            if not isinstance(value, str) or not value:
                raise WorkspaceGitError(
                    "bad_argument", f"credential {label} must be a non-empty str"
                )
            if "\n" in value or "\r" in value or "\x00" in value:
                raise WorkspaceGitError(
                    "bad_argument", f"credential {label} has a forbidden character"
                )
        if protocol.lower() != "https":
            raise WorkspaceGitError("bad_argument", "only https credentials are brokered")
        if len(secret) < _MIN_SECRET_LENGTH:
            raise WorkspaceGitError("bad_argument", "credential secret is implausibly short")

        self._protocol = protocol.lower()
        self._host = host.lower()
        self._path = _normalise_path(path)
        if not self._path:
            raise WorkspaceGitError("bad_argument", "credential path must name a repository")
        self._username = username
        self._secret = secret
        self._closed = False
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._socket_path: Path | None = None
        self._script_path: Path | None = None
        self._helper_command: str | None = None
        _register_secret(secret)

    # -- protocol ---------------------------------------------------------

    def answer(self, request_text: str) -> str | None:
        """Answer one framed credential request.

        The first line is ``operation=<get|store|erase>``; the rest are git's
        ``key=value`` request lines. ``get`` for this exact repository returns
        the credential; ``store`` and ``erase`` are ignored (empty response);
        anything else -- another host, another path, another username, an
        unknown operation, or any request after :meth:`close` -- returns
        ``None``, which git reads as "this helper has nothing", and the
        operation then fails to authenticate. That is the desired outcome.
        """
        if self._closed:
            return None
        fields: dict[str, str] = {}
        for line in request_text.splitlines():
            if not line or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key and key not in fields:
                fields[key] = value.strip()
        operation = fields.get("operation", "")
        if operation in ("store", "erase"):
            return ""
        if operation != "get":
            return None
        if fields.get("protocol", "").lower() != self._protocol:
            return None
        host, port = _split_host_port(fields.get("host", ""))
        if host.lower() != self._host:
            return None
        if port is not None and port != "443":
            return None
        if "path" not in fields:
            # useHttpPath is forced on; a request without a path cannot be
            # matched to one repository, so it is refused.
            return None
        if _normalise_path(fields["path"]) != self._path:
            return None
        requested_user = fields.get("username")
        if requested_user is not None and requested_user and requested_user != self._username:
            return None
        return f"username={self._username}\npassword={self._secret}\n"

    # -- transport --------------------------------------------------------

    def serve(
        self,
        *,
        socket_dir: str | os.PathLike[str],
        python_executable: str | None = None,
    ) -> str:
        """Start the unix-socket transport and return the ``credential.helper``.

        Returns the value to pass to :func:`forced_git_options`, of the form
        ``!<python> <helper script> <socket path>``.
        """
        if self._closed:
            raise WorkspaceGitError("bad_argument", "broker is closed")
        if _IS_WINDOWS:
            raise WorkspaceGitError(
                "transport",
                "the credential broker transport requires a POSIX unix domain socket",
            )
        if self._thread is not None:
            raise WorkspaceGitError("bad_argument", "broker is already serving")
        directory = Path(socket_dir)
        if not directory.is_dir():
            raise WorkspaceGitError(
                "bad_argument", "broker socket_dir must be an existing directory"
            )
        os.chmod(directory, 0o700)
        socket_path = directory / "credential.sock"
        script_path = directory / "credential_helper.py"
        if socket_path.exists() or script_path.exists():
            raise WorkspaceGitError("bad_argument", "broker socket_dir is not empty")
        if len(str(socket_path).encode("utf-8")) > _MAX_SOCKET_PATH_BYTES:
            raise WorkspaceGitError("bad_argument", "broker socket path is too long for sun_path")

        script_path.write_text(_HELPER_SCRIPT, encoding="utf-8")
        os.chmod(script_path, 0o500)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(socket_path))
            os.chmod(socket_path, 0o600)
            server.listen(8)
            server.settimeout(0.2)
        except OSError as exc:
            server.close()
            raise WorkspaceGitError(
                "transport", f"broker could not bind its socket: {exc}"
            ) from None

        self._server = server
        self._socket_path = socket_path
        self._script_path = script_path
        interpreter = python_executable or sys.executable
        self._helper_command = "!" + " ".join(
            shlex.quote(part) for part in (interpreter, str(script_path), str(socket_path))
        )
        self._thread = threading.Thread(
            target=self._accept_loop,
            name="workspace-git-credential-broker",
            daemon=True,
        )
        self._thread.start()
        return self._helper_command

    @property
    def helper_command(self) -> str:
        """The ``credential.helper`` value; only available while serving."""
        if self._closed or self._helper_command is None:
            raise WorkspaceGitError("bad_argument", "broker is not serving")
        return self._helper_command

    def _accept_loop(self) -> None:
        server = self._server
        if server is None:
            return
        while not self._closed:
            try:
                connection, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with connection:
                try:
                    self._handle(connection)
                except OSError:
                    continue

    def _handle(self, connection: socket.socket) -> None:
        connection.settimeout(15.0)
        chunks: list[bytes] = []
        total = 0
        while True:
            block = connection.recv(4096)
            if not block:
                break
            total += len(block)
            if total > _MAX_CAPTURED_BYTES:
                return
            chunks.append(block)
        request = b"".join(chunks).decode("utf-8", "replace")
        response = self.answer(request)
        if response is None:
            return
        connection.sendall(response.encode("utf-8"))

    # -- teardown ---------------------------------------------------------

    def close(self) -> None:
        """Tear down the transport and drop the secret. Idempotent."""
        if self._closed:
            return
        self._closed = True
        server, self._server = self._server, None
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=2.0)
        for path in (self._socket_path, self._script_path):
            if path is not None:
                try:
                    path.unlink()
                except OSError:
                    pass
        self._socket_path = None
        self._script_path = None
        self._helper_command = None
        _unregister_secret(self._secret)
        self._secret = ""
        self._username = ""

    def __enter__(self) -> CredentialBroker:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Environment and forced options
# ---------------------------------------------------------------------------

#: Exactly the keys :func:`git_environment` returns.
GIT_ENVIRONMENT_KEYS: frozenset[str] = frozenset(
    {
        "GIT_CONFIG_SYSTEM",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_TERMINAL_PROMPT",
        "GIT_ASKPASS",
        "HOME",
        "PATH",
        "LANG",
    }
)


def git_environment(home_dir: str | os.PathLike[str], *, path: str) -> dict[str, str]:
    """Build the git child's environment from empty.

    ``home_dir`` must be an existing empty directory (an inherited ``HOME``
    would hand the child a user's git config), and ``path`` is the minimal
    ``PATH`` the caller wants the child to search. No ``GIT_TRACE*`` is ever
    set: trace output prints the request headers.
    """
    if not isinstance(path, str) or not path:
        raise WorkspaceGitError("bad_argument", "git_environment needs a non-empty PATH")
    if "\n" in path or "\x00" in path:
        raise WorkspaceGitError("bad_argument", "PATH has a forbidden character")
    home = Path(home_dir)
    if not home.is_dir():
        raise WorkspaceGitError(
            "bad_argument", "git_environment HOME must be an existing directory"
        )
    if any(home.iterdir()):
        raise WorkspaceGitError("bad_argument", "git_environment HOME must be empty")
    return {
        "GIT_CONFIG_SYSTEM": NULL_DEVICE,
        "GIT_CONFIG_GLOBAL": NULL_DEVICE,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": FALSE_BINARY,
        "HOME": str(home),
        "PATH": path,
        "LANG": "C.UTF-8",
    }


#: libcurl gained comma-separated addresses in one ``CURLOPT_RESOLVE`` entry
#: in 7.59.0. Below that, one entry holds one address.
_MULTI_RESOLVE_MINIMUM = (7, 59, 0)
_LIBCURL_VERSION_RE = re.compile(r"libcurl/(\d+)\.(\d+)(?:\.(\d+))?")


def libcurl_supports_multi_resolve(curl_version_text: str) -> bool:
    """Whether this libcurl accepts several addresses in one resolve entry.

    Takes the version TEXT (``git version --build-options`` and ``curl -V``
    both carry a ``libcurl/X.Y.Z`` token) rather than running anything: the
    caller knows which binary it is about to run, and parsing a build-options
    blob for the git version is not the same question. Unparseable text is
    False -- the single-address fallback is always correct, just slower.
    """
    if not isinstance(curl_version_text, str):
        return False
    found = _LIBCURL_VERSION_RE.search(curl_version_text)
    if found is None:
        return False
    major, minor, patch = found.group(1), found.group(2), found.group(3)
    return (int(major), int(minor), int(patch or 0)) >= _MULTI_RESOLVE_MINIMUM


def _resolve_rule_addresses(validated_ips: str | Sequence[str]) -> list[str]:
    """Normalise addresses for a curl resolve entry; IPv6 is bracketed."""
    if isinstance(validated_ips, str):
        candidates: list[str] = [validated_ips]
    else:
        candidates = list(validated_ips)
    if not candidates:
        raise WorkspaceGitError("bad_argument", "no pinned address to resolve to")
    formatted: list[str] = []
    for candidate in candidates:
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            raise WorkspaceGitError(
                "bad_argument", "pinned address is not an ip address"
            ) from None
        # curl's resolve syntax brackets a literal IPv6 address.
        formatted.append(f"[{address.compressed}]" if address.version == 6 else address.compressed)
    return formatted


def forced_git_options(
    host: str,
    validated_ips: str | Sequence[str],
    broker_helper_cmd: str,
) -> list[str]:
    """The ``-c key=value`` arguments every credentialed git child carries.

    The two ``credential.helper`` entries are ordered: the empty one RESETS
    the inherited helper list, and only then is the broker appended. Reversing
    them would leave a system helper in front of the broker.

    ``validated_ips`` may be one address or several (what :func:`pin_address`
    returns). Several are emitted as ONE comma-joined resolve entry, which
    libcurl 7.59.0 and later accept and try in order -- so a dead first
    address does not fail an operation whose host has healthy siblings. A
    caller on an older libcurl checks :func:`libcurl_supports_multi_resolve`
    and passes ONE address per whole operation instead. The host is
    lower-cased: the resolve entry is matched against the URL's host
    case-insensitively by curl, but an upper-cased entry is not canonical and
    a mismatched entry silently does nothing.
    """
    if not _HOSTNAME_RE.match(host or ""):
        raise WorkspaceGitError("bad_argument", "pinned host is not a hostname")
    canonical_host = host.lower()
    pinned = ",".join(_resolve_rule_addresses(validated_ips))
    if not isinstance(broker_helper_cmd, str) or not broker_helper_cmd:
        raise WorkspaceGitError("bad_argument", "broker helper command must be a non-empty str")
    if "\n" in broker_helper_cmd or "\r" in broker_helper_cmd or "\x00" in broker_helper_cmd:
        raise WorkspaceGitError("bad_argument", "broker helper command has a forbidden character")
    settings = (
        f"core.hooksPath={NULL_DEVICE}",
        "core.fsmonitor=false",
        "credential.helper=",
        f"credential.helper={broker_helper_cmd}",
        "credential.useHttpPath=true",
        "protocol.allow=never",
        "protocol.https.allow=always",
        "http.followRedirects=false",
        "submodule.recurse=false",
        "transfer.fsckObjects=true",
        "fetch.fsckObjects=true",
        "receive.fsckObjects=true",
        f"http.curloptResolve={canonical_host}:443:{pinned}",
    )
    options: list[str] = []
    for setting in settings:
        options.extend(("-c", setting))
    return options


# ---------------------------------------------------------------------------
# Address pinning
# ---------------------------------------------------------------------------


def _production_resolver() -> Callable[[str, int], list[str]]:
    from tinyassets.storage.outbound_connections import _default_dns_resolver

    return _default_dns_resolver


def _production_classifier() -> Callable[[str], str]:
    from tinyassets.storage.outbound_connections import _classify_global_address

    return _classify_global_address


def pin_address(
    hostname: str,
    resolver: Callable[[str, int], list[str]] | None = None,
    classifier: Callable[[str], str] | None = None,
    *,
    port: int = 443,
) -> tuple[str, ...]:
    """Resolve ``hostname`` and return every address git may connect to.

    EVERY resolved address must classify as public unicast. A host that
    answers with a mix of public and private addresses is an attack signal,
    not a host with one usable address: the whole resolution is refused rather
    than narrowed to the public subset.

    All of them come back, in the resolver's order, because pinning only the
    first would fail an operation whose host has other healthy addresses.
    The order is the resolver's -- getaddrinfo already applies the platform's
    address-selection rules, and reordering here would discard them.

    The classifier follows the outbound driver's contract: it RETURNS the
    normalised address when the address is globally routable and RAISES
    otherwise. Any exception, and any empty or non-string return, is a
    refusal.
    """
    if not isinstance(hostname, str) or not hostname:
        raise WorkspaceGitError("bad_argument", "pin_address needs a hostname")
    resolve = resolver if resolver is not None else _production_resolver()
    classify = classifier if classifier is not None else _production_classifier()
    try:
        addresses = list(resolve(hostname, port))
    except Exception as exc:  # a resolver failure is a refusal, never a pass
        raise WorkspaceGitError(
            "address_refused", f"could not resolve {hostname}: {type(exc).__name__}"
        ) from None
    if not addresses:
        raise WorkspaceGitError("address_refused", f"{hostname} resolved to no address")
    validated: list[str] = []
    for candidate in addresses:
        try:
            classified = classify(candidate)
        except Exception:
            classified = ""
        if not isinstance(classified, str) or not classified:
            # Never proceed with the public subset: report the split, not the
            # address, which the outbound driver treats as untrusted input.
            raise WorkspaceGitError(
                "address_refused",
                f"{hostname} resolved to {len(addresses)} addresses and at least one "
                "is not globally routable",
            )
        validated.append(classified)
    return tuple(validated)


# ---------------------------------------------------------------------------
# Running git
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GitResult:
    """The bounded, scrubbed outcome of one git child."""

    returncode: int
    stdout_tail: str
    stderr_class: str
    stderr_scrubbed: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


# Conservative, ordered: the first matching class wins. Verification and
# branch-policy refusals are checked before auth because a rejected push often
# also mentions permissions, while "Authentication failed" is unambiguous.
_CLASS_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "verification",
        (
            r"\bfsck\b",
            r"\bindex-pack\b",
            r"did not send all necessary objects",
            r"object of unexpected type",
            r"\bbad object\b",
            r"\bcorrupt(ed)?\b",
            r"hash mismatch",
            r"\bbundle\b.*\b(invalid|corrupt|requires|not a bundle)",
            r"does not look like a v[0-9] bundle file",
        ),
    ),
    (
        "protected",
        (
            r"protected branch",
            r"\bGH006\b",
            r"pre-receive hook declined",
            r"refusing to allow",
            r"branch is read-only",
        ),
    ),
    (
        "non_fast_forward",
        (
            r"non-fast-forward",
            r"fetch first",
            r"updates were rejected because",
            r"cannot lock ref",
        ),
    ),
    (
        "auth",
        (
            r"authentication failed",
            r"could not read username",
            r"could not read password",
            r"terminal prompts disabled",
            r"invalid username or password",
            r"invalid username or token",
            r"permission denied",
            r"\b401\b",
            r"\b403 forbidden\b",
        ),
    ),
    (
        "not_found",
        (
            r"repository not found",
            r"\b404\b",
            r"couldn't find remote ref",
            r"does not appear to be a git repository",
            r"remote branch .* not found",
        ),
    ),
    (
        "transport",
        (
            r"could not resolve host",
            r"failed to connect",
            r"connection (timed out|refused|reset)",
            r"\bssl\b",
            r"\btls\b",
            r"rpc failed",
            r"early eof",
            r"unexpected disconnect",
            r"operation too slow",
            r"\bcurl\b",
            r"unable to access",
        ),
    ),
)

_COMPILED_CLASS_PATTERNS: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = tuple(
    (name, tuple(re.compile(p, re.IGNORECASE) for p in patterns))
    for name, patterns in _CLASS_PATTERNS
)


def classify_stderr(stderr_text: str) -> str:
    """Map scrubbed git stderr to exactly one of :data:`STDERR_CLASSES`.

    Only meaningful for a non-zero exit; a clean run classifies as ``other``.
    """
    text = stderr_text or ""
    for name, patterns in _COMPILED_CLASS_PATTERNS:
        for pattern in patterns:
            if pattern.search(text):
                return name
    return "other"


def _disable_core_dumps() -> None:  # pragma: no cover - runs in the child
    """POSIX preexec: a core dump of a credentialed git would hold the token."""
    import resource

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _tail_text(raw: object) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        data = raw.encode("utf-8", "replace")
    elif isinstance(raw, (bytes, bytearray)):
        data = bytes(raw)
    else:
        data = str(raw).encode("utf-8", "replace")
    if len(data) > _MAX_CAPTURED_BYTES:
        data = data[-_MAX_CAPTURED_BYTES:]
    return data.decode("utf-8", "replace")


def run_git(
    argv: Sequence[str],
    *,
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    options: Sequence[str] = (),
    timeout_s: float,
    launcher: Callable[..., object] = subprocess.run,
    git_binary: str = "git",
    extra_secrets: Sequence[str] = (),
    preexec_fn: Callable[[], None] | None = None,
) -> GitResult:
    """Run ``git <options...> <argv...>`` and return a bounded, scrubbed result.

    The child never inherits this process's environment, never gets a stdin,
    and on POSIX cannot write a core dump and starts in a NEW SESSION -- so it
    leads its own process group and :func:`kill_git` can take down anything it
    spawned, not just the git process itself. Output is truncated to the last
    64 KiB of each stream and scrubbed before it is returned or classified.

    ``preexec_fn`` is injectable so a test can observe that the child-side
    setup runs; the default on POSIX is :func:`_disable_core_dumps`.
    """
    if not isinstance(argv, Sequence) or isinstance(argv, (str, bytes)) or not argv:
        raise WorkspaceGitError("bad_argument", "run_git needs a non-empty argv sequence")
    for item in (*argv, *options):
        if not isinstance(item, str):
            raise WorkspaceGitError("bad_argument", "git arguments must all be str")
    if not Path(cwd).is_dir():
        raise WorkspaceGitError("bad_argument", "run_git cwd must be an existing directory")
    for key, value in env.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise WorkspaceGitError("bad_argument", "the git environment must be str to str")
        if key.startswith("GIT_TRACE"):
            raise WorkspaceGitError("bad_argument", "GIT_TRACE* would print the request headers")
    if timeout_s is None or float(timeout_s) <= 0:
        raise WorkspaceGitError("bad_argument", "run_git needs a positive timeout")

    command = [git_binary, *options, *argv]
    kwargs: dict[str, object] = {
        "cwd": str(cwd),
        "env": dict(env),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "timeout": float(timeout_s),
        "check": False,
        "shell": False,
    }
    child_setup = preexec_fn if preexec_fn is not None else (
        None if _IS_WINDOWS else _disable_core_dumps
    )
    if child_setup is not None:
        kwargs["preexec_fn"] = child_setup
    if not _IS_WINDOWS:
        # Its own session, so kill_git can signal the whole process group; a
        # git that spawned a helper must not leave the helper behind.
        kwargs["start_new_session"] = True
    try:
        completed = launcher(command, **kwargs)
    except subprocess.TimeoutExpired:
        raise WorkspaceGitError("timeout", f"git {argv[0]} exceeded {timeout_s}s") from None
    except OSError as exc:
        raise WorkspaceGitError("transport", f"git could not be started: {exc}") from None

    stdout_tail = scrub_text(_tail_text(getattr(completed, "stdout", b"")), extra_secrets)
    stderr_scrubbed = scrub_text(_tail_text(getattr(completed, "stderr", b"")), extra_secrets)
    return GitResult(
        returncode=int(getattr(completed, "returncode", 1)),
        stdout_tail=stdout_tail,
        stderr_class=classify_stderr(stderr_scrubbed),
        stderr_scrubbed=stderr_scrubbed,
    )


def kill_git(proc: object, *, timeout_s: float = 5.0) -> int:
    """SIGKILL a git started by :func:`run_git` and everything it spawned.

    ``run_git`` puts the child in its own session on POSIX, so signalling the
    process GROUP reaches a helper git double-forked away -- killing only the
    tracked pid would leave it running. Raises ``timeout`` if the tracked
    process has still not exited: a caller must never be told a process is
    gone while it holds a lease or a credential.
    """
    pid = getattr(proc, "pid", None)
    if pid is None or not hasattr(proc, "wait"):
        raise WorkspaceGitError("bad_argument", "kill_git needs a started process")
    if not _IS_WINDOWS:
        try:
            os.killpg(os.getpgid(pid), _KILL_SIGNAL)
        except (ProcessLookupError, PermissionError):
            # Already reaped, or never had its own group: fall back to the pid.
            try:
                proc.kill()
            except (ProcessLookupError, OSError):
                pass
    else:  # pragma: no cover - production is Linux; no process groups here
        try:
            proc.kill()
        except OSError:
            pass
    try:
        return int(proc.wait(timeout=float(timeout_s)))
    except subprocess.TimeoutExpired:
        raise WorkspaceGitError(
            "timeout", f"git did not exit within {timeout_s}s of SIGKILL"
        ) from None


def _require_ok(result: GitResult, what: str, fallback: str = "other") -> GitResult:
    if result.ok:
        return result
    code = result.stderr_class
    if code == "other":
        code = fallback
    raise WorkspaceGitError(code, f"{what} failed ({result.returncode}): {result.stderr_scrubbed}")


# ---------------------------------------------------------------------------
# Bundle helpers -- all credential-free
# ---------------------------------------------------------------------------


def _require_sha(commit_sha: str) -> str:
    if not isinstance(commit_sha, str) or not _SHA1_RE.match(commit_sha):
        raise WorkspaceGitError("bad_argument", "commit sha must be 40 lowercase hex characters")
    return commit_sha


def _require_ref(ref_name: str, label: str) -> str:
    if not isinstance(ref_name, str) or not _REF_COMPONENT_RE.match(ref_name):
        raise WorkspaceGitError("bad_argument", f"{label} is not a valid ref name")
    if ".." in ref_name or ref_name.endswith((".lock", "/", ".")) or "//" in ref_name:
        raise WorkspaceGitError("bad_argument", f"{label} is not a valid ref name")
    return ref_name


# git 2.43 and 2.53 both say "Repository lacks these prerequisite commits" on
# stderr and fail; older and newer wordings ("requires these refs") are matched
# too, so a git that warns instead of failing is still caught.
_PREREQUISITE_RE = re.compile(r"(?i)(prerequisite|requires th(?:is|ese) ref|lacks these)")


def _verify_prerequisite_free(
    target: Path,
    *,
    scratch_dir: str | os.PathLike[str],
    env: Mapping[str, str],
    timeout_s: float,
    launcher: Callable[..., object],
    git_binary: str,
) -> list[str]:
    """Verify a bundle in a FRESH EMPTY bare repo; return the refs it carries.

    Empty is the whole point: a bundle that needs objects it does not carry
    cannot verify against a repository that has none, so verifying here proves
    the bundle is self-contained. A thin or shallow bundle would import
    partially somewhere else and look fine.
    """
    scratch = Path(scratch_dir)
    if not scratch.is_dir():
        raise WorkspaceGitError(
            "bad_argument", "bundle verification scratch_dir must be a directory"
        )
    if any(scratch.iterdir()):
        raise WorkspaceGitError("bad_argument", "bundle verification scratch_dir must be empty")
    bare = scratch / "verify.git"
    bare.mkdir()

    def _run(argv: list[str]) -> GitResult:
        return run_git(
            argv,
            cwd=bare,
            env=env,
            timeout_s=timeout_s,
            launcher=launcher,
            git_binary=git_binary,
        )

    _require_ok(_run(["init", "--bare", "--quiet", "."]), "init bare", "verification")
    verified = _run(["bundle", "verify", str(target)])
    combined = f"{verified.stdout_tail}\n{verified.stderr_scrubbed}"
    if _PREREQUISITE_RE.search(combined):
        raise WorkspaceGitError(
            "verification",
            "bundle is not prerequisite-free: it needs objects it does not carry",
        )
    _require_ok(verified, "bundle verify", "verification")
    # ``bundle verify`` prints prose; ``list-heads`` prints "<sha> <ref>" and is
    # what the ref list is read from.
    heads = _require_ok(
        _run(["bundle", "list-heads", str(target)]), "bundle list-heads", "verification"
    )
    refs: list[str] = []
    for line in heads.stdout_tail.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            refs.append(parts[1].strip())
    if not refs:
        raise WorkspaceGitError("verification", "bundle carries no ref")
    return refs


def create_bundle(
    repo_dir: str | os.PathLike[str],
    commit_sha: str,
    bundle_path: str | os.PathLike[str],
    *,
    ref_name: str = "refs/tiny/export",
    env: Mapping[str, str],
    scratch_dir: str | os.PathLike[str],
    timeout_s: float = 120.0,
    launcher: Callable[..., object] = subprocess.run,
    git_binary: str = "git",
) -> Path:
    """Bundle exactly one commit from ``repo_dir`` into ``bundle_path``.

    Runs with hooks disabled and object replacement off, so a replace ref or a
    hook planted in the repository cannot change what is exported, and then
    verifies its OWN output in a fresh empty bare repo (``scratch_dir``): a
    bundle that carries prerequisites is refused and deleted here rather than
    failing later on the far side of the boundary, where the failure is a
    half-populated workspace.
    """
    _require_sha(commit_sha)
    _require_ref(ref_name, "bundle ref")
    repo = Path(repo_dir)
    if not repo.is_dir():
        raise WorkspaceGitError("bad_argument", "create_bundle repo_dir must be a directory")
    target = Path(bundle_path)
    if target.exists() or target.is_symlink():
        raise WorkspaceGitError("bad_argument", "create_bundle refuses to overwrite bundle_path")
    if not target.parent.is_dir():
        raise WorkspaceGitError("bad_argument", "create_bundle bundle_path has no parent directory")

    common = ["-c", f"core.hooksPath={NULL_DEVICE}", "--no-replace-objects"]

    def _run(argv: list[str]) -> GitResult:
        return run_git(
            argv,
            cwd=repo,
            env=env,
            options=common,
            timeout_s=timeout_s,
            launcher=launcher,
            git_binary=git_binary,
        )

    _require_ok(_run(["update-ref", ref_name, commit_sha]), "update-ref")
    try:
        _require_ok(_run(["bundle", "create", str(target), ref_name]), "bundle create")
    finally:
        # The synthetic ref is temporary whatever happened above.
        _run(["update-ref", "-d", ref_name])
    if not target.is_file():
        raise WorkspaceGitError("verification", "bundle create produced no file")
    try:
        _verify_prerequisite_free(
            target,
            scratch_dir=scratch_dir,
            env=env,
            timeout_s=timeout_s,
            launcher=launcher,
            git_binary=git_binary,
        )
    except WorkspaceGitError:
        # An unverifiable bundle must not survive where a caller could pick it
        # up; the exception is the report, the unlink is the cleanup.
        try:
            target.unlink()
        except OSError:
            pass
        raise
    return target


def verify_bundle(
    bundle_path: str | os.PathLike[str],
    *,
    max_bytes: int,
    scratch_dir: str | os.PathLike[str],
    env: Mapping[str, str],
    timeout_s: float = 120.0,
    launcher: Callable[..., object] = subprocess.run,
    git_binary: str = "git",
) -> list[str]:
    """Verify a bundle credential-free in a fresh bare repo; return its refs.

    ``scratch_dir`` must be an existing empty directory: the bare repository is
    created inside it so no repository the caller cares about is ever the cwd
    of a verification that reads attacker-supplied pack data.
    """
    target = Path(bundle_path)
    try:
        info = os.lstat(target)
    except OSError:
        raise WorkspaceGitError("verification", "bundle path does not exist") from None
    if not stat.S_ISREG(info.st_mode):
        raise WorkspaceGitError("verification", "bundle path is not a regular file")
    if int(max_bytes) <= 0:
        raise WorkspaceGitError("bad_argument", "verify_bundle needs a positive max_bytes")
    if info.st_size > int(max_bytes):
        raise WorkspaceGitError("verification", "bundle exceeds the permitted size")

    return _verify_prerequisite_free(
        target,
        scratch_dir=scratch_dir,
        env=env,
        timeout_s=timeout_s,
        launcher=launcher,
        git_binary=git_binary,
    )


def unbundle_into_fresh_repo(
    bundle_path: str | os.PathLike[str],
    dest_dir: str | os.PathLike[str],
    *,
    ref_name: str,
    env: Mapping[str, str],
    timeout_s: float = 300.0,
    launcher: Callable[..., object] = subprocess.run,
    git_binary: str = "git",
) -> str:
    """Populate an empty directory from a bundle; return the commit sha.

    The result has no remote and no reference to the bundle's path, which is
    the point: the workspace's ``.git`` must not tell user code where the
    host keeps anything, and must not carry a remote a later git could push to.
    """
    _require_ref(ref_name, "fetch ref")
    source = Path(bundle_path)
    if not source.is_file():
        raise WorkspaceGitError("verification", "bundle path is not a regular file")
    dest = Path(dest_dir)
    if dest.exists():
        if not dest.is_dir():
            raise WorkspaceGitError("bad_argument", "dest_dir is not a directory")
        if any(dest.iterdir()):
            raise WorkspaceGitError("bad_argument", "dest_dir must be empty")
    else:
        dest.mkdir(parents=True)

    def _run(argv: list[str], options: Sequence[str] = ()) -> GitResult:
        return run_git(
            argv,
            cwd=dest,
            env=env,
            options=options,
            timeout_s=timeout_s,
            launcher=launcher,
            git_binary=git_binary,
        )

    _require_ok(_run(["init", "--quiet", "."]), "init", "verification")
    _require_ok(
        _run(
            ["fetch", "--quiet", str(source), f"{ref_name}:{ref_name}"],
            options=["-c", "transfer.fsckObjects=true", "-c", "fetch.fsckObjects=true"],
        ),
        "fetch from bundle",
        "verification",
    )
    _require_ok(_run(["fsck", "--strict", "--no-dangling"]), "fsck", "verification")
    revision = _require_ok(_run(["rev-parse", ref_name]), "rev-parse", "verification")
    sha = revision.stdout_tail.strip()
    _require_sha(sha)

    remote = _run(["config", "--get", "remote.origin.url"])
    if remote.stdout_tail.strip():
        raise WorkspaceGitError("verification", "the populated repository carries a remote")
    config_path = dest / ".git" / "config"
    if config_path.is_file():
        config_text = config_path.read_text(encoding="utf-8", errors="replace")
        resolved = source.resolve()
        for spelling in {str(source), str(resolved), resolved.as_posix()}:
            if spelling and spelling in config_text:
                raise WorkspaceGitError(
                    "verification", "the populated repository records a host path"
                )
    return sha


def populate_workspace_from_bundle(
    bundle_path: str | os.PathLike[str],
    dest_dir: str | os.PathLike[str],
    ref_name: str,
    checkout_ref: str,
    *,
    env: Mapping[str, str],
    timeout_s: float = 300.0,
    launcher: Callable[..., object] = subprocess.run,
    git_binary: str = "git",
) -> str:
    """Unbundle into a fresh repo and check the commit out on a local branch."""
    _require_ref(checkout_ref, "checkout ref")
    sha = unbundle_into_fresh_repo(
        bundle_path,
        dest_dir,
        ref_name=ref_name,
        env=env,
        timeout_s=timeout_s,
        launcher=launcher,
        git_binary=git_binary,
    )
    result = run_git(
        ["checkout", "--quiet", "-B", checkout_ref, sha],
        cwd=dest_dir,
        env=env,
        timeout_s=timeout_s,
        launcher=launcher,
        git_binary=git_binary,
    )
    _require_ok(result, "checkout", "verification")
    return sha
