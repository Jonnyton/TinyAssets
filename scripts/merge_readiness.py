"""Read-only merge-readiness classification for community-loop PRs.

This script is a view, not an executor. It never approves, closes, rebases, or
merges a pull request. Its job is to turn scattered PR facts into the next
safe routing state so the loop can learn from queue pileups without relying on
operator memory.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

WRITER_CODEX_LABEL = "writer:codex"
WRITER_CLAUDE_LABEL = "writer:claude"
CHECKER_CODEX_LABEL = "checker:codex"
CHECKER_CLAUDE_LABEL = "checker:claude"
READY_FOR_CHECKER_LABEL = "ready_for_checker"

SEND_BACK_PATTERNS = (
    "send-back/amend",
    "send back",
    "not approval-ready",
    "please amend/regenerate",
    "source-hydration blocker",
)

PRECHECK_BLOCKED_PATTERNS = (
    "pre-checker self-review blocked",
    "pre-check failure",
    "precheck failure",
    "stale-base check failed",
)

HOST_KEY_PATTERNS = (
    "host key recorded",
    "host third-key explicit",
    "host explicitly turned keys",
)

CHECKER_VERDICT_MARKER = "workflow-checker-verdict:v1"
CHECKER_VERDICT_ATTR_RE = re.compile(r"([a-z_]+)=([^\s>]+)")

INDEPENDENT_CHECKER_BLOCKER_TERMS = (
    "independent checker",
    "independent codex checker",
    "independent claude checker",
    "not an independent",
)

EXECUTOR_INELIGIBILITY_TERMS = (
    "current executor",
    "executor session",
    "same session",
    "mechanically applied",
    "mechanically executed",
    "mechanically opened",
    "support commit",
    "support commits",
    "ineligible",
)


@dataclass(frozen=True)
class ConsensusMirrorFacts:
    """Facts required by the narrow ConsensusMirrorSelfClearance predicate."""

    engaged_aligned_source: bool = False
    cross_family_source: bool = False
    source_hash_matches: bool = False
    no_semantic_delta: bool = False
    no_frontmatter_delta: bool = False
    no_scope_delta: bool = False

    @classmethod
    def from_mapping(cls, value: Any) -> "ConsensusMirrorFacts":
        if not isinstance(value, dict):
            return cls()
        return cls(
            engaged_aligned_source=bool(value.get("engaged_aligned_source")),
            cross_family_source=bool(value.get("cross_family_source")),
            source_hash_matches=bool(value.get("source_hash_matches")),
            no_semantic_delta=bool(value.get("no_semantic_delta")),
            no_frontmatter_delta=bool(value.get("no_frontmatter_delta")),
            no_scope_delta=bool(value.get("no_scope_delta")),
        )

    def eligible(self) -> bool:
        return all(
            (
                self.engaged_aligned_source,
                self.cross_family_source,
                self.source_hash_matches,
                self.no_semantic_delta,
                self.no_frontmatter_delta,
                self.no_scope_delta,
            )
        )

    def missing(self) -> list[str]:
        fields = {
            "engaged_aligned_source": self.engaged_aligned_source,
            "cross_family_source": self.cross_family_source,
            "source_hash_matches": self.source_hash_matches,
            "no_semantic_delta": self.no_semantic_delta,
            "no_frontmatter_delta": self.no_frontmatter_delta,
            "no_scope_delta": self.no_scope_delta,
        }
        return [name for name, present in fields.items() if not present]


@dataclass(frozen=True)
class PullRequestFacts:
    number: int
    title: str
    state: str = "OPEN"
    head_oid: str = ""
    merge_state_status: str = "UNKNOWN"
    labels: frozenset[str] = frozenset()
    opposite_family_checker_approved: bool = False
    host_keyed: bool = False
    checks_green: bool | None = None
    send_back_advisory: bool = False
    precheck_blocked: bool = False
    checker_executor_ineligible: bool = False
    consensus_mirror: ConsensusMirrorFacts = ConsensusMirrorFacts()

    @classmethod
    def from_mapping(cls, pr: dict[str, Any]) -> "PullRequestFacts":
        labels = frozenset(_label_names(pr.get("labels", [])))
        comments = pr.get("comments", [])
        reviews = pr.get("reviews", [])
        checker_family = _checker_family(labels)
        head_oid = str(pr.get("headRefOid") or pr.get("head_oid") or pr.get("head_sha") or "")
        return cls(
            number=int(pr["number"]),
            title=str(pr.get("title") or ""),
            state=str(pr.get("state") or "OPEN"),
            head_oid=head_oid,
            merge_state_status=str(
                pr.get("merge_state_status")
                or pr.get("mergeStateStatus")
                or pr.get("mergeable_state")
                or "UNKNOWN"
            ),
            labels=labels,
            opposite_family_checker_approved=bool(
                pr.get("opposite_family_checker_approved")
                or _has_required_family_approval(reviews)
                or _has_required_checker_verdict(comments, checker_family, head_oid)
            ),
            host_keyed=bool(pr.get("host_keyed") or _has_host_key_comment(comments)),
            checks_green=pr.get("checks_green"),
            send_back_advisory=bool(
                pr.get("send_back_advisory")
                or _has_send_back_advisory(comments)
                or _has_checker_send_back_verdict(comments, checker_family, head_oid)
            ),
            precheck_blocked=bool(pr.get("precheck_blocked") or _has_precheck_blocker(comments)),
            checker_executor_ineligible=bool(
                pr.get("checker_executor_ineligible")
                or _has_checker_executor_ineligibility(comments, checker_family)
            ),
            consensus_mirror=ConsensusMirrorFacts.from_mapping(pr.get("consensus_mirror")),
        )


@dataclass(frozen=True)
class ReadinessResult:
    number: int
    state: str
    next_action: str
    risk_class: str
    merge_executor_state: str
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "state": self.state,
            "next_action": self.next_action,
            "risk_class": self.risk_class,
            "merge_executor_state": self.merge_executor_state,
            "reasons": list(self.reasons),
        }


def classify_pr(facts: PullRequestFacts) -> ReadinessResult:
    """Classify one PR into the next safe routing state."""

    reasons: list[str] = []
    risk_class = _risk_class(facts)
    writer_family = _writer_family(facts.labels)
    checker_family = _checker_family(facts.labels)

    if facts.state.upper() != "OPEN":
        return _result(
            facts,
            "not_open",
            "ignore closed or merged PRs",
            risk_class,
            "not_applicable",
            [f"state={facts.state}"],
        )

    if facts.precheck_blocked:
        return _result(
            facts,
            "blocked_precheck",
            "resolve pre-check failures before checker review",
            risk_class,
            "blocked",
            ["pre-check comment reports blocked self-review"],
        )

    anomalies = _routing_anomalies(facts.labels)
    if anomalies:
        return _result(
            facts,
            "routing_anomaly",
            "send to loop-routing repair",
            risk_class,
            "blocked",
            anomalies,
        )

    if not writer_family and not checker_family:
        return _result(
            facts,
            "needs_loop_labels",
            "apply writer/checker labels before review routing",
            risk_class,
            "blocked",
            ["missing writer/checker labels"],
        )

    if facts.merge_state_status != "CLEAN":
        return _result(
            facts,
            "blocked_merge_state",
            "repair stale or dirty branch before review",
            risk_class,
            "blocked",
            [f"merge_state_status={facts.merge_state_status}"],
        )

    if facts.send_back_advisory:
        return _result(
            facts,
            "send_back_amend",
            "amend or regenerate before checker review",
            risk_class,
            "blocked",
            ["consensus or advisory says send-back/amend"],
        )

    if READY_FOR_CHECKER_LABEL not in facts.labels:
        return _result(
            facts,
            "blocked_precheck",
            "resolve pre-check failures before checker review",
            risk_class,
            "blocked",
            [f"missing {READY_FOR_CHECKER_LABEL} label"],
        )

    if facts.consensus_mirror.eligible():
        return _result(
            facts,
            "consensus_mirror_self_clearance_canary",
            "record as canary; do not auto-merge in this slice",
            risk_class,
            "blocked_policy_canary",
            ["all ConsensusMirrorSelfClearance predicate fields are true"],
        )

    if facts.consensus_mirror != ConsensusMirrorFacts():
        reasons.append(
            "ConsensusMirrorSelfClearance missing: " + ", ".join(facts.consensus_mirror.missing())
        )

    if checker_family and not facts.opposite_family_checker_approved:
        checker_name = "Cowork/Claude" if checker_family == "claude" else "Codex"
        if facts.checker_executor_ineligible:
            return _result(
                facts,
                f"needs_independent_{checker_family}_checker",
                f"route to independent {checker_name} checker; current executor is ineligible",
                risk_class,
                "blocked_ineligible_checker",
                reasons
                + [
                    f"required_checker_family={checker_family}",
                    "current executor/session cannot provide checker key",
                ],
            )
        return _result(
            facts,
            f"needs_{checker_family}_checker",
            f"route to {checker_name} checker",
            risk_class,
            "blocked",
            reasons + [f"required_checker_family={checker_family}"],
        )

    if not facts.host_keyed:
        return _result(
            facts,
            "needs_host_key",
            "summarize implications and ask host for explicit PR key",
            risk_class,
            "blocked",
            reasons + ["opposite-family checker present; explicit host key absent"],
        )

    if facts.checks_green is False:
        return _result(
            facts,
            "needs_green_checks",
            "wait for or repair failing checks before execution",
            risk_class,
            "blocked",
            reasons + ["host key present but checks_green=false"],
        )

    if facts.checks_green is None:
        return _result(
            facts,
            "needs_check_evidence",
            "fetch check evidence before mechanical execution",
            risk_class,
            "blocked",
            reasons + ["host key present but checks_green is unknown"],
        )

    return _result(
        facts,
        "merge_executor_ready",
        "mechanical executor may merge if branch protection still agrees",
        risk_class,
        "ready",
        reasons + ["checker, host key, clean branch, and green checks are present"],
    )


def classify_many(prs: list[dict[str, Any]]) -> dict[str, Any]:
    results = [classify_pr(PullRequestFacts.from_mapping(pr)) for pr in prs]
    by_state: dict[str, int] = {}
    for result in results:
        by_state[result.state] = by_state.get(result.state, 0) + 1
    return {
        "count": len(results),
        "by_state": dict(sorted(by_state.items())),
        "items": [result.as_dict() for result in results],
    }


def _label_names(labels: Any) -> set[str]:
    names: set[str] = set()
    for label in labels or []:
        if isinstance(label, str):
            names.add(label)
        elif isinstance(label, dict) and label.get("name"):
            names.add(str(label["name"]))
    return names


def _has_send_back_advisory(comments: Any) -> bool:
    for comment in comments or []:
        body = comment.get("body") if isinstance(comment, dict) else str(comment)
        lowered = str(body or "").lower()
        if any(pattern in lowered for pattern in SEND_BACK_PATTERNS):
            return True
    return False


def _has_precheck_blocker(comments: Any) -> bool:
    for comment in comments or []:
        body = comment.get("body") if isinstance(comment, dict) else str(comment)
        lowered = str(body or "").lower()
        if any(pattern in lowered for pattern in PRECHECK_BLOCKED_PATTERNS):
            return True
    return False


def _has_host_key_comment(comments: Any) -> bool:
    for comment in comments or []:
        body = comment.get("body") if isinstance(comment, dict) else str(comment)
        lowered = str(body or "").lower()
        if any(pattern in lowered for pattern in HOST_KEY_PATTERNS):
            return True
    return False


def _checker_verdicts(comments: Any) -> list[dict[str, str]]:
    verdicts: list[dict[str, str]] = []
    for comment in comments or []:
        body = comment.get("body") if isinstance(comment, dict) else str(comment)
        lowered = str(body or "").lower()
        marker_index = lowered.find(CHECKER_VERDICT_MARKER)
        if marker_index < 0:
            continue
        marker_tail = lowered[marker_index + len(CHECKER_VERDICT_MARKER) :]
        marker_tail = marker_tail.split("-->", 1)[0]
        verdicts.append(dict(CHECKER_VERDICT_ATTR_RE.findall(marker_tail)))
    return verdicts


def _head_matches(verdict: dict[str, str], head_oid: Any) -> bool:
    head = str(head_oid or "").lower()
    verdict_head = str(verdict.get("head") or "").lower()
    if not head:
        return True
    return bool(verdict_head) and verdict_head == head


def _has_required_checker_verdict(
    comments: Any,
    checker_family: str | None,
    head_oid: Any,
) -> bool:
    if not checker_family:
        return False
    for verdict in _checker_verdicts(comments):
        if (
            verdict.get("family") == checker_family
            and verdict.get("verdict") == "approve"
            and _head_matches(verdict, head_oid)
        ):
            return True
    return False


def _has_checker_send_back_verdict(
    comments: Any,
    checker_family: str | None,
    head_oid: Any,
) -> bool:
    for verdict in _checker_verdicts(comments):
        family_matches = not checker_family or verdict.get("family") == checker_family
        if (
            family_matches
            and verdict.get("verdict") in {"send_back", "reject", "changes_requested"}
            and _head_matches(verdict, head_oid)
        ):
            return True
    return False


def _has_checker_executor_ineligibility(comments: Any, checker_family: str | None) -> bool:
    if not checker_family:
        return False
    family_term = f"independent {checker_family} checker"
    for comment in comments or []:
        body = comment.get("body") if isinstance(comment, dict) else str(comment)
        lowered = str(body or "").lower()
        has_independent_checker_reference = family_term in lowered or any(
            term in lowered for term in INDEPENDENT_CHECKER_BLOCKER_TERMS
        )
        has_executor_ineligibility = any(term in lowered for term in EXECUTOR_INELIGIBILITY_TERMS)
        if has_independent_checker_reference and has_executor_ineligibility:
            return True
    return False


def _has_required_family_approval(reviews: Any) -> bool:
    for review in reviews or []:
        if not isinstance(review, dict):
            continue
        if review.get("required_family_approved") is True:
            return True
        if review.get("opposite_family_checker_approved") is True:
            return True
    return False


def _writer_family(labels: set[str] | frozenset[str]) -> str | None:
    families = []
    if WRITER_CODEX_LABEL in labels:
        families.append("codex")
    if WRITER_CLAUDE_LABEL in labels:
        families.append("claude")
    return families[0] if len(families) == 1 else None


def _checker_family(labels: set[str] | frozenset[str]) -> str | None:
    families = []
    if CHECKER_CODEX_LABEL in labels:
        families.append("codex")
    if CHECKER_CLAUDE_LABEL in labels:
        families.append("claude")
    return families[0] if len(families) == 1 else None


def _routing_anomalies(labels: set[str] | frozenset[str]) -> list[str]:
    anomalies: list[str] = []
    writer_labels = [label for label in labels if label.startswith("writer:")]
    checker_labels = [label for label in labels if label.startswith("checker:")]
    if len(writer_labels) > 1:
        anomalies.append("multiple writer-family labels")
    if len(checker_labels) > 1:
        anomalies.append("multiple checker-family labels")
    if writer_labels and not checker_labels:
        anomalies.append("missing checker-family label")
    if checker_labels and not writer_labels:
        anomalies.append("missing writer-family label")
    if WRITER_CODEX_LABEL in labels and CHECKER_CODEX_LABEL in labels:
        anomalies.append("Codex-written PR cannot require Codex checker")
    if WRITER_CLAUDE_LABEL in labels and CHECKER_CLAUDE_LABEL in labels:
        anomalies.append("Claude-written PR cannot require Claude checker")
    return anomalies


def _risk_class(facts: PullRequestFacts) -> str:
    title = facts.title.lower()
    if "wiki-docs" in title or "design-note" in title:
        return "docs_or_brain"
    if "wiki-patch" in title:
        return "brain_patch"
    if re.search(r"\b(sandbox|auth|credential|secret|permission)\b", title):
        return "security_or_auth"
    if "bug-" in title:
        return "code_or_runtime"
    return "unknown"


def _result(
    facts: PullRequestFacts,
    state: str,
    next_action: str,
    risk_class: str,
    merge_executor_state: str,
    reasons: list[str],
) -> ReadinessResult:
    return ReadinessResult(
        number=facts.number,
        state=state,
        next_action=next_action,
        risk_class=risk_class,
        merge_executor_state=merge_executor_state,
        reasons=tuple(reasons),
    )


def _read_input(path: str | None) -> list[dict[str, Any]]:
    if path:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    elif not sys.stdin.isatty():
        payload = json.load(sys.stdin)
    else:
        raise SystemExit("Provide --input-json or pipe a gh PR JSON array on stdin.")

    if isinstance(payload, dict) and "items" in payload:
        payload = payload["items"]
    if not isinstance(payload, list):
        raise SystemExit("Input must be a JSON list of PR objects.")
    return payload


def _fetch_gh_prs(repo: str, limit: int, hydrate_comments: bool = False) -> list[dict[str, Any]]:
    fields = "number,state,mergeStateStatus,title,headRefOid,labels"
    raw = subprocess.check_output(
        ["gh", "pr", "list", "--repo", repo, "--limit", str(limit), "--json", fields],
        text=True,
        encoding="utf-8",
    )
    prs = json.loads(raw)
    if hydrate_comments:
        for pr in prs:
            detail_raw = subprocess.check_output(
                [
                    "gh",
                    "pr",
                    "view",
                    str(pr["number"]),
                    "--repo",
                    repo,
                    "--json",
                    "comments,reviews",
                ],
                text=True,
                encoding="utf-8",
            )
            pr.update(json.loads(detail_raw))
    return prs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify community-loop PR merge readiness without mutating GitHub."
    )
    parser.add_argument("--input-json", help="Path to gh-style PR facts JSON.")
    parser.add_argument("--repo", help="Fetch open PR facts with gh instead of reading JSON.")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument(
        "--hydrate-comments",
        action="store_true",
        help="With --repo, read each PR's comments/reviews before classifying.",
    )
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)

    prs = (
        _fetch_gh_prs(args.repo, args.limit, hydrate_comments=args.hydrate_comments)
        if args.repo
        else _read_input(args.input_json)
    )
    payload = classify_many(prs)
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
