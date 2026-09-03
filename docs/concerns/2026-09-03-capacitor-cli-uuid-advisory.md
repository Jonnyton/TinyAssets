# Capacitor CLI still resolves a vulnerable UUID library

**Filed:** 2026-09-03
**Verified:** 2026-09-03, Windows checkout, `cd mobile && npm audit --audit-level=high`
**Severity:** P2

## Source (verbatim)

```text
uuid  <11.1.1
Severity: moderate
uuid: Missing buffer bounds check in v3/v5/v6 when buf is provided - https://github.com/advisories/GHSA-w5hq-g745-h8pq
fix available via `npm audit fix --force`
Will install @capacitor/cli@8.4.3, which is a breaking change
node_modules/uuid
  xcode  >=0.9.2
  Depends on vulnerable versions of uuid
  node_modules/xcode
    @capacitor/cli  8.5.0 - 8.5.2-nightly-20260903T151257.0
    Depends on vulnerable versions of xcode
    node_modules/@capacitor/cli
```

## Re-verification and scope

The same run initially found one critical and three high advisories through the
unused `@capacitor/assets@3.0.5` build dependency. Removing it and refreshing the
lockfile eliminated every high/critical finding and upgraded
`@xmldom/xmldom` to 0.9.12. The remaining advisory is `uuid@7.0.3`, pinned by
`xcode@3.0.1` under `@capacitor/cli@8.5.1`.

This is build-time project-generation code; it is not bundled in the Android or
iOS app. The advisory's affected buffered UUID API is not a TinyAssets input
surface. `npm audit --audit-level=high` is green, but the moderate finding is
still real. Do not force an incompatible UUID major through an override without
upstream compatibility evidence. Resolve when Capacitor/xcode publishes a
compatible dependency update, then delete this concern.
