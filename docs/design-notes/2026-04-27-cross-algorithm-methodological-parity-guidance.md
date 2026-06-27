---
title: Cross-algorithm methodological-parity guidance via wiki composition
date: 2026-04-27
author: codex-gpt5-desktop
status: proposed
type: design-note
companion:
  - ideas/INBOX.md (2026-04-27 parity entry)
  - ideas/PIPELINE.md (cross-algorithm parity row)
  - tinyassets/api/helpers.py
  - tinyassets/api/market.py
load-bearing-question: Does this make the user's chatbot better at serving the user's real goal?
audience: lead, navigator, future dev/spec author
---

# Cross-algorithm methodological-parity guidance via wiki composition

## Decision

Do not add a new platform primitive for parity guidance now.

Ship parity guidance as a wiki concept-page template that chatbots compose at response time. Only escalate to a new MCP verb if wiki composition proves structurally insufficient.

## Why this route

- The need is real: users can make invalid comparisons when algorithm assumptions differ.
- The platform already has composition surfaces (`wiki` content + existing chatbot/tool routing).
- This follows the current minimal-primitives and community-build direction.
- A wiki-first path is reversible, cheap, and fast to iterate from user feedback.

## MVP content shape (wiki concept template)

Create one canonical concept page template that domain authors can fill:

1. **Comparison pair**
   - Algorithm A, Algorithm B.
2. **Assumption delta**
   - What one method requires that the other does not.
3. **Data-prep implications**
   - Required transforms, pseudo-absence/background strategy, leakage risks.
4. **Evaluation parity checks**
   - Which metrics are safe to compare directly, which are not.
5. **Failure modes**
   - Common invalid-comparison mistakes.
6. **Chatbot promptable checklist**
   - 5-8 short checks a chatbot can run before drafting conclusions.

## Seed example: RF vs MaxEnt

- **Assumption delta:** MaxEnt commonly needs background/pseudo-absence strategy discipline; RF typically consumes explicit absence labels or engineered pseudo-absences differently.
- **Parity risk:** "RF > MaxEnt AUC" claims can be invalid if pseudo-absence generation differs across arms.
- **Checklist snippet:**
  - Did both arms use the same pseudo-absence/background policy?
  - Are evaluation folds spatially consistent across algorithms?
  - Are thresholding and prevalence adjustments documented for both arms?

## Escalation trigger (when wiki-first is not enough)

Escalate to a platform primitive only if all are true:

1. Repeated user failures persist after wiki guidance is available.
2. Chatbot cannot reliably retrieve/apply the guidance with existing tools.
3. A structured output shape is required for downstream automation (not just prose quality).

## Next actions

1. Author the first wiki concept page using the template and the RF-vs-MaxEnt seed.
2. Run one user-sim pass to verify chatbot retrieval and checklist usage.
3. If the pass is clean, keep this as community guidance and do not open platform API work.
