# App Store privacy policy is still an explicitly unfinished legal draft

**Filed:** 2026-09-03
**Verified:** 2026-09-03, public `https://tinyassets.io/legal/` plus PR #2798 working tree
**Severity:** P2

## Source (verbatim)

> “Draft v0 — pending securities-counsel confirmation. Defaults are best-effort,
> not legal advice.”

The same live page currently introduces its privacy disclosure with:

> “What the apps collect (web, Android, desktop).”

## Re-verification and scope

The App Store submission packet correctly points to
`https://tinyassets.io/legal#app-data`, and the public page contains both the
app-data disclosure and a contact section. However, the live page still omits iOS
because PR #2798 has not landed or deployed, and both the live and branch versions
state that the legal copy is a draft pending counsel.

PR #2798's working tree adds iOS to the data-handling scope and has automated site
checks, but merging it would not make the legal policy final. Do not publish App
Privacy answers or submit the app with this URL while representing the policy as
legally complete. Before submission, the founder must approve final legal copy or
obtain the legal review the page itself says is pending; then the change must land,
deploy, and be verified on the public URL.

This finding does not authorize changing legal text, merging the draft PR,
publishing privacy answers, or submitting to App Review.
