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

## 2026-07-24T04:24:14Z — PASS

- **Backup source:** `tinyassets-data-2026-07-15T03-00-04Z.tar.gz`
- **Archive SHA-256:** `24f0489b7ca2e78aa670009d061fb9b931797fd3c3902fadffbfec847c326a68`
- **Representative member path (base64 UTF-8):** `LmNvZGV4Ly5sb2Nr`
- **Representative member SHA-256:** `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- **Drill Droplet:** ID `587165976`, IP `104.131.173.182`
- **Base Image:** `debian-13-x64`
- **Runtime Image:** `ghcr.io/jonnyton/tinyassets-daemon@sha256:10d4842c4d6243d031fbc97c7fc3f32540ce08040d0e5ff3f9750ccb4d63937b`
- **Size:** `s-2vcpu-2gb`
- **Probe:** green (MCP status via SSH port-forward to localhost:8001)
- **Cleanup:** Droplet DELETE confirmed before PASS publication
- **Run:** https://github.com/Jonnyton/TinyAssets/actions/runs/30066361115
