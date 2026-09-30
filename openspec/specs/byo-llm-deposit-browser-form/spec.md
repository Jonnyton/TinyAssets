# byo-llm-deposit-browser-form Specification

## Purpose
A browser form, reached through an identity-provider sign-in, that deposits a
subscription credential without the token ever entering a chat. Written
2026-09-30 from the code on `main` (`tinyassets/connect_deposit.py`,
`auth/middleware.connect_deposit_routes_enabled`), not from the archived
proposal. The form is built but dark: no deployment sets its flag, and the app's
own connect flows are the live deposit paths.

## Requirements
### Requirement: The form is dark unless its flag is set
The `/mcp/connect` routes and their exemption from the MCP bearer challenge SHALL both exist only when `TINYASSETS_CONNECT_DEPOSIT_ENABLED` is truthy. When the flag is unset, neither the routes nor any change to the challenge SHALL exist. When the flag is set but the configuration is incomplete, every handler SHALL answer 503.

#### Scenario: A default deployment
- **WHEN** the flag is unset
- **THEN** `/mcp/connect/login` is not served and every `/mcp/*` path keeps the bearer challenge

### Requirement: The form deposits through the one owner-scoped writer
The form SHALL authenticate the owner with the same resource-server validator `/mcp` uses. It SHALL then deposit as that subject through `api.llm_deposit.connect_llm`, with no vault behaviour of its own. It inherits that writer's admin-only rule, its material checks and its ownership rule.

#### Scenario: Not the owner
- **WHEN** the signed-in subject does not hold `admin` on the target universe
- **THEN** the deposit is refused exactly as the chatbot path refuses it, and nothing is written

### Requirement: State travels in signed tokens, never cookies
The edge strips `Set-Cookie` on `/mcp*`, so the callback CSRF state and the deposit session SHALL be HMAC-signed, self-contained tokens with a server-side expiry. A state or session token that is missing, altered or expired SHALL be refused, and nothing SHALL be written. The OAuth `redirect_uri` SHALL be the fixed literal `https://tinyassets.io/mcp/connect/callback` and SHALL never be taken from the request.

#### Scenario: Tampered state
- **WHEN** the callback receives an altered or expired state token
- **THEN** it does not exchange the code, and no credential is written
