# Bounded image retention: live activation

September 19, 2026 UTC, production `workflow-droplet`; coordinating root.

PR3879 merged `7b51c6737419b244657ad5bc9085a91a8381d32c` after
required Tests35428345248 passed. Deploy35429292706 passed public
`mcp_public_canary.py --url https://tinyassets.io/mcp --assert-handles` and
protected `deployed_sha.py --assert-contains` at07:26UTC. Host installer
35429335555 succeeded; actual current bundle was
`7b51c6737419b244657ad5bc9085a91a8381d32c-da31d7adaeda1e56`.

Installed helper SHA256 matches reviewed source:
`bf156638135411535f4b2ba686e14d3fef95648cff992a0890081fbef2702e7b`.
Installed direct dry-run (no `--apply`, activation0, verified containerd path)
returned dry_run, four verified recoverable immutable candidates, six protected
image IDs, removed none, pressure93.636%. Session72630 exit1 is its documented
pressure status, not a test failure.

First guarded configuration attempt refused before editing: Windows CRLF left
a carriage return in the key argument. Root corrected transport normalization;
no product patch. The independently authorized direct installed helper pass
had both `--apply` and activation1 and completed, session16152 exit1:

- Removed only four verified registry-recoverable daemon image digests:
  `27ef44f918bc`, `ea3c6e97d800`, `494502b5ffff`, `7d7dee5ca114`.
- Pressure93.6362638696903% ->84.37654107669891%; status pressure_unmet
  honestly retains the75% low-water target/four-removal bound distinction.
- Protected current591888086d1b, rollback e123d61e8226/4d7d2f923ce2/
  7d6255d7459b and both sidecars. No volume/container removal.

Corrected configuration attempt session66250 exit0 used the existing verified
environment installer under fence then host-mutation lock, verified helper
hashes again, and set storage path `/var/lib/containerd` and retention apply1.
This enables subsequent installed retention invocations; no full disk-watch
service was used as a pretend dry-run. Both exact keys were read back, no other
environment values printed. Data volume mount remained
`/var/lib/docker/volumes/tinyassets-data/_data`.

Post-removal public handles probe through a transient systemd unit using the
existing EnvironmentFile returned exit0. Concurrent normal delivery release
then deployed `e0ca501c03fa9cc2296e0285425ecf9bbabace60` in35429610533;
its public handles/protected contains gates passed at07:34UTC. Daemon healthy,
sidecars unchanged. Follow-up direct pass70546 refused `host_mutation_busy`
during normal host bundle installation; it performed no further removal.
Installer35429679314 subsequently passed, actual bundle now e0ca501c with the
same runtime-closure digest. The ordinary disk-watch service then ran at07:35UTC:
retention apply=true, before/after78.9614855%, selected/removed empty,
status below_threshold and service exit0. This is the required next healthy
no-needless-removal tick, not a fabricated direct-pass success.

Fresh `df -B1 /var/lib/containerd` reports total52,626,063,360 and
available10,381,881,344 bytes. Earlier sampled available was6,987,440,128 bytes;
containerd asynchronous reclamation and concurrent deployment prevent attributing
every byte of that delta exclusively to the first cleanup. Exact observed
percentage improvement and four actual removal events are the causal receipt;
do not substitute summed virtual image sizes for physically reclaimed bytes.
Main specification synchronization and archive are recorded by this closeout.

This is host/cache evidence, not app-agent workflow acceptance or completion of
all resource constraints. Removed cache is recoverable by exact registry digest;
remote registry permanence is not promised. Disable through the same guarded
environment helper with exact0, then wait any bounded active pass to settle.

Closeout validation: `openspec validate uptime-and-alarms --type spec --strict`
passed; archived change validated before archive, and diff whitespace is clean.
Fullspec sweep45passed/1failed: unchanged `universe-custom-agents` requirement7
lacks SHALL/MUST. The file is identical to base e0ca501c (`git diff --quiet`
exit0); no unrelated correction is included. This is not a fullspec-green claim.
