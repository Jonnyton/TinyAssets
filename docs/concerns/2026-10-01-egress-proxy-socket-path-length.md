---
severity: P3
title: The universe egress proxy cannot start when its socket path exceeds Linux's 108-byte limit
filed: '2026-10-01'
summary: '`universe_egress.ensure_proxy` binds `<data_dir>/.universe-sidecars/<universe>/egress-<pid>.sock`. Linux caps an AF_UNIX path at 108 bytes, so on a host whose data dir plus universe id run past about 67 bytes the proxy raises `OSError: AF_UNIX path too long`, and that universe''s bash gets no network. Production `/data` is far under the cap.'
---

# The egress proxy socket path can exceed the AF_UNIX limit

**Filed:** 2026-10-01, while taking over #4174 (harness S3a), which landed as `79bc52c5`.

## What happens

- `tinyassets/universe_egress.py` `ensure_proxy` (on main at `79bc52c5`) builds the socket path as `root.parent / UNIVERSE_SIDECARS_DIR / root.name / f"egress-{os.getpid()}.sock"`. `EgressProxy.__init__` then calls `server.bind(str(path))`.
- Linux limits `sun_path` to 108 bytes including the trailing NUL. The fixed parts (`/.universe-sidecars/`, `/egress-`, a pid of up to 7 digits, `.sock`) take about 40 bytes. That leaves about 67 bytes for the data dir plus the universe id.
- Observed: the stock Linux oracle (`scripts/linux_oracle.py`) puts pytest's tmp under `/tmp/oracle-tmp/pytest-of-root/pytest-0/<test name>/`. Every egress test there failed with `OSError: AF_UNIX path too long` at `server.bind`. CI's `/tmp/pytest-of-runner/...` is shorter, which is why CI passed.
- Production is not affected today: `TINYASSETS_DATA_DIR=/data`. A daemon host with a long home-relative data dir, such as `/home/<user>/.local/share/tinyassets/...`, plus a long universe id would hit it. That universe's bash would then have no network, because `ensure_proxy` raises.

## Obvious fix (not built)

Bind under a short per-process runtime dir with a fixed-length name derived from the universe, not from the full path. For example `$XDG_RUNTIME_DIR/ta/` (or `/tmp/ta-<uid>/`, mode 0700) plus `sha256(universe_dir)[:16].sock`.

That keeps the socket outside the universe, which is the point of `.universe-sidecars` after the gpt-6-astra REJECT folded into #4174. It also bounds the path length regardless of the data dir. Any jail bind of the socket follows the new path unchanged, because the jail sees only `/tmp/.ta-egress.sock`.
