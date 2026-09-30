# byo-llm-deposit-surface Specification

## Purpose
How an owner puts their own Claude or Codex subscription into their universe's
credential vault. Written 2026-09-30 from the code on `main`
(`tinyassets/api/llm_deposit.py`), not from the archived proposal.

## Requirements
### Requirement: One owner-scoped writer holds every subscription deposit
Every subscription deposit SHALL go through `api.llm_deposit.connect_llm`: the chatbot operation, the in-app OpenAI device sign-in (`onboarding/openai_device.py`) and the browser deposit form (`connect_deposit.py`). No transport SHALL write an `llm_subscription` record any other way. The depositor SHALL be the authenticated request subject, never a payload field or environment value. The caller SHALL hold an explicit `admin` ACL row on the target universe, and a `write` grant SHALL NOT be enough. An unauthenticated caller, a non-admin caller and an unknown universe SHALL receive responses that do not reveal whether the universe or a credential exists. Only `claude` and `codex` SHALL be accepted, and any other service SHALL be refused before anything is written.

#### Scenario: A write collaborator is refused
- **WHEN** a caller holding only `write` on the universe deposits
- **THEN** they receive `not_found`, and no vault, ownership, custody, binding or serving state changes

#### Scenario: Unsupported service
- **WHEN** a deposit names a service other than `claude` or `codex`
- **THEN** it fails with `unsupported_service` and writes nothing

### Requirement: The material is checked before any write
Material SHALL arrive base64-encoded and SHALL be bounded before it is decoded. A Claude deposit SHALL decode to a UTF-8 token that starts with `sk-ant-` and contains no whitespace or `#`. Anything else, including the browser authorization code that people paste by mistake, SHALL be refused with a message that says the existing connection is unchanged. A Codex deposit SHALL be stored as a base64 `auth.json` string in a stamped record, never as decoded bytes. After a successful write the handler SHALL clear the service's "sign in again" card.

#### Scenario: The authorization code instead of the token
- **WHEN** an owner deposits the browser authorization code rather than the `sk-ant-` token
- **THEN** the deposit is refused before any write, and the working credential is unchanged

### Requirement: A credential belongs to its first depositor
A deposit into a service slot that another principal already owns SHALL be refused as `credential_ownership_transfer_unsupported`, leaving the existing record unchanged. The recorded owner's repeat deposit SHALL replace that one service slot in place and leave every other credential untouched.

#### Scenario: Re-deposit keeps the others
- **WHEN** the owner re-deposits Claude in a universe that also holds Codex, GitHub and HTTP credentials
- **THEN** only the Claude slot changes

### Requirement: The result is non-secret and names the serving re-point
A deposit SHALL NOT enable serving. Its result SHALL carry only status, service, the owner's agent binding id with its current revision, and the two-step re-point (`bind_serving_provider`, then `set_serving`). No response, log line or exception SHALL carry the token, the decoded material or any digest of it.

#### Scenario: A successful deposit
- **WHEN** a deposit succeeds
- **THEN** the reply names `bind_serving_provider` as the next step and holds no credential material
