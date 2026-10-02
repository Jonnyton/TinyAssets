# Tasks: huggingface-sign-in-source

Owner: Claude Code (connect-screen lane). One PR, draft until the lead stamps.
Credential handling: Codex refute on the design before code (done, ADAPT folded).

- [x] 1. Design + Codex refute of the storage/authority shape (`design.md`, review log).
- [x] 2. Hugging Face card as installed data (`free_source_presets.json`, `sign_in` block);
  key cards exclude sign-in sources.
- [x] 3. `request_from_user(sign_in_hosts=...)`: server-set discovery root.
- [x] 4. `source_sign_in` ingress operation; canonical-ask check before the post-sign-in
  pool confirmation (`source_connect.py`).
- [x] 5. Public Client ID Metadata Document route + exact middleware carve-out;
  `TINYASSETS_HUGGINGFACE_OAUTH_CLIENT_ID` override documented.
- [x] 6. Connect screen in the app: intro, guided sign-in, sign-in sources, subscription,
  folded "Paste a key" with inline terms; settings entry.
- [x] 7. Daily-cap card from installed `daily_cap_offers.json`, under daily-quota failures.
- [x] 8. Tests: ingress/OAuth with a fake Hugging Face, router fallback, UI harness,
  real-browser (`real_browser` marker).
- [ ] 9. Live proof: lead walks connect + daily-cap in the second account's browser.
- [ ] 10. Delta drafted from the built code (`specs/free-source-pooling`); sync and archive after live proof.
