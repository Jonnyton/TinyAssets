# DR Drill Log

Evidence log for disaster-recovery drills. Appended automatically by
`.github/workflows/dr-drill.yml` on each passing run.

Each entry: timestamp, backup source, drill Droplet details, probe result, run link.

<!-- entries appended below -->

## 2026-04-22T03:47:26Z — PASS

- **Backup source:** `tinyassets-data-2026-04-22T03-00-00Z.tar.gz`
- **Drill Droplet:** ID `566378236`, IP `159.65.46.178`
- **Size:** `s-2vcpu-2gb`
- **Probe:** green (direct HTTP to drill Droplet port 8001)
- **Run:** https://github.com/Jonnyton/TinyAssets/actions/runs/24758953250
