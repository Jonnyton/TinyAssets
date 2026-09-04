# iOS App Store screenshot and preflight receipt

- **Verified:** 2026-09-03 local / 2026-09-04 UTC
- **Environment:** GitHub-hosted `macos-15`, Xcode 26.3, iOS Simulator; authenticated
  App Store Connect web session
- **App:** TinyAssets, Apple ID `6808434444`, Version 1.0, Build 3
- **Build 3 source:** `76d795a1a3794fc3f3112121a063ca21b3175ce0`
- **Capture workflow:** `iOS build` run `33839432494`, success at
  `2026-09-04T05:18:40Z`

## Authentic capture evidence

The manual workflow checked out Build 3's exact source separately from the capture
tooling, generated the native Capacitor iOS project, compiled its unsigned simulator
app with Xcode 26.3, installed and launched `io.tinyassets.app` on each required
simulator class, and captured the rendered app. The capture gate rejected wrong pixel
dimensions or an alpha channel before artifact upload.

| Display | File | CI validation | SHA-256 |
|---|---|---|---|
| 6.5-inch iPhone | `iphone-6.5.jpg` | `1284x2778`, RGB/no alpha | `6f123b4dbf1d11c26b676cdb53d537d6b7145da8aba407d7ba560d186b50a03d` |
| 13-inch iPad | `ipad-13.jpg` | `2064x2752`, RGB/no alpha | `a0be01762913af892862bde56be538a6f744aebbc740829dbc2b9f63783fe3ba` |

Both images were visually inspected after download. Each shows the real signed-out
TinyAssets landing screen with the iOS status bar, TinyAssets title and copy, **Sign
in** control, and Privacy policy / Terms links. There is no personal data, credential,
debug UI, transient error, notification, or microphone indicator.

## App Store Connect evidence

- Uploaded `iphone-6.5.jpg` to the **6.5-inch iPhone** set. The portal displayed
  `1 of 10 Screenshots` and named the draggable item; the count and item survived a
  full page reload.
- Uploaded `ipad-13.jpg` to the **13-inch iPad** set. The portal displayed
  `1 of 10 Screenshots` and named the draggable item; the count and item survived a
  full page reload.
- A fresh **Add for Review** preflight was then run. It returned **Unable to Add for
  Review** and did not create a submission. Neither screenshot appeared in the new
  blocker list.
- The separate **App Review** page was opened immediately afterward and still showed
  only “Items you submit to App Review will appear here,” with no submission item.

The remaining global blockers shown by Apple are Content Rights, Privacy Policy URL,
and Admin-published privacy practices. The remaining page-level blockers are reviewer
username/password and reviewer first name, last name, email, and international-format
phone number. The dedicated `play-review@tinyassets.io` password was verified in Google
Play's saved `Play Reviewer` record and accepted by Apple's form during preparation,
but Apple will not persist the version page until the separate contact block is
complete. The known contact name/email need not be re-entered by the founder; the only
unknown contact datum is the international-format phone number.

No App Review submission, TestFlight invitation, public release, privacy publication,
Content Rights attestation, or legal declaration occurred.
