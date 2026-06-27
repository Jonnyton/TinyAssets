# Scorched Tanks Original-Media Sources

- Original disk: Scorched Tanks v1.90 public-domain ADF, listed by Retro32 at `https://www.retro32.com/gaming/amiga-public-domain/26042020710-scorched-tanks-v1-90-1994-dark-unicorn-amiga-public-domain-game`.
- Local source asset: `assets/scorched-tanks-v1.90.adf`.
- Source asset hashes:
  - SHA256 `E95E9EBFAC31A6BAB8C182E4DE0E53167C04424AB7B0733A071A2294CC17F953`
  - SHA1 `8797D9CE33DCAA5E39D78676258542C30F774A00`
  - MD5 `CA16CDF1F81DAFDE22157866F0CAF6C1`
- Browser launch asset: `assets/scorched-tanks-v1.90-autostart-30582ca3.adf` (`assets/scorched-tanks-v1.90-autostart.adf` is retained as a corrected compatibility alias).
- Launch patch: `S/Startup-Sequence` changes from `LoadWB\nendcli\n` to `Stack 65536\ncd :\nScorched_TanksV1.90\nendcli\n`; game executable and data assets are unchanged. The ADF was regenerated with `xdftool write` so the Startup-Sequence file header reports the full 44-byte script.
- Launch asset hashes:
  - SHA256 `30582CA3EE2B8CA8BCBCCE2C93A1BB139889971F7C057834ACC35ED10605C19F`
  - SHA1 `A037D9A60197AD24660B5E9B875EA968947EA136`
  - MD5 `2920BC77BE21984D65A6C4BD4AE446EC`
- Reference package: Scorched Tanks v1.85 on Aminet at `https://aminet.net/package/game/shoot/Scorch185`.
- Browser runtime: vAmigaWeb at `https://github.com/vAmigaWeb/vAmigaWeb` and `https://vamigaweb.github.io/`.
- Optional hosted firmware path: `licensed/kickstart-a500-1.3.rom`, intentionally absent from the repository. A deployment may provision this only under a rights-cleared Kickstart license.

This page launches the autostart ADF in vAmigaWeb from a browser-only TinyAssets result. The parent page fetches the same-site ADF and injects the bytes into the iframe so static hosts do not need cross-origin ADF headers. It first checks for a rights-cleared hosted A500 Kickstart 1.3 ROM, then falls back to the open AROS ROM path, then accepts a user-owned Kickstart ROM through a local file picker without uploading the ROM.

Compatibility finding, verified 2026-05-01: Scorched Tanks v1.90 has a valid Startup-Sequence header and reaches the AROS shell in vAmigaWeb. The launcher now mounts the injected ADF once through vAmigaWeb's guarded `insert_file(0)` path, unlocks audio, and avoids the prior repeated-reset loop. The AROS firmware path still does not reach playable Scorched Tanks. Exact-game acceptance remains `NEEDS_RIGHTS_CLEARED_FIRMWARE` until a deployment supplies a rights-cleared Kickstart-compatible ROM path and verifies live gameplay with input, sound, and a tank hit captured.

No proprietary Kickstart ROM is bundled. The browser-native artillery port is kept only as a labeled fallback and must not be reported by TinyAssets as the exact original game. Live fallback proof, 2026-05-01: on `https://tinyassets.io/play/scorched-tanks/index.html`, a real browser canvas click fired a Big Shot, audio state was `running`, and the shot hit Kade for 52.6 damage (`output/scorched-compat-hit-tank-audio-live.png`, `output/scorched-compat-hit-tank-audio-live.json`).
