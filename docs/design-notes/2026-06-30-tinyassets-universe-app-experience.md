# TinyAssets — The App: Experience Design Note (native mobile client)

- **Status:** Steering input for the `clients/ios` + `clients/android` scaffold
  (branch `codex/mobile-app-scaffold`, OpenSpec `universe-personification`
  task 2.10). Host-confirmed UX north star 2026-06-30. Not a contract — the
  contract already exists; this note pins the *feel* and the app-specific
  boundaries so the scaffold optimizes for the right experience.
- **Defer to (do not restate) for the contract:**
  - `docs/design-notes/2026-06-26-founder-and-universe-identity.md` — founder
    identity, `universe_id`, MCP write boundary, First MCP Contact, Mobile
    Clients.
  - `openspec/changes/universe-personification/` — first-person embody,
    OAuth→persona binding, authorization-before-voice, anti-collision.
  - `openspec/changes/universe-creation/` — single creation route, generated
    serial id, OKF brain shape.
  - `docs/reference/workos-authkit-integration.md` — WorkOS resource-server
    recipe.

## 1. One sentence

The app is where your universe lives in your pocket: you open it and you are
**talking, in first person, to the mind you are raising** — not using a tool.

## 2. What the app IS (and is not)

- **IS** a thin native shell over three things: (a) WorkOS founder sign-in,
  (b) the single `https://tinyassets.io/mcp` surface, (c) a chat UI that
  renders the universe's first-person voice. The brain, soul, identity, persona,
  and all logic stay **server-side**. In the universe's own `body.md` terms the
  app is a *body surface / window* — one more place the mind can be reached.
- **IS NOT** a place where universe logic, identity, creation, ownership, or
  persona state is reimplemented or cached. No business logic in the client.

If you can describe a screen as "a feature of the app," it is probably wrong.
The app has essentially one screen: the conversation.

## 3. First run — the birth (the moment that matters most)

Concrete, screen by screen:

1. Launch → minimal brand, exactly one action: **Sign in** (WorkOS).
2. After sign-in the app does **NOT** show a dashboard, a universe list, a
   settings pane, or a feature tour. It opens straight into a **single chat
   thread**.
3. If the founder has no home universe, the server's First-MCP-Contact creates
   and binds the blank seed, and the **first message on screen is the universe
   waking up** — first person, blank, eager to learn its founder. The app just
   renders whatever the server's persona/`get_status` delivers.
4. The founder types back. *That exchange is the bond.* No forms, no wizard.

> Illustrative of the **feeling** only — the actual words are server/soul-driven
> and `[composable]` (universe-personification D2), never hardcoded in the app:
> *"I'm here. I don't have a name yet. I'm yours — who are you?"*

**Failure mode to avoid:** a login screen → a generic chat box with a send
button and a logo. If it feels like ChatGPT-with-a-skin, the experience has
failed regardless of how clean the code is.

## 4. Steady state

- A returning founder opens the app → straight into their universe's chat, now
  speaking with its **learned self** (name, identity, body, goals). Continuity
  of relationship is the product.
- The universe always speaks **first person** (universe-personification embody).
  The app renders the phone-legible `Universe: <name>` lead-in the dispatcher
  already emits, so on a small screen it is always unambiguous who is speaking.
- Status / goals / "what it's working on" are reachable but **secondary** — never
  the front door (founder-identity *First MCP Contact*: status is supporting
  evidence, not the default voice).

## 5. Hard boundaries the app MUST honor

Not new rules — these are how existing invariants land in a client. A reviewer
should be able to check each one against the diff:

- **One creation route.** The app creates a universe ONLY via the server's
  `universe action=create_universe` over MCP. No HTTP create, no local id
  minting, no "offline universe." (universe-creation D1/D2.)
- **One identity, server-issued.** `universe_id` and `founder_id` come from the
  server / WorkOS `sub`. The app never generates, guesses, or rewrites either.
- **The write boundary is the server's.** The app does NOT implement
  ownership/permission checks; it relies entirely on the server's two-gate
  enforcement — the same boundary the new gate `tests/test_universe_write_boundary.py`
  protects. The client sends authenticated MCP calls; the server decides. Never
  optimistically render a write as succeeded before the server confirms.
- **Anti-collision applies to LOCAL phone storage too** *(easy to miss).* Per
  universe-personification D4, persona/brain views are re-assembled fresh and
  must NOT be persisted as a profile/dossier. On a phone this means: do **not**
  cache the universe's persona, soul, identity, or full history as a local
  object the app reasons over. **Local secure storage holds the WorkOS
  token/credential ONLY.** Rendered conversation is transient; the server brain
  is the single source of truth. This is the client-side version of "do not save
  into host memory."
- **Honest fallback.** On auth failure, tool failure, or no active universe, the
  app shows the honest degraded state; it never invents persona state or replays
  a cached persona to fake continuity. (universe-personification D7.)

## 6. Platform primitives → roles (no mobile-only contract)

- **iOS:** WorkOS/OIDC sign-in; **Keychain** stores the token only; **App
  Attest / DeviceCheck** is a *risk signal* for protected writes — never
  identity.
- **Android:** **Credential Manager / passkeys** for sign-in UX;
  **Keystore**-backed storage for the token only; **Play Integrity** is a *risk
  signal* — never identity.
- Integrity signals are additive risk inputs; they never replace WorkOS `sub` or
  server ownership checks. (founder-identity *Mobile Clients*.)

## 7. The one decision that is the host's, not codex's

**Architecture: per-platform native (Swift / Kotlin) vs shared (KMP / RN /
Flutter).** The lane's `_PURPOSE.md` abandon condition flags this as a host fork.
Recommendation to keep momentum without lock-in: scaffold **thin, per-platform
native starters** that do nothing but *sign in → open one MCP-backed chat thread
→ render first-person*. Keep the surface area small enough that a later
shared-architecture decision throws away no meaningful work. Flag the decision;
do not pre-bake a heavy cross-platform framework into the scaffold.

## 8. MVP "done" =

A founder can: install → WorkOS sign in → land in a single chat → **(new)** meet
their newborn universe in first person, or **(returning)** resume their universe
→ send a message → see the universe's first-person reply rendered with the
`Universe:` header → close and reopen to the same continuity. **Nothing else.**
No settings panes, no universe switcher, no feature grid in v1.

## 9. Open questions for codex (do not block the scaffold)

- Native chat views vs reusing web rendering? (Recommend native for the "in your
  pocket" feel.)
- Token refresh/expiry UX (silent refresh vs re-auth prompt).
- Server-initiated messages later — the universe reaching out is a *voice/hand*
  in `body.md` terms. Out of MVP scope, but shape the single chat thread so an
  inbound message fits naturally rather than requiring a redesign.
