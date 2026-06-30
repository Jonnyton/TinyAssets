#!/usr/bin/env python3
"""Claude Code hook: push the Codex cross-family dispatch reflex.

Claude sessions *have* the `mcp__codex__codex` capability and the CLAUDE.md
§"Calling Codex via MCP" instructions in context, but the behavior is passive
knowledge — without a trigger at the decision moment the default-to-self bias
wins and the opposite-provider gate silently doesn't fire (the failure the host
reported: Claude finishes a review and presents a verdict without ever
cross-checking with Codex, then only dispatches once told to).

This is the trigger layer. On UserPromptSubmit, classify the prompt against the
qualifying surface (review / finding / risky-ship / decision / stuck /
second-opinion) and inject an imperative reminder with the exact dispatch shape.
Mirrors provider_context_feed_hook.py: non-blocking, additionalContext only.

Calibrated aggressive per host directive 2026-06-30 (default-to-dispatch), but
deliberately NOT firing on every build/edit/lookup — a nudge on every turn is
noise that gets tuned out, which defeats the purpose. It fires where an
independent model genuinely adds confidence.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

# Ordered most-actionable-first; the first match wins so the nudge is specific.
TRIGGERS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "stuck-loop",
        "Fresh eyes: hand Codex the error + what you've already tried for a "
        "different-model angle (don't grind a 4th time on the same approach).",
        re.compile(
            r"\b(stuck|blocked|can'?t (figure|get|work)|keep(s)? failing|"
            r"still (failing|broken)|same error|going in circles|"
            r"tried everything|3\+? ?(times|iterations|attempts))\b",
            re.I,
        ),
    ),
    (
        "review/finding",
        "Dispatch the opposite-provider review gate: have Codex re-check the "
        "sources + the actual code and return approve/adapt/reject BEFORE you "
        "present a verdict, finding, or 'looks correct' claim.",
        re.compile(
            r"\b(review|verif\w+|audit|conformance|finding|findings|verdict|"
            r"is this (right|correct|sound)|double[- ]?check|sanity[- ]?check|"
            r"security review|re-?check)\b",
            re.I,
        ),
    ),
    (
        "risky/ship",
        "Get an adversarial second opinion before acting: ask Codex to *refute* "
        "the change/plan/result — independent skeptic pass before it ships.",
        re.compile(
            r"\b(ship|push|deploy|merge|release|roll[- ]?out|rollout|land|"
            r"production|risky|breaking change|data ?loss|migration)\b",
            re.I,
        ),
    ),
    (
        "decision/recommend",
        "Get a diverse-perspective judge: have Codex independently weigh the "
        "options before you present a recommendation (different model than the "
        "writer).",
        re.compile(
            r"\b(recommend\w*|which (one|approach|option|way)|should (i|we)|"
            r"compare|trade[- ]?offs?|decide|decision|best approach|judge)\b",
            re.I,
        ),
    ),
    (
        "second-opinion",
        "Ask Codex to *refute* it — an independent skeptic pass before you rely "
        "on this result.",
        re.compile(
            r"\b(second opinion|refute|are you sure|surprising|unexpected|"
            r"skeptic\w*|sceptic\w*|challenge this|does this (look|seem) (right|ok))\b",
            re.I,
        ),
    ),
)


def classify(prompt: str) -> tuple[str, str] | None:
    for label, instruction, pattern in TRIGGERS:
        if pattern.search(prompt):
            return label, instruction
    return None


def render(label: str, instruction: str) -> str:
    return "\n".join(
        (
            f"Codex cross-family reflex — qualifying signal: {label}.",
            "You have Codex (a second model family) wired into the harness. Per",
            'CLAUDE.md §"Calling Codex via MCP", dispatch PROACTIVELY now — do not',
            "wait to be told:",
            f"  → {instruction}",
            "  Call mcp__codex__codex (sandbox: read-only, approval-policy: never;",
            "  workspace-write only if Codex must edit, in its own branch). Log the",
            "  verdict like any review.",
            "This dispatch is a standing reflex, not an option. If you deliberately",
            "skip it, say so in one line and why — don't just default to doing it",
            "yourself.",
        )
    )


def main() -> int:
    try:
        payload: dict[str, Any] = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if str(payload.get("hook_event_name") or "") != "UserPromptSubmit":
        return 0

    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return 0

    match = classify(prompt)
    if match is None:
        return 0

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": render(*match),
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
