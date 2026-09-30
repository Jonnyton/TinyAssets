## Why

Launch testers exhaust a connected provider's daily free quota in a few agent turns. TinyAssets currently describes that daily exhaustion as a short cooldown and offers too few readily connectable alternatives.

## What Changes

- Distinguish daily source quota from transient throttling, retain the reset evidence, and offer another free source or the provider's credit page.
- Add verified Google AI Studio, Groq, Cerebras and Mistral connection presets using api_key_http and openai_chat.
- Cool an exhausted source and continue the existing owner-bound candidate order for chat and workflows.
- Expose the presets in the existing connect card and gently suggest a second source to owners with just one.

## Capabilities

### New Capabilities
- `free-source-pooling`: daily quota evidence and owner-bound source fallback with discoverable free-source connection cards.

### Modified Capabilities
None.

## Impact

Provider capacity decoding, router cooldown evidence, failure notices, onboarding connect cards and their regression tests. No platform credentials, account tier branches, new platform rate limits or expanded model grants.

Owner: Codex. Branch: free-compute-pool. Delivery: one PR; deployment and live app proof follow merge.
