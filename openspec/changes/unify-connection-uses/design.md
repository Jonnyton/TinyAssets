# Design: one connector, two uses (Slice 1)

This is section 1 of the vendor-neutral migration plan, trimmed to this slice.

## D1. One primitive: the universe connection

A compute source is a connection whose use is `model`. A platform is the same
object with use `call`. There is no separate LLM stack. The base is the
existing generic path:

- the `ConnectionLedger` (endpoint allowlist, auth scheme, grant, capabilities);
- the credential-blind broker;
- `authenticated_external_call`;
- the `connect_http` deposit;
- the pending-request rail.

The record is exactly what the user or agent supplied. The secret lives only
in the vault.

```
destination       the owner's name for it ("work-llm", "tasks")      (exists)
endpoint          host + method/path allowlist, exact or full         (exists)
auth              bearer | basic | header | oauth1a                   (exists)
constant_headers  {name: value}, applied by the broker                (NEW)
uses              call  -> authenticated_external_call                (exists)
                  model -> {wire, models, billing}                    (NEW)
```

Storage adds no table. `constant_headers` and `uses.model` are two new
`connection_capabilities` kinds (`constant_headers`, `model_use`), validated
on write and again on every read. `uses.call` is the default and is stored
implicitly.

## D2. `model.wire` is dialect data, not a vendor encoder

A bundled document in `tinyassets/providers/dialects/` declares, as closed
and validated data:

- `message_dialect`: `chat_messages | content_blocks`;
- `tool_dialect`: `chat_functions | none`;
- the `system` placement, checked against the encoder;
- the text path;
- any headers the wire itself needs;
- for tool dialects, the agent `envelope` (the former `agent_wire_shape.json`).

Only the two structural encoder pairs remain code. `PROTOCOLS` is built from
the documents under both the structural names and the aliases, and each
alias maps to the same object. Definition ids content-address the stored
protocol string, so rows keep their exact string. Comparisons go through
`same_dialect`.

## D3. `model.models` and `model.billing`

- `models` is a static list `[{id, tools, context}]`.
- `billing` is `free | flat`. `metered` is refused here with a pointer to the
  priced `model_discovery` source contract.

`DeclaredModelContract` gives the declaration the contract shape selection
and the executor already read:

- models are `unmetered`, with `availability_basis=owner_configured_contract`;
- the price components are the legacy three, with zero caps;
- inference is validated by the installed wire.

**Money floor (review round 1).** A declared billing is the requester's word,
never evidence of price. A priced `model_discovery` catalogue therefore always
wins at read time. A `model_use` is refused, in the same storage transaction,
on a connection that has one. It is also refused where the owner accepted
access with cost caps for the grant's model source.

`refresh_model_discovery` uses a `model_use` only when the connection has no
catalogue. It needs POST scope, not GET. It brackets with the same authority re-read, fetches
nothing, and returns the ordinary `DiscoverySnapshot`. Workflow evidence
persists it as a third contract kind, `declared`, which is re-validated on
reconstruction.

## D4. The request is the setup

```
write_graph target=pending_request operation=ask
  action {type:"connect", destination, auth_scheme, host/path|endpoints|hosts,
          uses:{model:{wire, models, billing}}, constant_headers:{...}}
```

The deposit half is validated by the `connect_http` code itself. A model use
needs a POST endpoint. The rail sentence names the models, the billing and
the headers.

Answering does five things in order:

1. deposit the key (`connect_http`, unchanged);
2. write the capabilities;
3. register the model source, reusing this grant's definition in the same
   wire;
4. if `_serving_llm_bound` is false, run `ensure_founder_serving` with
   `ModelAccess("explicit", <declared ids>, cost_caps=None)`;
5. leave a powered universe unchanged.

If a step fails after the deposit, the ask stays pending. Answering again is
idempotent. The price-source check runs at ask time and again before the
deposit. The rail sentence says the requester declared the models free or
flat, that TinyAssets cannot check it, and that any provider charge is billed
to the owner's key. It grants no platform spending.

`configure` (the agent's own write) may not create or change a model use.
Re-stating the owner-confirmed one is a no-op. A model or billing change is a
new `connect` ask.

## D5. Constant headers

Names are HTTP tokens that pass the broker's forbidden-header policy, so no
`Authorization`, `Host` or framing header is allowed. Nor is any credential or
session name (`key`, `token`, `secret`, `auth`, `passw`, `session`, `cookie`,
`signature`, `credential`). The driver removes any request header that
matches an auth header case-insensitively before it adds auth. Values are single-line
and at most 256 characters. A run of 32 or more key-like characters is
refused as a probable credential, because these headers are readable
metadata.

The broker merges them, case-insensitively, over the node's headers. The
driver then applies auth last. If the headers cannot be read, dispatch
fails loudly.

## D6. What this slice does not do

It adds no new top-level tool. The canonical handles and their operation
names are unchanged apart from `configure`. It has no OAuth2, command
runner or vendor deletion. It does not build a transform language. The
closed dialects plus pointer maps are the whole wire vocabulary.
