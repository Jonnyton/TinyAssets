# Node-Type Taxonomy — Catalog v1

**Status:** v1 catalog. Complements `docs/catalogs/privacy-principles-and-data-leak-taxonomy.md`. Loaded by the chatbot when designing or categorizing nodes.
**Purpose:** give the chatbot + the catalog's browse UX a stable vocabulary for **what kind of thing a node is**, independent of domain.
**Audience:** chatbot (primary consumer for design reasoning); catalog browser (secondary, for filter UX).
**Licensing:** CC0-1.0.

---

## 1. Why taxonomy

At Wikipedia-scale workflow design (per `project_convergent_design_commons.md`), nodes span thousands of domains. A user-facing "domain" field (`research-paper`, `fantasy-authoring`, `recipes`) doesn't tell the chatbot the *shape* of a node — what it takes in, what it produces, how reliable it is.

Taxonomy gives the chatbot a parallel axis: **what role does this node play in a workflow**, beyond its subject matter.

When a user says "I need a node that validates research-paper citations": domain = research-paper, **type = validator**. The chatbot searches the catalog by **type** alongside domain + semantic match. Cross-domain structural matches emerge naturally — a validator node built for invoices ("check this number matches the total") has a similar shape to a citations-validator.

---

## 2. Top-level node types

Every node belongs to exactly one top-level type. Ordered roughly by frequency (rough-estimated from prior workflow corpora):

### 2.1 Generators

Produce substantive new content from context. High LLM use, high variability.

**Examples:** scene drafter, research-hypothesis generator, code function writer, recipe suggestion, email draft, news summary.

**Input pattern:** context + constraints (tone, length, style).
**Output pattern:** new text / artifact.
**Reliability:** variable (0.6-0.9 typical accept rate depending on domain + model).

### 2.2 Extractors

Pull structured data out of unstructured input. Regex / NER / LLM parse.

**Examples:** invoice-number extractor, entity-from-text, date-normalizer, PII-redactor, key-phrase extractor.

**Input pattern:** unstructured text / image / document.
**Output pattern:** typed JSON.
**Reliability:** high on clean input (0.85-0.98); drops on noisy / OCR'd input.

### 2.3 Validators

Check whether input meets some criterion; return boolean + rationale.

**Examples:** citation-validity checker, code-lints, schema-conformance checker, factuality scorer, tone-match validator.

**Input pattern:** content + rule / reference.
**Output pattern:** `{passed: bool, score: float, rationale: string, failures: [...]}`.
**Reliability:** rule-based = high; LLM-judged = variable.

### 2.4 Transformers

Rewrite input into a different form without adding new substance. Format conversion, style changes, translations.

**Examples:** markdown-to-HTML, tone-rewriter (formal ↔ casual), language-translator, recipe-scaler, prose-polish.

**Input pattern:** content + target format / style.
**Output pattern:** same-substance content, different form.
**Reliability:** deterministic transforms = 1.0; LLM-transforms = ~0.9.

### 2.5 Routers

Decide which next node or branch executes based on input. Typically the output is a next-step identifier, not content.

**Examples:** quality-gated router (if score > 0.7 → commit; else → revise), domain-classifier (research vs fiction), intent-classifier.

**Input pattern:** current state + routing rule.
**Output pattern:** `{next_node: "...", confidence: float}` OR a state mutation.
**Reliability:** high when rules are explicit; variable when LLM-judged.

### 2.6 Retrievers

Fetch relevant content from a store (vector DB, file system, web, catalog).

**Examples:** semantic search of prior notes, citation-lookup by DOI, recipe-search, web-fetch of a URL.

**Input pattern:** query + filters.
**Output pattern:** ranked list of candidates.
**Reliability:** embedding-retrieval = 0.8-0.95 precision@10; keyword = lower.

### 2.7 Aggregators

Combine N inputs into a single output. Summarize, synthesize, merge.

**Examples:** multi-source literature synthesis, meeting-notes-summary, ensemble-of-drafts, vote-resolver.

**Input pattern:** list of items.
**Output pattern:** single synthesized artifact.
**Reliability:** variable; hardest category because it combines generator + reasoning + coverage.

### 2.8 Side-effecters

Produce effects beyond just-returned data: write to DB, call external API, send email, run subprocess.

**Examples:** file-writer, notification-sender, git-commit, API-call (Stripe, GitHub), executable-runner.

**Input pattern:** request specification.
**Output pattern:** effect receipt (status + IDs).
**Reliability:** depends on the external system; needs retry + idempotency discipline.

### 2.9 Evaluators

A specialized validator class: judge a past run's output, produce a score + critique for iteration.

**Examples:** scene-evaluator (score + rationale), code-review-judge, research-rigor-checker, recipe-taste-predictor.

**Input pattern:** prior-node-output + rubric.
**Output pattern:** `{score: float, critique: string, revise_suggestions: [...]}`.
**Reliability:** LLM-judged; typically used with a self-consistency pass.

### 2.10 Orchestrators

Compose other nodes into a higher-order flow. Rare at the leaf level; more common as a BranchDefinition top-level.

**Examples:** multi-turn conversation manager, hierarchical-task runner (chapter → scene → beat).

**Input pattern:** high-level goal.
**Output pattern:** delegated state updates.
**Reliability:** depends on component reliability (product of compositions).

---

## 3. Cross-taxonomy dimensions

### 3.1 Effect class

Orthogonal to the type. Every node is ONE of:

- **Pure** — same input → same output. No side effects. Fully replay-safe.
- **Deterministic-with-IO** — reads / writes to a known store, but replay produces same state. Side-effecter subset.
- **LLM-stochastic** — same input → variable output. Any generator / LLM-validator / LLM-aggregator falls here.
- **External-effect** — performs action with real-world consequences (email sent, payment processed). Non-reversible.

**Why it matters:** the chatbot + daemon treat these differently for retry + caching. Pure nodes cache forever; LLM-stochastic cache with temperature=0 only; external-effect never cache + need explicit consent each invocation.

### 3.2 Resource profile

- **Light** — LLM call under 500 tokens. Cheap. Sub-second.
- **Medium** — LLM call 500-5000 tokens. Multi-second.
- **Heavy** — LLM call >5000 tokens OR multi-model ensemble OR substantial tool calls.
- **Compute-bound** — non-LLM, e.g. local Python analysis, image processing.
- **External-bound** — blocked on network / third-party latency.

**Why it matters:** daemon cost estimation in paid-market bids (#29 §2) + capability matching.

### 3.3 Reliability tier

- **Rule-based** — deterministic logic (regex, lookup, schema-check). High reliability.
- **Hybrid** — rule-based core + LLM fallback for edge cases.
- **LLM-driven** — primary logic is LLM prompt. Reliability varies with model + prompt quality.
- **Exploratory** — nodes explicitly marked "experimental, don't rely on output"; useful for brainstorm / divergence.

**Why it matters:** the `quality` signals in `discover_nodes` (per #25 §3.1) are more meaningful when compared within a reliability tier. A 0.7 success rate is good for LLM-driven, concerning for rule-based.

---

## 4. Decision matrix for type classification

When the chatbot (or a contributor) is categorizing a new node, apply this decision tree:

```
Does the node produce new substantive content?
 ├─ Yes → Generators (§2.1)
 └─ No → continue
Does the node pull structured data from unstructured input?
 ├─ Yes → Extractors (§2.2)
 └─ No → continue
Does the node judge / check something + return pass/fail?
 ├─ Yes, on past-run output → Evaluators (§2.9)
 ├─ Yes, on incoming content → Validators (§2.3)
 └─ No → continue
Does the node rewrite content into a different form?
 ├─ Yes → Transformers (§2.4)
 └─ No → continue
Does the node produce a routing decision (next-step)?
 ├─ Yes → Routers (§2.5)
 └─ No → continue
Does the node fetch content from a store?
 ├─ Yes → Retrievers (§2.6)
 └─ No → continue
Does the node combine N inputs into 1 output?
 ├─ Yes → Aggregators (§2.7)
 └─ No → continue
Does the node perform an external side effect?
 ├─ Yes → Side-effecters (§2.8)
 └─ No → continue
Does the node compose multiple other nodes?
 ├─ Yes → Orchestrators (§2.10)
 └─ No → doesn't fit v1 taxonomy; propose a new category in v2.
```

---

## 5. Example classifications (v0 sample nodes applied)

Cross-ref to `prototype/tinyassets-catalog-v0/catalog/nodes/`:

| Sample node | Type | Effect class | Resource profile | Reliability tier |
|---|---|---|---|---|
| invoice-ocr (invoice-number extractor) | **Extractor** (§2.2) | Pure | Light | Hybrid |
| research-hypothesis-generator | **Generator** (§2.1) | LLM-stochastic | Medium | LLM-driven |
| fantasy-scene-drafter | **Generator** (§2.1) | LLM-stochastic | Heavy | LLM-driven |
| recipe-scaler | **Transformer** (§2.4) | Pure | Light | Rule-based |

---

## 6. Integration with `discover_nodes`

Augment the ranked candidate signal block per #25 §3.1:

```json
{
  "type": "generator",
  "effect_class": "llm-stochastic",
  "resource_profile": "heavy",
  "reliability_tier": "llm-driven",
  ...
}
```

These four enums attach to every node row. They inform the chatbot's `is-this-the-right-shape` reasoning without the chatbot having to read + classify the node's entire concept blob.

Storage: add to `nodes` table as 4 new columns (see schema extension below). Indexed composite on `(domain, type)` for fast type-filtered discovery. Backward-compatible default: existing rows get `type='generator'` + `effect_class='llm-stochastic'` (safe-assumption defaults) + `resource_profile='medium'` + `reliability_tier='llm-driven'`. Owner can refine per row.

### 6.1 Schema extension to #25 §1.2

```sql
ALTER TABLE public.nodes
  ADD COLUMN node_type text NOT NULL DEFAULT 'generator'
    CHECK (node_type IN (
      'generator', 'extractor', 'validator', 'transformer',
      'router', 'retriever', 'aggregator', 'side_effecter',
      'evaluator', 'orchestrator'
    )),
  ADD COLUMN effect_class text NOT NULL DEFAULT 'llm-stochastic'
    CHECK (effect_class IN (
      'pure', 'deterministic-with-io', 'llm-stochastic', 'external-effect'
    )),
  ADD COLUMN resource_profile text NOT NULL DEFAULT 'medium'
    CHECK (resource_profile IN (
      'light', 'medium', 'heavy', 'compute-bound', 'external-bound'
    )),
  ADD COLUMN reliability_tier text NOT NULL DEFAULT 'llm-driven'
    CHECK (reliability_tier IN (
      'rule-based', 'hybrid', 'llm-driven', 'exploratory'
    ));

CREATE INDEX nodes_type_domain ON public.nodes (node_type, domain);
```

---

## 7. OPEN flags

| # | Question |
|---|---|
| Q1 | **Multi-type nodes.** Some nodes legitimately span types (e.g., a validator that also produces a rewrite suggestion = validator + transformer). v1: force single primary type; allow a secondary via optional column? Flagged for v2. |
| Q2 | **User-extensible taxonomy.** Should contributors be able to add new top-level types via PR, or is the list fixed in v1? Recommend: fixed in v1 (10 categories cover 99%+ of corpora); extensible in v2 if community demand proves gaps. |
| Q3 | **Auto-classification.** Can the chatbot auto-assign `node_type` + `effect_class` etc. based on the concept blob? Recommend yes; UX prompt asks user "does this look right?" as confirmation. |
| Q4 | **Historical node classification.** Pre-launch seed nodes don't have these columns filled. Run a one-time bulk-classification pass against §5-style rules + manual review by admin-pool? |
| Q5 | **Cross-taxonomy search.** `discover_nodes` takes a `type` filter or not at launch? If yes, expose as param; if no, chatbot filters client-side. Recommend expose as param. |

---

## 8. Cross-reference

- Schema spec #25 §1.2 — `nodes` table this extends.
- Privacy catalog — `docs/catalogs/privacy-principles-and-data-leak-taxonomy.md` complementary catalog.
- Sample nodes — `prototype/tinyassets-catalog-v0/catalog/nodes/` for worked examples.
- Memory — `project_convergent_design_commons.md` for Wikipedia-scale framing.
