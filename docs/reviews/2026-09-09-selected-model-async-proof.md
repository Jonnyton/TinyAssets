# Selected-model discovery without blocking ingress

September 9, 2026, 23:10 UTC. Local implementation; no deployment or app
activation claimed. Extends the selected HTTP text executor reviewed at83b19b49.

The router uses an async serving-authority entrypoint for a requested model.
It validates the authentic request, owner, serving agent/revision and exact
accepted candidate under a short shared admission fence. It then releases that
fence before awaiting the existing per-loop discovery single-flight. Only the
HTTP discovery worker moves threads; thread-owned assignment admission stays on
the ingress thread. No SQLite read transaction spans the network request.

After discovery, the normal validator rechecks the request, agent, full current
assignment/member/custody chain and live discovery source before emitting trusted
model facts. The preflight chain and agent must equal the post-discovery facts.
The existing slot-bound prelaunch recheck and launch-only accounting remain.
Public callers supply only ModelRef; neither authorization entrypoint accepts
caller-provided catalogues, model facts or preflight results. A private helper
shares the final validator; it is not a new token/provenance scheme.

Legacy unselected calls retain their synchronous entrypoint and differential
tests. Synchronous selected callers retain the previous fenced behavior; the
async router no longer uses that network-blocking path. HTTP inference itself
is still synchronous inside the existing executor, and full agent tools, safe
continuation, policy persistence, model picker and public activation are still
unfinished. This slice does not claim those capabilities.

Nine new selected-router cases cover responsive ingress, a real exclusive
assignment writer and SQLite write transaction while discovery waits, request/
agent/assignment/grant/profile changes during that interval, cancellation with
one retained discovery flight and zero cancelled launches, and invalid member
references before any GET. A tenth snapshot regression counts catalogue request
duration itself toward the five-minute freshness window. Synthetic transport,
real local stores and real router/HTTP encoder; not a live account test.

Windows Python3.14, September9: focused selected/snapshot group69passed;
16-file integration group452passed/3skipped in29.89s. Command:

`python -m pytest -q tests/test_selected_model_authority.py tests/test_config.py
tests/test_open_serving_bind.py tests/test_provider_serving_binding.py
tests/test_provider_served_router.py tests/test_served_authority_shared_chain.py
tests/test_served_launch_accounting.py tests/test_serving_manifest_publication.py
tests/test_provider_assignment_manifest.py tests/test_model_discovery_capability.py
tests/test_discovery_snapshot.py tests/test_discovery_http.py
tests/test_catalog_decoders.py tests/test_model_policy.py
tests/test_api_key_http_provider.py tests/test_mirror_parity_gate.py --tb=short -rs`

Windows skips: concurrent shared file readers, POSIX bubblewrap and optional real
Codex credential fixture. Ruff and git diff --check pass. The403-file plugin
runtime build/import probe passes. Supplemental Ubuntu Python3.11.15 runs the
same16 files through the external-temp receiver-linux-proof.sh harness:
454passed/1skipped in80.74s, only the optional real-Codex fixture skipped and one
existing LangChain deprecation warning. Independent Claude review83041 approved
exact9e19a7b8 after311s, reproducing51 selected-model cases. Full result and
optional-nit disposition are in selected-model-async-review.md.

The required Docker oracle is now running through an already-installed native
Ubuntu engine (29.1.3 linux), not the failed Windows Desktop engine. Initial
oracle invocation could not follow the Windows absolute worktree gitdir; setting
process-local GIT_DIR to the existing admin directory's /mnt/c equivalent and
GIT_WORK_TREE to the feature checkout resolved that without changing git files.
It printed exact9e19a7b8 then began building the normal oracle image. Result
pending; no push/landing claim. Neither Docker Desktop data nor settings changed.
