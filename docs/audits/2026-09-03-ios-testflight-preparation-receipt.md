# iOS TestFlight preparation receipt

- **Verified:** 2026-09-03, App Store Connect API and authenticated App Store
  Connect web session
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
- The authenticated web session saved the staged app-level beta description and
  the verified marketing URL `https://tinyassets.io`.
- The authenticated web session selected Build 3 for App Store Version 1.0 and
  saved the relationship. The version remains `PREPARE_FOR_SUBMISSION` with
  manual release selected; **Add for Review** was not used.
- The authenticated web session set the app's base country or region to United
  States (USD) and confirmed a free (`$0.00`) price in all 175 displayed
  countries or regions. App availability was not configured.

## Automatic-notification finding

The existing Developer-role App Store Connect key returned 403, "API key in use
does not allow this request," for each of these writes:

- creating the app-level beta localization containing the staged beta description;
- changing Build 3 `autoNotifyEnabled` from its current `true` value to `false`;
- selecting Build 3 through the App Store Version 1.0 build relationship.

Reauthentication made the beta-description and version-build writes available.
The live internal-group settings exposed manual versus automatic **build
distribution**, and the Build 3 pages exposed group membership and test details,
but neither exposed an automatic tester-notification control. Apple documents
**Automatically notify testers** in the external-testing flow. No external group
or tester exists, the internal group remains on manual distribution for Xcode
builds, and Build 3 has zero testers, so the API's residual `true` flag has no
recipient or external-test path on which to act. No group was removed or recreated
merely to probe this setting.

## Remaining boundaries

The product listing still has no authentic iPhone screenshots or App Review
contact/sign-in details. App Privacy remains an unpublished four-type draft with
blank policy URLs. Age rating, content-rights, availability, DSA/trader status,
Accessibility Nutrition Labels, and Mac/Vision distribution choices were left
unchanged because they require device evidence or personal/legal/product-owner
judgment.

No external TestFlight review, App Review submission, tester invitation, legal
declaration, privacy publication, or public release occurred.
