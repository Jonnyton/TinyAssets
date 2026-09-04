# iOS TestFlight preparation receipt

- **Verified:** 2026-09-03, App Store Connect API and signed-in App Store Connect
- **App version:** 1.0.0
- **Build:** 3
- **Upload delivery UUID:** `59f9e3ee-57b3-41c9-871b-91cb357b536f`

## Completed safely

- The API reported Build 3 as `VALID`, `APP_STORE_ELIGIBLE`, and exempt from
  non-exempt-encryption documentation.
- `POST /v1/betaBuildLocalizations` returned 201 and created one en-US beta-build
  localization containing the exact **What to Test** copy staged in
  `docs/ops/app-store-submission-packet.md`.
- `POST /v1/betaGroups/{id}/relationships/builds` returned 204 and associated
  Build 3 with the existing internal group named `Internal`.
- A follow-up read verified that the group contains Build 3 and has zero testers.
  No tester was added, so no invitation or notification was sent.

## Least-privilege boundary

The existing Developer-role App Store Connect key returned 403, "API key in use
does not allow this request," for each of these writes:

- creating the app-level beta localization containing the staged beta description;
- changing Build 3 `autoNotifyEnabled` from its current `true` value to `false`;
- selecting Build 3 through the App Store Version 1.0 build relationship.

Follow-up reads verified that Version 1.0 remains
`PREPARE_FOR_SUBMISSION`, uses manual release, and has no selected build. The
signed-in web session then expired at Apple's password screen. Completing these
three fields therefore requires founder reauthentication; no password was guessed
or retrieved.

No external TestFlight review, App Review submission, tester invitation, legal
declaration, or public release occurred.
