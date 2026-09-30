## Context

PRs #4124/#4132 use prepare_owned_model_plan for both chat and workflow candidates. HTTP capacity currently decodes status and Retry-After only, losing the daily quota in the response body; source cooldowns subsequently lose the reason too.

## Goals / Non-Goals

Recognize explicit daily exhaustion, preserve actionable notices across cooled attempts, and pool only already accepted sources belonging to the same owner and universe. Keep one generic HTTP execution path, no account tier conditionals and no platform keys or additional platform rate limits.

## Decisions

- Decode bounded structured error bodies and reset headers as capacity evidence, independent of vendor host. Explicit daily evidence wins over a short generic retry hint. Unknown 429s remain transient/unknown; never infer daily solely from status 429.
- Carry daily classification through the existing source cooldown and attempt evidence. Daily exhaustion is account/source scope and cannot narrow to a sibling model. Existing candidate selection handles the next source; authority and price ceilings still apply to every attempt.
- Add connection presets as data using the existing manual-key connect mechanism and generic OpenAI chat contract. Document verified endpoints and free/trial restrictions; Cerebras currently requires a payment method for expiring trial credit.
- Keep recovery URLs from trusted preset data, not arbitrary provider error text. Unknown daily reset uses a conservative one-day cooldown without claiming a provider-promised reset time.
- Suggest an additional source for a single-source owner regardless of TinyAssets account tier.

## Risks / Trade-offs

Provider error shapes and offers change: cite official docs, test representative structured shapes, and leave ambiguous responses unclassified. Some daily limits are model-specific: conservatively cool the connected source as requested instead of burning more rounds. Providers without enforceable monetary ceilings must not be misrepresented as zero-cost; retain existing explicit owner acceptance.

## Migration Plan

Additive preset and evidence changes; rebuild plugin mirror. No credential migration. Revert the PR to roll back. Deployment and live app proof remain post-merge work.
