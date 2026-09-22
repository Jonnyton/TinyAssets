"""Record-only platform runtime provenance observation.

OpenSpec change `cloud-only-runtime-admission`, task 4 (record-only slice).

**This module enforces nothing.** It resolves one bounded observation — does the
DigitalOcean droplet metadata service answer from inside this process's machine,
and does the id it reports equal the instance id the deploy recorded before this
process started — and it hands back a typed verdict. No caller in this slice
branches on that verdict: claim admission, runtime registration, serving startup
and provider authority are all unchanged. Flipping refusal sites onto this
resolver is tasks 6-8 and requires its own live positive observation first.

What the verdict is, stated honestly
------------------------------------
An **accidental-start backstop**, never attestation. The metadata service is
unauthenticated and unsigned (`docs.digitalocean.com/reference/api/metadata/`),
readable by any process inside the droplet, and forgeable by a local root
operator who adds a route or a listener. The deploy-recorded expected id is
copyable too. What the pair does establish is that a checkout, an env file, a
hostname, a container name or a compose label — all of which travel with a copy
of this repo — do not by themselves resolve to CLOUD. Absence, malformation,
timeout, redirect, oversize body and mismatch all resolve to not-cloud.

Design constraints this module is required to hold (design.md § Evidence
primitive, § Process lifetime and deployment ordering):

* One resolver function. The probe is a dedicated internal client on a literal
  link-local address with no redirects, no proxy inheritance, a sub-second
  timeout and no caller-supplied input. It never routes through the outbound
  HTTP/effect surface, so the SSRF driver's link-local classification stays
  exactly as it is, and it is not reachable as a user capability.
* Expected identity is read through the canonical CWD-independent data-root
  resolver (`tinyassets.storage.data_dir`), never from an environment variable,
  a hostname, a UUID or a container label.
* Comparison is a strict integer comparison of two bare numeric ids.
* The process-level observation is resolved at most once and is then immutable.
  A refusal never silently upgrades; a new process resolves independently.
* No database transaction is opened or held here, so no network I/O can ever run
  under the SQLite write lock. Callers that later gate a claim CAS must read the
  already-resolved process-owned value inside the transaction.
* There is no environment-variable bypass and no tests-only switch. Tests inject
  a reader/resolver, or construct their own observation object.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

# --- fixed literals (nothing here is caller-supplied) ---------------------

#: The one address this module reads. A literal, never composed from input.
METADATA_URL = "http://169.254.169.254/metadata/v1/id"

#: Bounded request/response budget. Sub-second: this runs once per process at
#: startup, and a hung link-local read must never become a startup stall.
METADATA_TIMEOUT_SECONDS = 0.5

#: A droplet id is a short integer. A longer body is not the fact we came for
#: and is refused outright rather than parsed as a prefix — a truncated prefix
#: of an overlong body can itself be a well-formed id.
MAX_METADATA_BODY_BYTES = 64

#: The deploy writes a small typed file. Anything larger is not it.
MAX_EXPECTED_STATE_BYTES = 4096

#: Dedicated typed state, prepared by the deploy BEFORE the candidate starts,
#: in the existing data root. Deliberately not a field in `release-state.json`:
#: that receipt is published only after the candidate is already healthy, and it
#: is rewritten whole on every deploy, so a field inside it is both absent when
#: first needed and erasable by any receipt rewrite (see design.md).
EXPECTED_INSTANCE_FILENAME = "platform-expected-instance.json"
EXPECTED_INSTANCE_SCHEMA = "platform_expected_instance"
EXPECTED_INSTANCE_VERSION = 1

CLOUD = "cloud"
NOT_CLOUD = "not_cloud"

_INSTANCE_ID_RE = re.compile(r"^[0-9]{1,20}$")


# --- typed results --------------------------------------------------------


@dataclass(frozen=True)
class MetadataRead:
    """One bounded metadata observation.

    `instance_id` is kept only long enough to compare; it is never carried into
    `RuntimeProvenance` and never logged.
    """

    instance_id: str | None
    reason: str

    @property
    def ok(self) -> bool:
        return self.instance_id is not None


@dataclass(frozen=True)
class ExpectedInstanceRead:
    """The deploy-recorded expected instance identity."""

    instance_id: str | None
    reason: str

    @property
    def ok(self) -> bool:
        return self.instance_id is not None


@dataclass(frozen=True)
class RuntimeProvenance:
    """A sanitized verdict. Carries no identifier and no secret.

    Only a verdict, a stable snake_case reason token and two booleans, so a log
    line or a ledger row built from this cannot leak an instance id.
    """

    verdict: str
    reason: str
    metadata_reachable: bool
    expected_identity_prepared: bool
    #: Record-only slice: this is always False. Tasks 6-8 flip refusal sites.
    enforced: bool = False

    @property
    def is_cloud(self) -> bool:
        return self.verdict == CLOUD


class _UrlOpener(Protocol):  # pragma: no cover - structural type only
    def open(self, request: object, timeout: float): ...


# --- the dedicated internal metadata client -------------------------------


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Never follow a 3xx away from the link-local address.

    `build_opener` installs the default redirect handler unless a replacement is
    passed, so a redirect would otherwise report whatever answered elsewhere as
    this machine's own identity.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


def build_metadata_opener() -> urllib.request.OpenerDirector:
    """Build the dedicated opener: no redirects, no proxy inheritance.

    An empty `ProxyHandler` is load-bearing. The metadata service is link-local
    and must be read directly or not at all; inheriting `http_proxy` would send
    the probe to a proxy and report the proxy's answer as local identity.
    """
    return urllib.request.build_opener(
        _RefuseRedirects(),
        urllib.request.ProxyHandler({}),
    )


def read_metadata_instance_id(
    *,
    opener: _UrlOpener | None = None,
    timeout: float = METADATA_TIMEOUT_SECONDS,
) -> MetadataRead:
    """Read the droplet id once, bounded, with no redirects and no proxy.

    Every failure mode is a typed refusal reason; nothing raises.
    """
    active = opener if opener is not None else build_metadata_opener()
    request = urllib.request.Request(METADATA_URL, method="GET")
    try:
        with active.open(request, timeout=timeout) as response:
            # One byte past the ceiling, so a body AT the ceiling is known
            # complete and a longer one is detectable.
            body = response.read(MAX_METADATA_BODY_BYTES + 1)
    except urllib.error.HTTPError as exc:
        code = getattr(exc, "code", 0) or 0
        if 300 <= int(code) < 400:
            # The refusing redirect handler surfaces here. Something answered
            # and tried to send us elsewhere; that is not a local identity.
            return MetadataRead(None, "metadata_redirect_refused")
        return MetadataRead(None, "metadata_http_error")
    except urllib.error.URLError as exc:
        # URLError wraps the transport fault; a timeout must stay distinguishable
        # from "nothing is listening", because they mean different things on a
        # droplet (slow/degraded metadata service vs not a droplet at all).
        if isinstance(exc.reason, TimeoutError):
            return MetadataRead(None, "metadata_timeout")
        return MetadataRead(None, "metadata_unreachable")
    except TimeoutError:
        # socket.timeout is TimeoutError on 3.11; a read that stalls past the
        # sub-second budget lands here.
        return MetadataRead(None, "metadata_timeout")
    except OSError:
        return MetadataRead(None, "metadata_unreachable")
    except Exception:  # noqa: BLE001 - an unknown probe fault is not cloud proof
        return MetadataRead(None, "metadata_probe_failed")

    if not isinstance(body, (bytes, bytearray)):
        return MetadataRead(None, "metadata_malformed_body")
    if len(body) > MAX_METADATA_BODY_BYTES:
        return MetadataRead(None, "metadata_body_too_large")
    observed = bytes(body).decode("utf-8", "replace").strip()
    if not observed:
        return MetadataRead(None, "metadata_empty_id")
    if not _INSTANCE_ID_RE.match(observed):
        return MetadataRead(None, "metadata_malformed_instance_id")
    return MetadataRead(observed, "reachable")


# --- deploy-recorded expected identity ------------------------------------


def expected_instance_state_path(data_root: Path | None = None) -> Path:
    """Locate the expected-instance state inside the canonical data root.

    `tinyassets.storage.data_dir()` is the single CWD-independent resolver; this
    never re-implements its precedence and never reads an env var of its own.
    """
    if data_root is not None:
        return Path(data_root) / EXPECTED_INSTANCE_FILENAME
    from tinyassets.storage import data_dir

    return data_dir() / EXPECTED_INSTANCE_FILENAME


def read_expected_instance_id(
    *, data_root: Path | None = None
) -> ExpectedInstanceRead:
    """Read and validate the deploy-recorded expected instance id."""
    try:
        path = expected_instance_state_path(data_root)
    except Exception:  # noqa: BLE001 - an unresolvable root is not cloud proof
        return ExpectedInstanceRead(None, "expected_identity_root_unresolved")
    try:
        if not path.is_file():
            return ExpectedInstanceRead(None, "expected_identity_missing")
        if path.stat().st_size > MAX_EXPECTED_STATE_BYTES:
            return ExpectedInstanceRead(None, "expected_identity_state_too_large")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - unreadable/invalid state refuses
        return ExpectedInstanceRead(None, "expected_identity_state_unreadable")
    if not isinstance(payload, dict):
        return ExpectedInstanceRead(None, "expected_identity_malformed")
    if payload.get("schema") != EXPECTED_INSTANCE_SCHEMA:
        return ExpectedInstanceRead(None, "expected_identity_schema_unknown")
    if payload.get("version") != EXPECTED_INSTANCE_VERSION:
        return ExpectedInstanceRead(None, "expected_identity_version_unsupported")
    recorded = payload.get("expected_instance_id")
    if not isinstance(recorded, str) or not _INSTANCE_ID_RE.match(recorded.strip()):
        return ExpectedInstanceRead(None, "expected_identity_malformed")
    return ExpectedInstanceRead(recorded.strip(), "prepared")


# --- the one resolver -----------------------------------------------------


def resolve_platform_runtime_provenance(
    *,
    metadata_reader: Callable[[], MetadataRead] | None = None,
    expected_reader: Callable[[], ExpectedInstanceRead] | None = None,
) -> RuntimeProvenance:
    """Resolve cloud provenance = metadata reachable AND identity matching.

    Fail-closed in every branch: absent, malformed, timed-out, redirected,
    oversize, unprepared and mismatched all resolve to `NOT_CLOUD`. There is no
    host fallback and no environment-variable override.

    Both readers are injectable, which is how tests drive this — never by
    setting an env var, and never by a tests-only code path.
    """
    read_metadata = metadata_reader or read_metadata_instance_id
    read_expected = expected_reader or read_expected_instance_id

    observed = read_metadata()
    expected = read_expected()

    if not observed.ok:
        return RuntimeProvenance(
            verdict=NOT_CLOUD,
            reason=observed.reason,
            metadata_reachable=False,
            expected_identity_prepared=expected.ok,
        )
    if not expected.ok:
        return RuntimeProvenance(
            verdict=NOT_CLOUD,
            reason=expected.reason,
            metadata_reachable=True,
            expected_identity_prepared=False,
        )
    # Strict integer comparison of two validated bare numeric ids: "0123" and
    # "123" are the same droplet, and no prefix/substring match is possible.
    if int(observed.instance_id or "") != int(expected.instance_id or ""):
        return RuntimeProvenance(
            verdict=NOT_CLOUD,
            reason="instance_mismatch",
            metadata_reachable=True,
            expected_identity_prepared=True,
        )
    return RuntimeProvenance(
        verdict=CLOUD,
        reason="instance_match",
        metadata_reachable=True,
        expected_identity_prepared=True,
    )


# --- immutable once-per-process observation -------------------------------


class ProcessProvenanceObservation:
    """Resolve once per process, then hand back the same immutable verdict.

    A refused observation is never re-resolved, so a cached refusal cannot
    silently upgrade itself if metadata later starts answering. An explicitly
    restarted process constructs a new object and resolves anew — which is what
    makes "restart to recover" honest rather than automatic.

    Holds no database handle and opens no transaction, so the one bounded
    network read can never happen under a write lock.
    """

    def __init__(
        self,
        resolver: Callable[[], RuntimeProvenance] = resolve_platform_runtime_provenance,
    ) -> None:
        self._resolver = resolver
        self._lock = threading.Lock()
        self._result: RuntimeProvenance | None = None

    @property
    def resolved(self) -> bool:
        return self._result is not None

    def observe(self) -> RuntimeProvenance:
        with self._lock:
            if self._result is None:
                self._result = self._resolver()
            return self._result


_PROCESS_OBSERVATION = ProcessProvenanceObservation()


def observe_platform_runtime_provenance() -> RuntimeProvenance:
    """Process-wide entry point. Record-only: no caller branches on this."""
    return _PROCESS_OBSERVATION.observe()


def sanitized_observation_fields(provenance: RuntimeProvenance) -> dict[str, object]:
    """The only shape that may be logged or recorded.

    Verdict, reason token and two booleans. No instance id, no expected id, no
    address, no secret, and `enforced` stated explicitly so a record-only line
    can never be read as an enforcement claim.
    """
    return {
        "verdict": provenance.verdict,
        "reason": provenance.reason,
        "metadata_reachable": provenance.metadata_reachable,
        "expected_identity_prepared": provenance.expected_identity_prepared,
        "enforced": provenance.enforced,
        "mode": "observation_only",
    }
