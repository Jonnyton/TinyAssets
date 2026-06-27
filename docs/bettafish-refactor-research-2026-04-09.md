# BettaFish Deep Dive For TinyAssets

Date: 2026-04-09

Repository researched: [666ghj/BettaFish](https://github.com/666ghj/BettaFish)

License note: BettaFish is GPL-2.0. Treat this document as architectural research. Do not copy BettaFish code into this project unless licensing is reviewed and approved separately.

## Why this matters

BettaFish is not valuable to us because it is a perfect system. It is valuable because it proves a stronger standard for long-form AI output than most multi-agent projects ever reach. Its best subsystem does not trust raw model output, does not collapse the pipeline into one prompt, and does not pretend loose markdown is a sufficient intermediate artifact.

That is the level we should steal in spirit.

The part worth studying is not the marketing language around "multi-agent." The part worth studying is the report pipeline discipline:

- explicit intermediate representation
- chapter-level generation rather than one monolithic write
- durable per-stage artifacts
- validation and sanitization before render
- multi-model rescue paths when a generation fails
- event streaming and resumable task tracking

The parts we should reject are equally important:

- log-scraping as the core coordination protocol
- high duplication across agents
- oversized dependency surface
- mixed framework sprawl
- direct SDK-centric primary writing path, which conflicts with this project's rules

## Executive judgment

BettaFish is a layered analysis-and-report system with one genuinely strong subsystem: `ReportEngine`.

The system is not a frontier orchestration runtime. It is closer to:

1. three parallel specialist analysis engines
2. a moderator layer that synthesizes their outputs through a forum log
3. a structured report compiler that turns the outputs into validated HTML and export artifacts
4. an optional crawler stack that populates the private-data side

For TinyAssets, the direct opportunity is not "build BettaFish for fiction." The real opportunity is:

1. replace lightweight text-only generation paths with an IR-first authoring pipeline
2. make deliberation and drafting durable, inspectable, and resumable
3. enforce hard acceptance gates on chapter and scene output
4. split synthesis, planning, drafting, validation, and rendering into explicit stages
5. preserve provenance from canon facts to generated prose

If we do that well, this project becomes materially more serious.

## What BettaFish Actually Is

### 1. Orchestration shell

Key files:

- [app.py](https://github.com/666ghj/BettaFish/blob/main/app.py)
- [config.py](https://github.com/666ghj/BettaFish/blob/main/config.py)
- [.env.example](https://github.com/666ghj/BettaFish/blob/main/.env.example)
- [docker-compose.yml](https://github.com/666ghj/BettaFish/blob/main/docker-compose.yml)

Observed design:

- Flask is the control surface.
- Multiple Streamlit apps are launched as subprocesses.
- Report generation is exposed through a Flask blueprint with SSE.
- Configuration is centralized with `pydantic-settings`.
- Different engines are assigned different models and providers.

Usefulness for us:

- centralized typed config is worth copying
- stage-specific model routing is worth copying
- the Flask + Streamlit + SocketIO mix is not worth copying

### 2. Three specialist engines with near-identical loops

Key files:

- [QueryEngine/agent.py](https://github.com/666ghj/BettaFish/blob/main/QueryEngine/agent.py)
- [MediaEngine/agent.py](https://github.com/666ghj/BettaFish/blob/main/MediaEngine/agent.py)
- [InsightEngine/agent.py](https://github.com/666ghj/BettaFish/blob/main/InsightEngine/agent.py)

Observed design:

- each engine builds structure first
- each section or paragraph gets its own search or evidence retrieval step
- each section then gets summary and reflection passes
- each engine writes an engine-specific markdown report
- the engine loops are highly similar, with tool variation more than orchestration variation

Usefulness for us:

- section-level iterative drafting is worth copying
- reflection loops are worth copying
- per-engine specialization is worth copying
- duplicated orchestration code is not worth copying

### 3. Forum coordination via logs

Key files:

- [ForumEngine/monitor.py](https://github.com/666ghj/BettaFish/blob/main/ForumEngine/monitor.py)
- [ForumEngine/llm_host.py](https://github.com/666ghj/BettaFish/blob/main/ForumEngine/llm_host.py)
- [utils/forum_reader.py](https://github.com/666ghj/BettaFish/blob/main/utils/forum_reader.py)
- [tests/test_monitor.py](https://github.com/666ghj/BettaFish/blob/main/tests/test_monitor.py)

Observed design:

- engine logs are watched rather than agents messaging each other directly
- only selected summary-node outputs are admitted into the forum
- a host agent synthesizes multiple agent speeches into new guidance
- host guidance is persisted back to `forum.log`
- downstream engines can read latest host speech as steering context

What is good here:

- they identified the right problem: agent collaboration needs synthesis, not just parallel outputs
- they test the filter layer so garbage log lines do not become collaboration content
- they create a moderator role rather than allowing raw agent chatter to flood the system

What is weak here:

- the bus is implemented through log parsing, which is brittle
- JSON repair and line cleanup are compensating for the transport being the wrong abstraction
- coordination semantics are implicit in strings instead of explicit in typed messages

Translation for us:

- keep the moderator pattern
- reject log scraping
- replace it with a typed deliberation ledger

### 4. ReportEngine is the core gem

Key files:

- [ReportEngine/agent.py](https://github.com/666ghj/BettaFish/blob/main/ReportEngine/agent.py)
- [ReportEngine/nodes/document_layout_node.py](https://github.com/666ghj/BettaFish/blob/main/ReportEngine/nodes/document_layout_node.py)
- [ReportEngine/nodes/word_budget_node.py](https://github.com/666ghj/BettaFish/blob/main/ReportEngine/nodes/word_budget_node.py)
- [ReportEngine/nodes/chapter_generation_node.py](https://github.com/666ghj/BettaFish/blob/main/ReportEngine/nodes/chapter_generation_node.py)
- [ReportEngine/ir/schema.py](https://github.com/666ghj/BettaFish/blob/main/ReportEngine/ir/schema.py)
- [ReportEngine/ir/validator.py](https://github.com/666ghj/BettaFish/blob/main/ReportEngine/ir/validator.py)
- [ReportEngine/core/chapter_storage.py](https://github.com/666ghj/BettaFish/blob/main/ReportEngine/core/chapter_storage.py)
- [ReportEngine/core/stitcher.py](https://github.com/666ghj/BettaFish/blob/main/ReportEngine/core/stitcher.py)
- [ReportEngine/flask_interface.py](https://github.com/666ghj/BettaFish/blob/main/ReportEngine/flask_interface.py)
- [ReportEngine/scripts/validate_ir.py](https://github.com/666ghj/BettaFish/blob/main/ReportEngine/scripts/validate_ir.py)
- [report_engine_only.py](https://github.com/666ghj/BettaFish/blob/main/report_engine_only.py)
- [tests/test_report_engine_sanitization.py](https://github.com/666ghj/BettaFish/blob/main/tests/test_report_engine_sanitization.py)

Observed design:

- report generation is broken into stages
- document design and chapter sizing happen before chapter writing
- each chapter is generated as structured JSON, not free-form text
- output is parsed, repaired, sanitized, and validated before persistence
- raw and cleaned artifacts are both stored
- the final document is composed from validated chapter payloads
- rendering is a separate concern from generation
- event history is replayable for SSE clients

This is the single most valuable pattern in the repo.

### 5. MindSpider crawler stack

Key files:

- [MindSpider/main.py](https://github.com/666ghj/BettaFish/blob/main/MindSpider/main.py)
- [MindSpider/README.md](https://github.com/666ghj/BettaFish/blob/main/MindSpider/README.md)

Observed design:

- broad topic collection and deeper crawl paths are split
- crawler setup is operationally heavy
- social-platform breadth is large

Usefulness for us:

- the idea of autonomous background ingestion is useful
- the exact crawler system is mostly irrelevant to this fiction project
- compliance and operational risk are too high to treat as a simple transplant

## Highest-Value Patterns To Bring Into TinyAssets

## Pattern A: IR-first authoring

### Why this is the most important import

BettaFish refuses to treat markdown as the source of truth. That is the real upgrade.

For TinyAssets, the equivalent move is:

- stop treating raw model prose as the only meaningful artifact
- represent authored output as structured narrative IR
- render prose from that IR
- persist both raw generation output and validated structured output

### Required implementation in this project

Build a `Narrative IR` layer with at least these levels:

1. `Document`
2. `Chapter`
3. `Scene`
4. `SceneBlock`

Minimum root fields:

- `version`
- `workId`
- `generatedAt`
- `metadata`
- `chapters`

Minimum chapter fields:

- `chapterId`
- `title`
- `anchor`
- `order`
- `summary`
- `sceneIds`
- `blocks`

Minimum scene fields:

- `sceneId`
- `chapterId`
- `order`
- `povCharacterId`
- `locationId`
- `timelinePosition`
- `purpose`
- `entryState`
- `exitState`
- `factRefs`
- `blocks`

Minimum `SceneBlock` types:

- `narrative`
- `dialogue`
- `actionBeat`
- `interiorBeat`
- `transition`
- `epigraph`
- `callout`
- `continuityNote`

Every fact-bearing scene or block must support provenance back to this project's canon structures. At minimum, use references that can resolve back to `FactWithContext` records or equivalent notes entries. No final prose block should be orphaned from the canon/evidence path that justified it.

### Non-negotiable anti-cheat rules

- Do not allow "chapter is just markdown" as the internal representation.
- Do not allow scene generation to skip validation because "the prose looked good."
- Do not allow final manuscript rendering directly from raw model output.
- Do not allow fact provenance to disappear between planning and prose.
- Do not allow the validator to become a warning-only observer. Invalid IR must fail the stage.

### Required storage layout

Every run must persist a durable ledger, for example:

```text
output/<run_id>/
  manifest.json
  planning/
    book_plan.json
    chapter_plan.json
    scene_plan.json
  chapters/
    010-opening-movement/
      stream.raw
      chapter.json
      validation.json
      rescue.json
    020-second-movement/
      stream.raw
      chapter.json
      validation.json
      rescue.json
  compiled/
    document_ir.json
    manuscript.md
    editorial.html
```

If a future builder proposes a system that only stores the final markdown or docx, that proposal is below standard and should be rejected.

## Pattern B: Stage separation with hard contracts

BettaFish separates template selection, layout design, word budget, chapter generation, composition, and rendering. That discipline is worth importing directly.

For TinyAssets, the analogous stages should be:

1. canon pack assembly
2. book architecture selection
3. chapter outline generation
4. scene plan generation
5. scene drafting
6. chapter composition
7. continuity validation
8. manuscript composition
9. output rendering

Each stage must accept and emit typed payloads. A stage that accepts "misc prompt text" and emits "misc markdown text" is not a real stage boundary.

### Required contracts

- `canon pack assembly` emits typed facts, unresolved contradictions, and allowed invention budget
- `book architecture selection` emits narrative structure and target movement map
- `chapter outline generation` emits ordered chapter specs with scene targets
- `scene plan generation` emits scene specs with purpose, stakes, character delta, and fact refs
- `scene drafting` emits scene IR, not manuscript markdown
- `continuity validation` emits pass or fail plus machine-readable defects
- `rendering` never invents content; it only transforms validated IR

### Non-negotiable anti-cheat rules

- No stage may silently absorb malformed input and keep going.
- No stage may collapse multiple responsibilities into one "smart" prompt.
- No stage may invent canon repairs without surfacing them as explicit issues.
- No renderer may mutate narrative meaning.

## Pattern C: Typed deliberation bus, not log scraping

BettaFish correctly discovered that parallel specialists need a synthesizer. The implementation is too brittle. We should build the stronger version.

### Required implementation in this project

Create a persisted deliberation model with records such as:

- `proposal`
- `objection`
- `evidence`
- `continuity-risk`
- `host-directive`
- `open-question`
- `decision`

Each message record should include:

- `messageId`
- `runId`
- `round`
- `speaker`
- `messageType`
- `summary`
- `details`
- `factRefs`
- `targetSceneIds`
- `severity`
- `createdAt`

This should be stored through the project's approved persistence path, not as ad hoc log strings. Graph state should accumulate these via `TypedDict` plus `Annotated[list, operator.add]`, consistent with project rules.

### Host/moderator requirements

The host agent should:

- synthesize only persisted typed messages
- resolve conflicts explicitly
- produce directives with target scope
- identify unresolved canon contradictions
- emit machine-readable action items for the next drafting round

### Non-negotiable anti-cheat rules

- No free-form untyped "forum transcript" as the source of truth.
- No scraping of stdout or log files as the coordination protocol.
- No host message without structured targets and defect classes.
- No claim may lose its fact references when promoted into a directive.

## Pattern D: Durable rescue chain for bad model output

BettaFish's chapter generator does something many systems avoid because it is annoying: it treats malformed output as normal enough to engineer around without lowering the quality bar.

That pattern is correct.

### Required implementation in this project

For any stage that depends on model-structured output:

1. capture raw output exactly
2. attempt strict parse
3. run deterministic repair
4. re-validate
5. if still invalid, try the rescue model path
6. if still invalid, fail loudly and persist the failure artifact

This project's primary writer cannot use direct API SDKs. The writer and rescue paths therefore must use the approved subprocess model interfaces, not direct OpenAI-style client calls.

### What must be persisted

- raw generation
- parse errors
- repair attempts applied
- rescue model used
- final validation result
- whether a placeholder was emitted

### Non-negotiable anti-cheat rules

- No hidden repair that leaves no audit trail.
- No swallowing parse failure and substituting optimistic markdown.
- No placeholder content that is presented as real authored material.
- No "best effort" success label when the stage actually degraded.

## Pattern E: Validation as a first-class module

BettaFish has both schema-level validation and artifact validators for tables and charts. Our equivalent should be even stricter because fiction continuity failure is harder to detect visually than broken analytics formatting.

### Required validator families for TinyAssets

1. schema validator
2. continuity validator
3. canon provenance validator
4. character state transition validator
5. timeline validator
6. renderer validator

### Minimum continuity checks

- chapter and scene ordering is consistent
- POV stays legal within scene rules
- character knowledge does not jump ahead of evidence
- unresolved plot states do not disappear without a transition
- location and timeline references remain coherent
- every scene purpose maps to the chapter purpose
- every fact-linked scene block references valid canon inputs

### Non-negotiable anti-cheat rules

- No continuity checking by "LLM vibes only."
- No validator that returns plain prose when defects need structured actionability.
- No merge of invalid scene IR into a chapter because only one field was wrong.
- No final manuscript publish when continuity defects remain above threshold.

## Pattern F: Replayable run state and event stream

BettaFish's SSE layer stores task history so clients can reconnect and catch up. That is the right standard for long-running generation.

### Required implementation in this project

Any long-running authoring or refactor pipeline should expose:

- stable run id
- stage transitions
- per-chapter or per-scene progress
- warnings
- defects
- cancellation state
- artifact paths

The event stream may be UI-facing, CLI-facing, or both, but the source of truth must be persistent run state, not ephemeral terminal logs.

### Non-negotiable anti-cheat rules

- No progress tracking that exists only in console output.
- No event feed without replay.
- No "done" state until validation and artifact persistence complete.

## Pattern G: Multi-model specialization by stage

BettaFish routes different engines to different model families. That idea is right even if the exact vendor mix is incidental.

For TinyAssets, specialization should be based on stage role, not provider fandom:

- planning model
- continuity or critical review model
- drafting model
- rescue model
- formatting or rendering helper where needed

This should be configured centrally and typed. The main mistake to avoid is hard-coding one provider assumption into every node.

### Non-negotiable anti-cheat rules

- No provider-specific logic spread across nodes.
- No stage that silently falls back to a weaker model without logging it.
- No single-model assumption for all authoring tasks.

## What We Should Not Copy

### 1. Log files as the collaboration substrate

This is inventive but brittle. We should preserve the idea and replace the transport.

### 2. Duplicated engine loops

Query, Media, and Insight are structurally too similar. The next-level version is a shared orchestration scaffold with pluggable tool adapters and stage policies.

### 3. Framework sprawl

Flask plus Streamlit plus SocketIO plus eventlet plus multiple service entry modes is too much surface area for the core value delivered.

### 4. Oversized dependency footprint

BettaFish pulls in a very broad stack. For this project, every dependency must justify itself against maintenance and reliability cost.

### 5. Direct SDK-centric writer path

This project explicitly forbids API SDKs for the primary writer. Any imported pattern must be adapted to subprocess-based provider execution.

### 6. Analytics-specific blocks without narrative translation

Widgets, SWOT tables, and KPI grids are not directly useful. The transferable principle is typed renderable blocks, not those particular block types.

## Concrete Refactor Program For TinyAssets

If we use this research seriously, the path should look like this.

### Phase 1: Land the narrative IR foundation

Deliverables:

- `Narrative IR` schema module
- validators for schema and provenance
- renderer interface for manuscript markdown and editorial HTML
- run manifest and per-chapter storage

Definition of done:

- a chapter can be generated, validated, persisted, and rendered without any markdown-first shortcut
- invalid scene or chapter payloads fail loudly
- every persisted chapter has raw output, validated JSON, and validation artifacts

### Phase 2: Replace loose chapter generation with staged drafting

Deliverables:

- chapter outline stage
- scene plan stage
- scene drafting stage
- chapter composition stage
- rescue pipeline for structured output failures

Definition of done:

- no chapter is produced by a single monolithic prose prompt
- scene plans exist as first-class artifacts
- chapter composition consumes validated scene IR only

### Phase 3: Add typed deliberation and moderator synthesis

Deliverables:

- persisted deliberation ledger
- host directive generator
- defect routing into scene or chapter regeneration

Definition of done:

- specialists can disagree in structured form
- host directives are targeted and persisted
- unresolved issues remain visible until cleared or explicitly accepted

### Phase 4: Add continuity-grade validation and replayable progress

Deliverables:

- continuity validators
- run status ledger
- event stream or equivalent replayable progress surface

Definition of done:

- long runs can be resumed and audited
- progress survives client disconnects
- final outputs cannot bypass continuity gates

## Red Flags Future Builders Must Treat As Failure

- "We can add the IR later, let us just generate markdown first."
- "Validation can be manual during early development."
- "We do not need raw artifacts once the chapter looks good."
- "The moderator can just read chat logs."
- "The renderer can fix structure problems downstream."
- "We can keep provenance in comments for now."
- "One big prompt is simpler and good enough."

Each of those is a downgrade back to lightweight AI project behavior.

## Suggested project-specific adaptations

### Adapt BettaFish's chapter JSON into scene-first narrative JSON

BettaFish generates chapters as the atomic structured unit. For fiction, scenes should be the tighter quality unit, with chapters composed from scenes. That gives us:

- better continuity checking
- smaller recovery scope on failure
- clearer provenance from fact packs to prose
- better support for iterative redrafting

### Adapt BettaFish's engine quotes into source-bound narrative evidence

BettaFish has explicit `engineQuote` handling. Our equivalent should be structured links from scene decisions back to world facts, plot notes, user uploads, and editorial constraints. Not visible in the final prose, but always traceable in the artifact ledger.

### Adapt BettaFish's template selection into narrative architecture selection

Instead of report templates, we need narrative architecture templates:

- braided viewpoint
- single-view arc
- nested frame
- alternating present and history
- dossier interleave

The system should choose or be assigned one, then the downstream stages must obey it as a contract, not as soft style guidance.

## Final take

BettaFish is worth studying because it demonstrates seriousness about output structure and artifact durability. Its strongest lesson is not "use more agents." Its strongest lesson is:

structured generation beats loose generation

For TinyAssets, the win is to build a narrative compiler, not a chatty demo.

If we import the right ideas and reject the weak ones, this project can move from "AI writes text" to "AI produces inspectable, continuity-safe, refactorable authored artifacts." That is the step that actually changes how credible the system looks.
