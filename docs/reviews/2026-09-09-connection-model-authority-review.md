# Dynamic connection-model authority review

September 9, 2026. Claude returned ADAPT (exit 0, 262s). The brief pinned 336adc95;
source reading also observed the later endpoint-path correction 9240d92f while
that independent bugfix was in progress. No other runtime source changed during
this review. This is shape evidence, not exact-head implementation approval.

Lead accepts provider-keyed children with explicit root anchoring, and set-once
request-registry launch limits. Those corrections are integrated into
connection-model-authority.md. No new provenance token is added for model choice;
trusted authority owns and overwrites it. Zero-price enforcement still requires
adapter and live evidence. Discovery metadata and HTTP tools remain unfinished.

**Verdict up front: ADAPT.** The schema/authority/model-override seam is consistent with the existing custody, binding and assignment protocol and with the owner's requirements. Two statements in the new adaptation cannot both be implemented as written and need one correction each. The ModelConfig propagation question resolves to "no new token, same provenance as the authority." Details follow.

## AGREE, with source citations

- **Connection scope independent from model choice is already how the HTTP path is built.** Definition identity hashes the model (`tinyassets/providers/definition.py:117`), but custody verification is model-blind: it recomputes the grant record digest from grant, connection, credential ref, owner and universe only (`tinyassets/provider_serving_binding.py:280-292`). The router resolves a fresh `ApiKeyHttpProvider` per call from the content-addressed definition (`tinyassets/providers/router.py:845`, `provider_resolver.py:54-64`), and the model reaches the wire only as an encoder argument (`api_key_http_provider.py:181-185`). A per-attempt override passed into the encoder changes no definition, no host, no path, no auth, and no shared instance. Children naming the existing definition plus a signed `model_scope` fit this cleanly.
- **A newly discovered HTTP model needs no definition mutation.** A member sets `model_scope=discovered` with a cost ceiling through the existing bind transaction, which advances the assignment generation once. At attempt time the shared validator refreshes the owner-filtered catalogue through the same grant's allowlisted GET, checks membership, price and executor shape, and returns the opaque id. The router passes it to the encoder in place of `definition.model`. The definition id, the serving binding id and the custody tuple are all untouched, so the legacy pin coexists with dynamic selection.
- **Discovery GET on the same connection does not disturb inference routing.** `_declared_path` already filters to POST endpoints and its docstring explicitly excludes read-only catalogue paths (`api_key_http_provider.py:65-90`). The broker allowlist remains the only grant.
- **Launch accounting reorder is implementable in place.** Today the request launch is consumed before budget reservation and slot admission (`router.py:916-933`, slot at 954). Moving the consume to just before `provider.complete` inside the slot, with the existing release path for pre-launch refusals (`router.py:968-975`), matches the spec. Consumption runs under the registry lock with a per-nonce record (`auth/middleware.py:335-343`), so concurrent calls cannot inflate the count.
- **Replay and non-ready denial.** The current replay early-return compares provider, digest, provider_ref and ceilings only (`provider_serving_binding.py:425-436`); the spec correctly requires membership and constraint equality to be added. Readiness already requires a ready root (`provider_serving_binding.py:641-647`), so stale children under a pending or failed root are inert without cleanup.
- **Price claims stay within evidence.** The fetched OpenRouter provider-selection page confirms `max_price` accepts prompt, completion, request and image, in dollars per million tokens or per image, and states the request will not run if the price is not available. The page says nothing about zero pricing or free models. The spec's zero-ceiling free-only rule is therefore a design inference, correctly hedged by "missing evidence is unknown." Today's encoders emit only model, messages, temperature and max_tokens (`protocol_encoders.py:67-125`), so in-request enforcement is new encoder work gated on the connection's declared pricing protocol, not on the generic `openai_chat` shape.

## DISAGREE_EVIDENCE: two blockers with corrections

**1. Sorted-identity hashing and child-0/root equality contradict each other.** The adaptation says canonical hashing sorts members by stable identity, and separately requires child-0/root equality on every read. The prior review's schema keys children on `(universe_id, assignment_generation, position)` with position 0 as the primary. If positions follow sorted identity, child 0 is whichever identity sorts first, not the root anchor. If positions put the root first, position is an ordering the manifest was supposed to exclude. Implemented literally, the read check fails or the digest silently depends on order.
Correction: remove `position` from child identity. Key child rows on `(universe_id, assignment_generation, provider)`. Compute the manifest digest over the root identity followed by the sorted set of all member identities. On every read, verify the digest, then verify that the child whose provider equals `assignment.provider` matches the root row field for field. Preference order stays in the policy record only.

**2. The sealed launch allowance has no home in the current seam.** The spec requires sealing one plan under the authenticated request and never raising it after a launch. But the limit is currently a constant assigned per authorization (`provider_assignment.py:1238,1269`), authorization runs once per router call (`router.py:504-513`), and `consume_provider_request_invocation` takes `limit` as a fresh caller argument every time (`auth/middleware.py:321-343`). A second attempt in the same turn, after a catalogue refresh added candidates, would recompute a larger allowance, violating the spec's own rule and gate 5.
Correction: add a set-once `launch_limit` to the request registry record, written by a new `seal_provider_request_launch_allowance(capability, limit)` that refuses a second call with a different value. Make consumption enforce the sealed value when present and fall back to the passed limit otherwise, which keeps legacy at 2 with no seal.

## DISAGREE_CONCERN: no unforgeable token for the model selection

The router already records the Codex decision that no in-process provenance scheme survives an in-process adversary (`router.py:484-493`), and `ServedProviderAuthority` is a plain dataclass trusted because only `authorize_served_provider_call` yields it. Launch unforgeability comes from the non-constructible, pid-bound capability (`auth/middleware.py:92-118`). A stronger token for the model selection than for the authority itself adds nothing. What matters is provenance and overwrite semantics. Carry the selection as a field on the authority, default None meaning legacy. On the served path the router must overwrite, exactly as it already does for the credential snapshot directory (`router.py:630-633`). Never read a caller-settable ModelConfig field, because `_default_config` builds ModelConfig from universe config (`router.py:166-184`) and a config-supplied model would bypass validation. The CLI adapters already take the model as a list argument, not shell text (`codex_provider.py:786`), and the operator env override (`codex_provider.py:224-232`) must remain distinct from the validated selection.

One non-blocking note: with `discovered` scope on OpenRouter the eligible count can reach dozens, so the twice-count allowance is finite but large. The binding token, cost and concurrency ceilings the spec keeps are what bound it, and the spec says so. I did not trace which of the two converse call sites in universe_intelligence is the learning launch, so I accept the "one reply, one learning" reading on the strength of the existing limit of 2.

VERDICT: ADAPT


