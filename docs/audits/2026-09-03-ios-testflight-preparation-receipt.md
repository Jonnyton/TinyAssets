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
  manual release selected.
- The authenticated web session saved factual App Review Notes identifying the
  Capacitor shell's pinned URL, absent purchase/advertising/voice surfaces, and
  critical review paths. No credential or personal contact detail was entered.
- The authenticated web session set the app's base country or region to United
  States (USD) and confirmed a free (`$0.00`) price in all 175 displayed
  countries or regions. App availability was not configured.
- The authenticated web session completed and saved Apple's live age-rating
  questionnaire. The storefront rating is **18+** in 173 countries or regions
  and Brazil, **19+** in Korea, and **17+** on operating systems earlier than
  version 26 (with Apple's displayed regional exceptions). The higher-rating
  override aligns the listing with TinyAssets' documented legal minimum age.
- Apple Silicon Mac and Apple Vision Pro availability were both disabled and
  saved because those compatibility paths have not been tested. Public App Store
  distribution remains selected; storefront availability remains unset.
- Apple's **Add for Review** preflight was invoked after all safe preparation.
  It returned **Unable to Add for Review**, left the version in
  `PREPARE_FOR_SUBMISSION`, and created no review submission. Its exact global
  blockers are a 13-inch iPad screenshot, a 6.5-inch iPhone screenshot, Content
  Rights, a Privacy Policy URL, and Admin-provided privacy practices. Its exact
  page-level blockers are reviewer username/password plus first name, last name,
  email, and an international-format phone number.

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
contact/sign-in details. This Windows host cannot run Apple's simulator tooling:
the Xcode simulator inventory failed with `spawn xcrun ENOENT`. App Privacy
remains an unpublished four-type draft with blank policy URLs. Storefront
availability, DSA/trader status, and voluntary Accessibility Nutrition Labels
remain unset.

Content Rights remains a legal-attestation boundary. The app can access
third-party content, so Apple's "No" answer is not truthful; the "Yes" answer
also attests that the account holder has the necessary rights in every region,
which verified product behavior cannot establish. The modal was cancelled
without saving. The least-privilege reviewer identity could not be populated
because the secure local password vault was locked, and account-holder review
contact details remain personal facts that must not be guessed.

No external TestFlight review, App Review submission, tester invitation, legal
declaration, privacy publication, or public release occurred. The failed
preflight did not add the version to review.

## Follow-up: required screenshots and second preflight

On 2026-09-03 local / 2026-09-04 UTC, macOS CI run `33839432494` captured the
required iPhone and iPad images from Build 3's exact source. Both were validated,
visually inspected, uploaded, and verified after reloading App Store Connect. A
fresh **Add for Review** preflight no longer listed either screenshot; it still
failed without creating a submission on Content Rights, privacy URL/publication,
and the reviewer contact/sign-in block. Full evidence:
`docs/audits/2026-09-03-ios-app-store-screenshot-preflight-receipt.md`.
