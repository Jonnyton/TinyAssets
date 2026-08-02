# V1 cross-user remix and private-binding evidence

Date: 2026-08-01
Environment: production `https://tinyassets.io/mcp` through the installed TinyAssets connector in a rendered Claude.ai conversation; local repair on Windows/Python 3.14.

## Intended customer journey

A browser-only user discovers public agent definitions, blends selected components, adds their own component, publishes the result, binds provider/resource/channel references privately in a writable universe, and exports a portable public definition containing no binding-private state.

## Rendered production result

The connector listed two public agent definitions, but both had the same authorship. No second authenticated creator identity or other-creator public definition was available, so the required cross-user blend was not fabricated and remains open.

Within that constraint, one user completed the rest of the journey:

- discovered and selected both public definitions;
- blended their evidence-planning and provenance behavior, added a fact-checking component, and published `V1 Intelligence Agent`;
- exported the resulting public definition successfully;
- received the correct authorization refusal when attempting to bind in a readable but non-writable universe;
- created the binding in their own writable universe and read it back as private, configured state;
- confirmed that provider and Slack address references remained in the private binding and did not alter the public definition or export.

No real provider credential was supplied, no outbound Slack message was sent, and no account fingerprint, private universe identifier, or private binding identifier is recorded here.

## Acceptance-discovered contract defect

The rendered client could not infer the ordinary remix lineage envelope from `write_graph.payload_json`. It attempted several invalid lineage shapes, received `lineage.<key> names no child component`, and ultimately published without structured lineage. It also had to retry private binding because the public description omitted the required `schema_version=1` and non-empty `name`.

The repair makes the advertised contract state:

- publish/remix definition requirements;
- lineage keyed by child component, with `definition_id`, `component_key`, and bounded `credit_share` entries;
- paired optional definition/component fingerprints;
- bind/update `schema_version=1` and non-empty `name` requirements;
- the rule that provider, resource, and channel references belong only in private binding JSON.

### Post-deploy rendered regression

After #2146 was included in a successful image build, production deploy, and public canary, a new Claude.ai conversation tested the contract without prior-chat context. Public discovery succeeded on its first call, but all three public definitions still had the same author, so other-creator remix remained unavailable.

The first remix mutation failed with `agent_validation_error`: `lineage.fact_check must be a non-empty JSON list`. Although the deployed prose said that each lineage value is a list and named the accepted fields, the rendered client constructed a single object with invented source-field names. Per the test instruction it made no corrective retry; private binding and export were therefore not attempted. Conversation: `https://claude.ai/chat/3105eae3-a31f-4296-8de5-84b8d00f2c57`.

The follow-up repair adds a copy-ready nested JSON example and explicitly says never to pass a single object as a lineage value. No real credential or outbound message was used, and private identifiers are omitted from this record.

### Follow-up release

Independent review approved exact head `2b896649f352f31ba8818552bbe98a8e4260ec21` with no findings. PR #2152 merged as `7256335820ef2247c4d7880455a67d88f5dc5c3d`; image run `30738561630` and production deploy/canary run `30738667081` passed. The production checks included health, cloud-worker startup, canonical MCP canary, exact-seven surface, direct-URL Access fencing, writer/receipt fencing, and release-receipt publication.

A new rendered Claude.ai conversation was submitted at `https://claude.ai/chat/6984f7db-b882-4856-9b72-46e67026e9de`, but the visible browser-control route reset before its final response could be read. The fallback browser route also failed to start, while the installed Chrome-extension route reported Chrome was not running. Therefore no rendered pass is claimed. This conversation was also not started in Claude.ai Incognito and cannot count as first-contact proof even if its response is later recovered.

## Local verification

RED before the repair:

```text
python -m pytest -q tests/test_universe_server_five_handles.py -k "advertises_agent_remix_lineage_contract or advertises_private_binding_contract"
2 failed, 12 deselected
```

GREEN after the repair:

```text
python -m pytest -q tests/test_universe_server_five_handles.py
14 passed
python -m ruff check tinyassets/universe_server.py packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/universe_server.py tests/test_universe_server_five_handles.py
All checks passed!
openspec validate agent-interchange-pipeline --strict
Change 'agent-interchange-pipeline' is valid
```

Initial #2146 canonical/package SHA-256 parity: `21ACDE5ECDA95A6A76C2F2A85C3076885A70B5FC86B3B0804F3AF103F7CB7FA1`.

Follow-up RED/GREEN on Windows with Python 3.14:

```text
python -m pytest tests/test_universe_server_five_handles.py::test_write_graph_advertises_agent_remix_lineage_contract -q
1 failed before the copy-ready example
1 passed after the repair
python -m pytest tests/test_universe_server_five_handles.py -q
14 passed
python -m pytest tests/test_agent_interchange.py tests/test_custom_agents.py tests/test_universe_server_five_handles.py -q
77 passed
python -m ruff check tinyassets/universe_server.py packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/universe_server.py tests/test_universe_server_five_handles.py
All checks passed!
python scripts/invariants_run.py --check mirror-parity
[OK] all 309 canonical file(s) mirror-matched
openspec validate agent-interchange-pipeline --strict --no-interactive
Change 'agent-interchange-pipeline' is valid
all active changes: 40 strict validations passed
```

Follow-up canonical/package SHA-256 parity: `FC58AC023D778593B990B43294F2E656B38A0D1C8E3C52CA8BE047E2ECDFC39C`.

## Remaining proof

OpenSpec task 4.1 is not complete. After this contract repair is reviewed, merged, and deployed, acceptance still requires a rendered conversation that selects public parents authored by at least one different user, publishes verified lineage, privately binds the child, and exports it. The current live commons population prevents that exact proof today.
