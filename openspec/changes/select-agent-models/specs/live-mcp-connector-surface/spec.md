## ADDED Requirements

### Requirement: Converse accepts non-authoritative current model choice
The authenticated converse handle SHALL accept optional model_choice using the
existing versioned preferences document. Omission SHALL use supported saved
preferences or preserve absent-policy legacy behavior. A current override SHALL
replace the entire current order without modifying saved defaults or authority.

#### Scenario: One-turn explicit choice
- **WHEN** an authorized owner supplies valid explicit model_choice
- **THEN** this turn captures that primary and exact fallback tail
- **AND** the saved row and generation remain unchanged

#### Scenario: One-turn automatic choice
- **WHEN** model_choice requests automatic mode
- **THEN** this turn clears the saved primary and uses eligible automatic ordering
- **AND** it does not append the old default as an explicit fallback

#### Scenario: Invalid or unauthorized choice
- **WHEN** the document is malformed, unsupported, outside supported owner scope or accepted authority
- **THEN** the runtime refuses before launch without widening access

#### Scenario: Cross-client compatibility
- **WHEN** the changed tool is tested through ChatGPT and Claude
- **THEN** both render structured results and final narration without wedging
- **AND** protected canary --assert-handles and deployed-SHA gates remain required
