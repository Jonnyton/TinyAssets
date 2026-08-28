# Tasks

## 1. Resolve operation (server)

- [ ] Add the owner-gated resolve handler: accepts credential *shape* + optional
      intent, returns a proposed policy, writes nothing.
- [ ] Refuse payloads carrying full credential values, so the
      no-transmission guarantee is enforced at the boundary.
- [ ] Narrow or reject any proposal broader than a hand-authored deposit can
      express (no host-wide, no wildcard path); fence the paste as data, and fail
      to resolve rather than deposit against an ungroundable host.
- [ ] Tests: unknown-service resolution, secret-bearing payload refused,
      non-owner gets the uniform not-found envelope, and an injected
      "use host X" line in the paste does not move the proposed host.

## 2. Shape extraction (client)

- [ ] Split a paste into candidate values, sending label + public prefix +
      length only; keep the remainder in the browser.
- [ ] Carry hostnames, URLs and field labels through as-is — already non-secret
      and usually decisive.
- [ ] Test: a paste with four OAuth values plus extras yields shape with no
      high-entropy material.

## 3. The one-box surface

- [ ] Replace the five-field card with one textarea + optional intent line;
      move the explicit fields behind a disclosure, pre-filled from the proposal.
- [ ] Deposit straight through with no confirmation step, then show the receipt
      sentence with change and remove attached.
- [ ] Test: a paste that resolves deposits with no further interaction; the
      receipt names the granted method/host/path and remove actually revokes.

## 4. Proof

- [ ] Live test through the deployed app: paste GitHub material with extra
      unused values, confirm, and have the universe open a real PR on the
      resulting connection.
- [ ] Sync the delta specs and archive.
