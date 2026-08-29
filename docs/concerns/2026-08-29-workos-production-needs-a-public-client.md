# The WorkOS production switch needs a public client that does not exist yet

**Severity:** P2 · **Filed:** 2026-08-29 after a live attempt and rollback
**Surface:** `/etc/tinyassets/env` on the droplet, WorkOS dashboard

## What was attempted

Production had been signing real users in against the WorkOS **staging** environment on an
`sk_test_` key. The founder enabled the Production environment (it required billing
details first — no charge, AuthKit is free to 1M MAU and custom domains at $99/mo are
optional), and I switched three variables and recreated the daemon:

```
WORKOS_API_KEY                      -> production key
WORKOS_AUTHKIT_DOMAIN               -> unassuming-environment-16.authkit.app
TINYASSETS_ONBOARDING_APP_CLIENT_ID -> client_01KW15P0PD1R9ETW3DTP8R9G3B
```

The canary went green and the app served the new issuer. **Sign-in then failed** with
`https://unassuming-environment-16.authkit.app/oauth2/error?error=application_not_found`.

Rolled back the same night; sign-in verified working again by loading the app and
reaching the founder's universe with its thread intact.

## The thing I had wrong

I assumed the client id came from the environment's **default Application**
(`client_01KW15P0PD1R9ETW3DTP8R9G3B` in production, `client_01KW15P07QYSMF9CY4XXXJN520`
in staging). It does not. The value that WORKS in staging is
**`client_01M0GQEWZ6VBKHQNRKXRMBT423`**, which:

* is **not** listed on the staging Applications page (that page shows only the default app), and
* has a much later id prefix (`01M0…` vs `01KW…`), so it was created long after the environment.

It is the **native/public client** recorded in `docs/host-actions.md`: PKCE S256, no
secret, loopback redirect, offline access. Production has no equivalent, so AuthKit
correctly reports the application as not found.

## What is needed

Create the matching public client in the **Production** environment, then set
`TINYASSETS_ONBOARDING_APP_CLIENT_ID` to its id. I could not find where the dashboard
creates one — Applications shows only the default — and the API has no listing endpoint
(`/applications`, `/user_management/applications`, `/oauth/applications`, `/sso/clients`
all 404), so the creation path needs to be found in WorkOS's docs or support rather than
guessed at. Guessing is what produced the outage above.

## Already done, and still valid for the next attempt

* Production environment enabled, billing added.
* Redirect URI `https://tinyassets.io/mcp/app` registered on the production default
  application and marked Default.
* Production API key created and known-good (the API answers with it; the environment
  correctly reports 0 users).
* Values recorded: environment `environment_01KW15P0GR4QQX1TPPW4SMJGTC`, default app
  `app_01KW15P0XBDWAXYGXHDTP9PKTR`, AuthKit domain
  `unassuming-environment-16.authkit.app`.

## What this cost

About four minutes of broken sign-in, on a surface used by one person (both accounts are
the founder's). The env file was backed up before the change, which is what made the
rollback a single copy.

**The lesson is the ordering, not the outage:** I verified the canary and the served
config — both of which passed — and treated that as proof. Neither exercises the
authorization server. The only test that would have caught this is the one that finally
did: click Sign in and see where it lands.
