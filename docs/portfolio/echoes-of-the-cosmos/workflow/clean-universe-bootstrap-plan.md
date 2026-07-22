# Clean Workflow Universe Bootstrap Plan

Goal: create a fresh Echoes of the Cosmos universe in Workflow instead of attaching the public project to an old test universe.

## Why Clean

The canon docs have been used for testing before, but the current test universe may contain experimental state, old prompts, generated artifacts, or decisions that should not become public canon.

A clean universe gives Echoes a trustworthy public baseline.

## Inputs

- `canon/ECHOES_OF_THE_COSMOS.md`
- `canon/THE_RESONANCE_Magic_System.md`
- selected Reddit posts/comments after import policy exists

## Desired Initial State

The initial Workflow universe should contain:

- canonical source documents
- source provenance
- public/private status per source
- summarized canon index
- initial entity/faction/location graph if supported
- contribution rules
- canon promotion states

## Do Not Import Yet

- old generated test universes
- private conversation memories
- generated drafts from prior experiments unless explicitly selected
- old Reddit imports without attribution

## First Public Milestone

MVP Echoes universe is ready when:

- the two public canon docs are loaded as source truth
- Workflow can answer basic canon queries from those docs
- a new contribution can be proposed as a branch/change packet
- the change can be reviewed without being auto-promoted to canon
- public docs can be regenerated or updated from accepted canon

## Open Questions

- What is the canonical repo path for public Echoes?
- Should Workflow store the public canon docs directly, or mirror them from the Echoes repo?
- Should Reddit import be manual at first, or automated after the first clean universe works?
- What counts as accepted canon: Jonathan approval, contributor review, gate pass, or some combination?
