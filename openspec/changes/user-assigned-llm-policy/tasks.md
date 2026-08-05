# Tasks

Ordering note: 2.x depends on `constrain-set-engine-provider-authority` owning
the `allowed_providers` boundary. Do not implement a second writer of that field
— if that change has not landed, 2.x blocks on it rather than reimplementing it.
Building around it would repeat the surface-by-surface patching the host
rejected in favour of one unified authority-derivation model.

## 1. Selection surface (no credential path)

- [ ] 1.1 Add owner-facing provider selection on an existing advertised handle. Accept only identifiers of providers already enrolled and requester-owned for the authenticated owner + universe, resolved against `provider_work_enrollment`. Add no advertised handle; `mcp_public_canary.py --assert-handles` must be unchanged.
- [ ] 1.2 Make the surface structurally incapable of carrying a credential: no field accepts free-form secret material, and credential-shaped input is rejected rather than stored-and-ignored. Test with API-key-shaped, bearer-shaped, and base64 blob inputs and assert rejection plus no write to storage or logs.
- [ ] 1.3 Reject selection of providers that are unenrolled, revoked, expired, or owned by another principal, naming the offending provider and leaving any prior selection unchanged.
- [ ] 1.4 Persist the selection bound to owner + universe + assignment generation, never as free-standing mutable state.

## 2. Constraining resolution (depends on the allowed_providers owner)

- [ ] 2.1 On selection, set the routable set to exactly `{preferred} ∪ accepted_fallbacks` intersected with the enrolled set. Assert the persisted set is a *constraint*, not an ordering over a wider set.
- [ ] 2.2 Refuse routing to any provider outside the effective set even when every member fails. Mutation-probe this: force all members to fail with an unselected enrolled provider available, and assert it is never invoked.
- [ ] 2.3 Implement empty `accepted_fallbacks` as fail-closed with a named error; never widen to any available provider.
- [ ] 2.4 Implement resolution with the ENROLLED set as the only boundary: workflow policy resolves against it directly, and the universe selection applies only as the default when a workflow declares none. A workflow may name any enrolled requester-owned provider outside the universe default. An empty effective set fails closed naming which input produced it. Assert a workflow CAN use an enrolled provider the universe default omits — that case must stay green.
- [ ] 2.5 Verify the `converse` path consumes the same resolution, so a selected universe stops returning `missing: ["compute", "model_access"]` and begins answering.

## 3. Per-workflow policy

- [ ] 3.1 Add `preferred_provider` + ordered `accepted_fallbacks` to the Branch spec, plumbed through `graph_compiler` to node execution.
- [ ] 3.2 Add the same policy to agent bindings as private operational configuration. Assert it never appears in the public definition, the portable export, or remix lineage, and that a second-account remix carries none of it.
- [ ] 3.3 Add the same policy to the automation definition, inside the bytes `definition_digest` covers, so changing it requires a new definition and a rebind rather than mutating a live automation.
- [ ] 3.4 Assert policy is authority-bearing-but-frozen: a mutation attempt on a live automation's policy is rejected, and the digest is recomputed on rebind.

## 4. Decouple execution from the drain

- [ ] 4.1 Derive claimable executor class from `provider_binding_id` rather than a named `daemon_id` for requester-owned automations.
- [ ] 4.2 Prove a requester-owned automation is claimed and executed while the maintainer drain daemon has no live runtime instance — the exact live condition that blocked `automation_repo_7a09c311891da0f773aa1a8b024ecd19`.
- [ ] 4.3 Prove two active automations for one owner execute concurrently, neither waiting on the other's terminal receipt.
- [ ] 4.4 Confirm no maintainer-owned credential can be substituted when no compatible requester-owned executor is live; the automation must wait, visibly.

## 4b. Universe hosts many automations (unblocks scheduled execution)

- [ ] 4b.1 Confirm and record the live chain: `write_graph target=request` on a publicly created universe returns `universe_loop_not_declared`; `select_project_loop_daemon` returns None; `cloud_worker._register_worker_runtime` logs "no project loop daemon registered" and returns without raising; `runtime_instance_count` stays 0. This is the mechanical cause of scheduled execution never running.
- [ ] 4b.2 Move loop declaration off the universe scalar: an owner may declare and change automation loops AFTER birth through the advertised handles. Any universe-level default becomes a mutable set, never a write-once value. Add no advertised handle.
- [ ] 4b.3 Assert a universe hosts two automations of different kinds simultaneously, and that declaring the second neither replaces nor invalidates the first.
- [ ] 4b.4 Make an undeclared loop actionable rather than silent: the queue refusal names the missing declaration and the action supplying it, and worker registration reports the skip instead of returning quietly.
- [ ] 4b.5 Re-run the live walk end to end and confirm the created automation reaches an active activation and produces a terminal receipt.

## 5. Actionable health

- [x] 5.1 Populate `health.blocker` and `health.next_action` for every BLOCKED state (stopped, paused, activation_stopped, no_progress). Assert non-null for `activation_stopped`, which today returns null for both, and assert a normally scheduled `waiting` automation stays unblocked — healthy idling must not become a false alarm.
- [x] 5.2 Assert the blocker names the missing thing and the next action names what would resolve it, rather than restating the state.

## 6. Evidence and rollout

- [ ] 6.1 Focused tests, surrounding suites, Ruff, strict OpenSpec validation, and the packaged-mirror parity check.
- [ ] 6.2 §14 concurrency/load proof for multi-automation execution under the new executor selection, with recomputable raw evidence; shaped or mocked execution is `not_run`, not a pass.
- [ ] 6.3 Dual-family review (latest model of both families) before deploy, per the standing gate for security-adjacent authority changes. A finding that any credential can reach the selection surface is blocking.
- [ ] 6.4 Rendered connector `ui-test`: an owner selects providers in a real chatbot conversation, then converses with their universe and receives a reply. Direct MCP calls are supporting evidence only.
- [ ] 6.5 Rendered proof of a scheduled automation running with the owner's machine off, and of two automations running concurrently.
- [ ] 6.6 Post-deploy canaries including `--assert-handles`; record dated post-fix organic-use evidence, or leave an explicit monitoring row stating none exists yet.
- [ ] 6.7 Sync delta specs and archive; retire the STATUS row in the same lane.
