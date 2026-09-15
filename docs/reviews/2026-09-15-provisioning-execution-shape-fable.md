# Cloud dependency execution: Fable5.1 shape review

September15,2026 UTC. Session31374, terminal exit0/223s, VERDICT ADAPT.
Read-only Claude Fable5.1 at resolver tree ec867fa4, amendment in primary tree.
Full output: repair-resolver-pip-configuration/TinyAssets/output/provisioning-execution-shape-fable.md.
Reviewer explicitly confirms this never-designed execution seam does not reopen
the three-round-capped checkout/push review. No runtime code or live action.

## Required corrections accepted after lead source check

- AGREE: provisioning consent after credentialed staging removal, before mount
  publication. Access mode must come from connection authority, not packet.
- AGREE: reuse held-descriptor bounded manifest readers; scratch/cache beneath
  lease root but outside content, covered by existing wipe/reconciliation.
- DISAGREE_EVIDENCE/completeness: fixed CONNECT443 set must include pypi.org,
  files.pythonhosted.org and registry.npmjs.org. Reject plain HTTP/other methods;
  use existing git pinned-address validation, broker counts bytes/connections.
- AGREE with correction: acquisition-only fixed proxy argv/flag admission;
  offline remains proxy-free. npm ignore-scripts still extracts tarballs, but
  the resolver jail cannot access checkout or credentials.
- AGREE with correction: two separate jail launches, broker fd only in first;
  add second descriptor-validated typed mount, not unrestricted extra binds.
- DISAGREE_CONCERN accepted: use workspace resource class, not ordinary16MiB
  code-node file limit for downloads. Existing Node RLIMIT experiment does not
  transfer to Chromium; actual jailed browser memory/sandbox proof required.

Reverified via docview on workspace.py408-453/877-991, resolver.py20-110,
node_sandbox.py1595-1725. No executable path is claimed by parser/builder tests.
Lead incorporated corrections in provisioning-execution-amendment.md; corrected
shape can be implemented. Independent exact-head runtime review remains ahead.

## Browser implementation sequence, not narrowed completion

Reviewer recommends image-supplied system Chromium+OS libraries as the initial
toolchain, user-chosen driver via manifest. Accept as a first delivery slice,
not proof of every user-selected browser/runtime. Governed digest-bound arbitrary
browser artifacts remain in the overall capability goal. Cloud user must produce
its own genuine captures; no operator-built private workflows or forged proof.

Later hardening: kernel quotas/cgroups and broker metrics. Browser artifact
admission is later implementation, not optional if needed for the full goal.
