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

Canonical/package SHA-256 parity: `21ACDE5ECDA95A6A76C2F2A85C3076885A70B5FC86B3B0804F3AF103F7CB7FA1`.

## Remaining proof

OpenSpec task 4.1 is not complete. After this contract repair is reviewed, merged, and deployed, acceptance still requires a rendered conversation that selects public parents authored by at least one different user, publishes verified lineage, privately binds the child, and exports it. The current live commons population prevents that exact proof today.
