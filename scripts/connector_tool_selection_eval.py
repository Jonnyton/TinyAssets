"""Connector tool-selection accuracy — dataset loader, scorer, and baseline gate.

Instrument for the change ``openspec/changes/connector-tool-selection-accuracy``,
which carries task 6.3 of ``reconcile-universe-personification-relay`` (itself the
residual of retired task 2.9).

**What this measures.** Whether a host chatbot, reading the shipped server
``instructions`` + ``control_station`` prompt, picks the right handle out of the
canonical seven. ``mcp_public_canary.py --assert-handles`` proves the handles are
*advertised*; nothing proved they are *chosen*. A chatbot that answers "talk to my
universe" with ``read_graph`` does not error — it returns a plausible wrong answer
and the founder never reaches their universe.

**What this does NOT do.** It does not run the measurement. Handle choice is a
property of the host chatbot, so observations come from a real browser-rendered
session through the live connector, per the ``ui-test`` skill (AGENTS.md §Quality
Gates: direct MCP calls are supporting evidence, not user-surface proof). This
module scores a *recorded* run and gates it against a *recorded* baseline.

Everything here fails loudly. A malformed dataset, a partial run, a
non-rendered source, an unusable threshold, or a cross-version comparison raises
rather than producing a number that looks like evidence:

  * a partial run cannot be scored, so the gate cannot be passed by omitting the
    prompts that failed;
  * the permitted regression lives on the baseline, not in the call, so a failing
    run cannot be rescued by loosening the threshold at the call site — and it
    must be a finite rate in [0, 1], because ``drop > NaN`` is False for every
    drop and would turn the gate into an unconditional pass;
  * the opening-turn rate is reported separately from top-1, because a regression
    confined to first-contact turns is invisible in a pooled average — and
    first-contact is exactly the flow that depends on ``converse`` being picked.

**What ``source`` is, precisely.** A *trusted transcription* — not proof of
provenance. The harness refuses an honestly labelled non-rendered source, and
that is the whole of what it enforces: it cannot distinguish a transcribed
rendered session from a synthetic file labelled ``claude.ai``. Provenance is
therefore established by *review of the evidence*, not by the label. A recorded
run may carry an ``evidence`` pointer (a ``ui-test`` log anchor, trace, or
screenshot path); the harness carries and reports it, and says plainly when it is
absent. Requiring that pointer on a recorded baseline is a review obligation
(task 3.1), not a check this module performs.

Usage
-----
    python scripts/connector_tool_selection_eval.py \\
        --dataset tests/data/connector_tool_selection_v1.jsonl \\
        --run output/tool_selection_run.json \\
        --baseline docs/ops/tool-selection-baseline.json

``--run`` is a JSON object of ``{"source": ..., "observed_on": ...,
"evidence": ..., "observations": {prompt: observed_handle}}`` transcribed from
the rendered session (``evidence`` optional). Exit 0 = gate passed, 1 = gate
failed, 2 = the input was unusable — every unusable shape, so exit 1 always means
a valid run that failed a valid gate.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

#: The canonical advertised handle set. Kept in sync with
#: ``scripts/mcp_public_canary.py::CANONICAL_HANDLES`` and
#: ``openspec/specs/live-mcp-connector-surface/spec.md``.
CANONICAL_HANDLES = frozenset({
    "read_graph",
    "write_graph",
    "run_graph",
    "read_page",
    "write_page",
    "converse",
    "get_status",
})

#: Sources that count as a measurement. Handle choice can only be observed where
#: a host chatbot actually chooses, so a direct MCP call is not a measurement.
#: This refuses an *honestly labelled* non-rendered source; it does not and
#: cannot verify that an accepted label was truthful — see the module docstring.
RENDERED_SOURCES = frozenset({"claude.ai", "chatgpt"})

_VERSION_RE = re.compile(r"_(v\d+)\.jsonl$")


class DatasetError(ValueError):
    """The measurement instrument is malformed and must not be scored."""


class MeasurementError(ValueError):
    """A run or comparison is unusable as evidence."""


def _as_rate(value: object, field_name: str) -> float:
    """Coerce and range-check a rate, refusing anything a comparison cannot use.

    NaN is the sharp case: ``baseline - NaN`` is NaN and ``NaN > tolerance`` is
    False, so a single non-finite value converts a failing gate into
    ``GATE PASS`` without touching the comparison logic at all. An out-of-range
    rate is the blunt version — it shifts every drop by an arbitrary amount.
    """
    try:
        rate = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise MeasurementError(
            f"{field_name} {value!r} is not a number — an unreadable rate cannot "
            "gate anything"
        ) from exc
    if not math.isfinite(rate):
        raise MeasurementError(
            f"{field_name} is {rate} — a non-finite rate makes every comparison "
            "against it vacuously true, which reads as a passing gate"
        )
    if not 0.0 <= rate <= 1.0:
        raise MeasurementError(
            f"{field_name} is {rate}, outside the [0.0, 1.0] range a rate can occupy"
        )
    return rate


def _as_tolerance(value: object) -> float:
    """Coerce and range-check the permitted regression. Same hole, same refusal."""
    try:
        tolerance = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise MeasurementError(
            f"permitted_regression {value!r} is not a number — an unreadable "
            "threshold cannot gate anything"
        ) from exc
    if not math.isfinite(tolerance):
        raise MeasurementError(
            f"permitted_regression is {tolerance} — `drop > tolerance` is False for "
            "every drop, so every regression would pass the gate"
        )
    if not 0.0 <= tolerance <= 1.0:
        raise MeasurementError(
            f"permitted_regression is {tolerance}: a negative tolerance is "
            "meaningless, and one wider than the rate range is not a loose gate "
            "but no gate"
        )
    return tolerance


@dataclass(frozen=True)
class DatasetEntry:
    prompt: str
    expected_handle: str
    opening: bool = False
    note: str = ""


@dataclass(frozen=True)
class Dataset:
    version: str
    path: Path
    entries: tuple[DatasetEntry, ...]

    @property
    def prompts(self) -> tuple[str, ...]:
        return tuple(entry.prompt for entry in self.entries)


@dataclass(frozen=True)
class Measurement:
    dataset_version: str
    surface: str
    observed_on: str
    top1_rate: float
    opening_converse_rate: float
    total: int
    correct: int
    non_canonical_observed: tuple[str, ...] = ()
    misses: tuple[tuple[str, str, str], ...] = ()  # (prompt, expected, observed)
    #: Optional reviewable pointer to the rendered session this was transcribed
    #: from (a ``ui-test`` log anchor, trace, or screenshot path). Carried, not
    #: verified — see the module docstring on trusted transcription.
    evidence: str = ""

    def __post_init__(self) -> None:
        # Validated here rather than only in `score_run`, so a hand-built
        # Measurement cannot carry a NaN rate into the gate either.
        object.__setattr__(self, "top1_rate", _as_rate(self.top1_rate, "top1_rate"))
        object.__setattr__(
            self,
            "opening_converse_rate",
            _as_rate(self.opening_converse_rate, "opening_converse_rate"),
        )


@dataclass(frozen=True)
class Baseline:
    dataset_version: str
    surface: str
    recorded_on: str
    top1_rate: float
    opening_converse_rate: float
    #: Maximum tolerated drop, in rate units (0.05 == 5 percentage points).
    #: Defaults to zero — no regression — until the connector-surface owner
    #: records a tolerance. Recorded here rather than passed per-invocation so a
    #: failing run cannot be rescued by loosening it at the call site.
    permitted_regression: float = 0.0
    #: Reviewable pointer to the rendered session this baseline was transcribed
    #: from. Optional in the type, required by the recording task (3.1).
    evidence: str = ""

    def __post_init__(self) -> None:
        # Construction is the single validation point, so `_load_baseline` gets
        # the same refusals for free: a non-numeric, non-finite, or out-of-range
        # value never reaches `compare_to_baseline` to be silently tolerated.
        object.__setattr__(self, "top1_rate", _as_rate(self.top1_rate, "top1_rate"))
        object.__setattr__(
            self,
            "opening_converse_rate",
            _as_rate(self.opening_converse_rate, "opening_converse_rate"),
        )
        object.__setattr__(
            self, "permitted_regression", _as_tolerance(self.permitted_regression)
        )


@dataclass(frozen=True)
class GateVerdict:
    passed: bool
    reason: str = ""
    details: dict = field(default_factory=dict)


def load_dataset(path: Path | str) -> Dataset:
    """Load and validate a labelled prompt->handle dataset.

    Every integrity rule raises: a silently-accepted malformed instrument
    produces a number that looks like evidence but is not.
    """
    path = Path(path)
    match = _VERSION_RE.search(path.name)
    if not match:
        raise DatasetError(
            f"dataset {path.name!r} carries no version: the filename must end "
            "in _v<N>.jsonl so a baseline records what it was measured against"
        )
    version = match.group(1)

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DatasetError(f"dataset {path} could not be read: {exc}") from exc

    entries: list[DatasetEntry] = []
    seen: set[str] = set()
    for lineno, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetError(
                f"{path.name} line {lineno}: not valid JSON ({exc.msg}) — a torn "
                "line is a torn instrument, not a row to skip"
            ) from exc
        if not isinstance(row, dict):
            raise DatasetError(f"{path.name} line {lineno}: row is not an object")

        prompt = str(row.get("prompt") or "").strip()
        handle = str(row.get("expected_handle") or "").strip()
        if not prompt:
            raise DatasetError(f"{path.name} line {lineno}: empty prompt")
        if handle not in CANONICAL_HANDLES:
            raise DatasetError(
                f"{path.name} line {lineno}: prompt {prompt!r} is labelled "
                f"{handle!r}, which is not a canonical handle; expected one of "
                f"{sorted(CANONICAL_HANDLES)}"
            )
        if prompt in seen:
            raise DatasetError(
                f"{path.name} line {lineno}: duplicate prompt {prompt!r} — a "
                "repeated prompt silently reweights the metric"
            )
        seen.add(prompt)
        entries.append(
            DatasetEntry(
                prompt=prompt,
                expected_handle=handle,
                opening=bool(row.get("opening", False)),
                note=str(row.get("note") or ""),
            )
        )

    if not entries:
        raise DatasetError(f"{path.name}: dataset is empty")

    uncovered = CANONICAL_HANDLES - {entry.expected_handle for entry in entries}
    if uncovered:
        raise DatasetError(
            f"{path.name}: no prompt covers {sorted(uncovered)} — an uncovered "
            "handle cannot regress visibly"
        )
    return Dataset(version=version, path=path, entries=tuple(entries))


def score_run(
    dataset: Dataset,
    observations: dict[str, str],
    *,
    source: str,
    observed_on: str,
    evidence: str = "",
) -> Measurement:
    """Score a recorded rendered-chatbot run against ``dataset``.

    Refuses anything that would yield a misleading number: a non-rendered source,
    a missing date, a run that omits dataset prompts, or a run carrying prompts
    the dataset does not contain.

    ``evidence`` is an optional reviewable pointer to the rendered session (a
    ``ui-test`` log anchor, trace, or screenshot path). It is carried and
    reported, never checked — the label is a trusted transcription.
    """
    if not isinstance(observations, dict):
        raise MeasurementError(
            "observations must be a JSON object of prompt->observed handle, got "
            f"{type(observations).__name__}"
        )
    if not isinstance(evidence, str):
        raise MeasurementError(
            f"evidence must be a string reference, got {type(evidence).__name__}"
        )
    surface = (source or "").strip()
    if surface not in RENDERED_SOURCES:
        raise MeasurementError(
            f"source {source!r} is not a rendered chatbot surface (expected one "
            f"of {sorted(RENDERED_SOURCES)}); direct MCP calls, scripts, and "
            "canary probes are supporting evidence, not a measurement"
        )
    if not (observed_on or "").strip():
        raise MeasurementError("observed_on is required: a measurement without a date cannot age")

    expected_prompts = set(dataset.prompts)
    observed_prompts = set(observations)
    missing = sorted(expected_prompts - observed_prompts)
    if missing:
        raise MeasurementError(
            f"run covers {len(observed_prompts)}/{len(expected_prompts)} prompts; "
            f"missing {missing} — a partial run is refused rather than scored over "
            "the subset it happens to have"
        )
    extra = sorted(observed_prompts - expected_prompts)
    if extra:
        raise MeasurementError(
            f"run carries prompts not in the dataset: {extra} — the instrument is "
            "fixed; scoring extra prompts changes what is being measured"
        )

    correct = 0
    opening_total = 0
    opening_correct = 0
    non_canonical: list[str] = []
    misses: list[tuple[str, str, str]] = []
    for entry in dataset.entries:
        observed = str(observations[entry.prompt] or "").strip()
        if observed not in CANONICAL_HANDLES:
            # Scored incorrect, not discarded — and reported, so a systematic
            # mis-selection onto a retired/hallucinated tool stays visible.
            non_canonical.append(observed)
        hit = observed == entry.expected_handle
        if hit:
            correct += 1
        else:
            misses.append((entry.prompt, entry.expected_handle, observed))
        if entry.opening:
            opening_total += 1
            if observed == "converse":
                opening_correct += 1

    total = len(dataset.entries)
    return Measurement(
        dataset_version=dataset.version,
        surface=surface,
        observed_on=observed_on.strip(),
        top1_rate=correct / total,
        opening_converse_rate=(
            opening_correct / opening_total if opening_total else 0.0
        ),
        total=total,
        correct=correct,
        non_canonical_observed=tuple(dict.fromkeys(non_canonical)),
        misses=tuple(misses),
        evidence=evidence.strip(),
    )


def compare_to_baseline(
    measurement: Measurement, baseline: Baseline
) -> GateVerdict:
    """Gate a measurement against a recorded baseline.

    Takes NO tolerance argument by design — the permitted regression is a
    property of the recorded baseline, so a failing run cannot be rescued by
    loosening the threshold where the gate is invoked.
    """
    if measurement.dataset_version != baseline.dataset_version:
        raise MeasurementError(
            f"cannot compare a measurement on dataset {measurement.dataset_version} "
            f"to a baseline recorded on {baseline.dataset_version}: different "
            "instruments produce incomparable numbers"
        )
    if measurement.surface != baseline.surface:
        raise MeasurementError(
            f"cannot compare surface {measurement.surface!r} to a baseline "
            f"recorded on surface {baseline.surface!r}: they are different "
            "subjects under test"
        )

    tolerance = baseline.permitted_regression
    top1_drop = baseline.top1_rate - measurement.top1_rate
    opening_drop = baseline.opening_converse_rate - measurement.opening_converse_rate
    details = {
        "tolerance": tolerance,
        "top1_baseline": baseline.top1_rate,
        "top1_candidate": measurement.top1_rate,
        "opening_baseline": baseline.opening_converse_rate,
        "opening_candidate": measurement.opening_converse_rate,
    }
    reasons = []
    if top1_drop > tolerance:
        reasons.append(
            f"top1 fell {top1_drop:.3f} (baseline {baseline.top1_rate:.3f} -> "
            f"{measurement.top1_rate:.3f}), tolerance {tolerance:.3f}"
        )
    if opening_drop > tolerance:
        reasons.append(
            f"opening converse rate fell {opening_drop:.3f} (baseline "
            f"{baseline.opening_converse_rate:.3f} -> "
            f"{measurement.opening_converse_rate:.3f}), tolerance {tolerance:.3f}"
        )
    if reasons:
        return GateVerdict(passed=False, reason="; ".join(reasons), details=details)
    return GateVerdict(passed=True, reason="within tolerance", details=details)


def _load_baseline(path: Path) -> Baseline:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise MeasurementError(
            f"baseline {path} is not a JSON object (got {type(data).__name__})"
        )
    try:
        return Baseline(
            dataset_version=data["dataset_version"],
            surface=data["surface"],
            recorded_on=data["recorded_on"],
            # Passed unconverted on purpose: `Baseline.__post_init__` raises
            # MeasurementError for a non-numeric, non-finite, or out-of-range
            # value, so an unusable baseline exits 2 rather than crashing out of
            # the CLI's envelope with the exit code reserved for a failed gate.
            top1_rate=data["top1_rate"],
            opening_converse_rate=data["opening_converse_rate"],
            permitted_regression=data.get("permitted_regression", 0.0),
            evidence=str(data.get("evidence") or ""),
        )
    except KeyError as exc:
        raise MeasurementError(f"baseline {path} is missing {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument(
        "--run", required=True, type=Path,
        help="JSON: {source, observed_on, observations:{prompt: handle}}",
    )
    parser.add_argument(
        "--baseline", type=Path,
        help="JSON baseline to gate against. Omit to just report the rates.",
    )
    args = parser.parse_args(argv)

    # Exit 2 covers EVERY unusable input, so it never collides with exit 1 (a
    # valid run that failed a valid gate). TypeError/ValueError are caught as a
    # class, not enumerated: JSON is untyped, so any field can arrive as the
    # wrong shape, and a traceback out of here would be misread as exit 1.
    # (DatasetError, MeasurementError and json.JSONDecodeError are all
    # ValueError subclasses; named for the reader.)
    try:
        dataset = load_dataset(args.dataset)
        run = json.loads(args.run.read_text(encoding="utf-8"))
        if not isinstance(run, dict):
            raise MeasurementError(
                f"run {args.run} is not a JSON object (got {type(run).__name__})"
            )
        measurement = score_run(
            dataset,
            run.get("observations") or {},
            source=str(run.get("source") or ""),
            observed_on=str(run.get("observed_on") or ""),
            evidence=str(run.get("evidence") or ""),
        )
    except (DatasetError, MeasurementError, OSError, TypeError, ValueError) as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2

    print(
        f"dataset={measurement.dataset_version} surface={measurement.surface} "
        f"observed_on={measurement.observed_on}\n"
        f"top1={measurement.top1_rate:.3f} "
        f"({measurement.correct}/{measurement.total})  "
        f"opening_converse={measurement.opening_converse_rate:.3f}"
    )
    for prompt, expected, observed in measurement.misses:
        print(f"  MISS  {prompt!r}: expected {expected}, observed {observed!r}")
    if measurement.non_canonical_observed:
        print(f"  non-canonical handles observed: {list(measurement.non_canonical_observed)}")
    if measurement.evidence:
        print(f"  rendered-session evidence: {measurement.evidence}")
    else:
        print(
            "  rendered-session evidence: none recorded — the source label is a "
            "trusted transcription, not proof of provenance"
        )

    if not args.baseline:
        return 0
    try:
        verdict = compare_to_baseline(measurement, _load_baseline(args.baseline))
    except (MeasurementError, OSError, TypeError, ValueError) as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2
    print(f"GATE {'PASS' if verdict.passed else 'FAIL'}: {verdict.reason}")
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
