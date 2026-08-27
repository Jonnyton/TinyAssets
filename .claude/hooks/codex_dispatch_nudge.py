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
        "cross-family-gate",
        "This names an opposite-provider / cross-family review gate — dispatch "
        "Codex to re-check sources + actual code and return "
        "approve/adapt/reject before the gated step advances.",
        re.compile(
            r"\b(cross[- ]?family|opposite[- ]?provider|dual[- ]?family|"
            r"research[- ]derived|codex review|security (review|audit))\b",
            re.I,
        ),
    ),
    (
        "high-risk-ship",
        "High-risk / hard-to-reverse change: ask Codex to *refute* it before "
        "it ships — independent skeptic pass on Codex's budget.",
        re.compile(
            r"\b(deploy|production|release|roll[- ]?out|rollout|migration|"
            r"data ?loss|breaking change|irreversible|mass[- ](delete|deletion)|"
            # merged-is-deployed repo: shipping/merging to main IS production
            r"auth (change|migration)|ship (it|this)|(push|merge) to main)\b",
            re.I,
        ),
    ),
    (
        "second-opinion",
        "The user is explicitly inviting an independent check — ask Codex to "
        "*refute* the result before relying on it.",
        re.compile(
            r"\b(second opinion|refute|are you sure|skeptic\w*|sceptic\w*|"
            r"challenge this)\b",
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
            f"Codex judgment-class signal: {label}.",
            f"  → {instruction}",
            "  BACKGROUND offload on Codex's quota: `python scripts/peer_agent.py",
            '  --out <lane-local-file> --prompt "<ask>"` in a background Bash call',
            "  (the wrapper feeds Codex via stdin — never multi-line argv — and",
            "  fail-closes with `VERDICT: error` on timeout/no-output).",
            "  Inline `mcp__codex__codex` only for a quick blocking gate.",
            'Policy: CLAUDE.md §"Calling Codex via MCP" — dispatch for',
            "judgment-class decisions, not routine work.",
        )
    )


def main() -> int:
    try:
        payload: Any = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    # Valid JSON that isn't an object (e.g. `[]`) would crash payload.get.
    if not isinstance(payload, dict):
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
