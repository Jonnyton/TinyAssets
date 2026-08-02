# Draft: V1 remix-to-running agent demo

**Status:** Awaiting host approval. This is not implementation authority and
does not change `PLAN.md` or OpenSpec.

## Problem statement

How might a browser-only user prove, in one coherent experience, that
TinyAssets lets them take an agent another person made, reshape every part of
it, privately bind their own services, talk to it through an everyday app, and
let it create and improve useful automations that keep running while their
computer is off?

## Recommended direction

Build the first V1 demonstration around a **remixed 24/7 Slack intelligence
agent**. The user begins with the TinyAssets connector, a Slack workspace, and
their own supported model/provider subscription; they do not install or host a
daemon.

The golden path is:

1. Discover a real public agent definition published by another user.
2. Remix it with selected components from at least one additional creator.
3. Replace, remove, add, and configure components conversationally, without an
   archetype enum or platform-owned starter template.
4. Create a private universe binding for goals, provider authority, Slack
   destination, runtime policy, and governed resources. No binding data or
   credential enters the public definition or lineage.
5. Talk to the new agent in Slack: “Every morning, research these companies,
   cite meaningful changes, test the workflow now, and improve it if the
   evidence is weak.”
6. Watch the agent draft the automation, run a bounded test, evaluate the
   result, revise it, show the before/after evidence, and request activation.
7. Approve activation, turn the user's computer off, and receive the next
   scheduled result in Slack from the user's cloud universe.
8. Export the agent losslessly. If the user publishes its definition, prove a
   second account can remix it while receiving none of the first user's goals,
   conversations, provider authority, Slack bindings, or secrets.

This demonstrates the product thesis in one sentence: **take any
community-built agent, make it entirely yours, and let it work continuously in
the apps you already use.**

## Directions considered

- **Recommended: intelligence agent.** Read-heavy, source-verifiable, safe
  enough that remix, evaluation, app conversation, and offline execution stay
  visible instead of being buried under dangerous-write controls.
- **Coding agent first.** More immediately impressive to developers and a
  stronger power-user signal, but repository credentials, sandboxing, patch
  review, CI, and write approval can consume the demo and obscure the common
  agent pipeline.
- **Bring-your-own foreign agent first.** Best direct proof of arbitrary
  import, but conversion failures and foreign-format explanation make a weaker
  first-run experience. Use it as the next acceptance story over the same
  substrate.

## Key assumptions to validate

- A user understands “remix” from visible component choices and lineage,
  rather than mistaking it for copying a prompt.
- Slack is a sufficiently universal first app surface; the substrate must not
  encode Slack-specific agent semantics.
- One supported provider-binding path can prove “use the subscription or
  authority you already have” without implying every provider is ready.
- A test/evaluate/revise transcript is legible enough that activation feels
  earned rather than magical.
- A genuine PC-off scheduled run can be demonstrated without maintainer
  credentials, quota, or compute.

Validate these with a rendered user session, private/public state inspection,
an exact export round trip, a second-account remix, execution traces, and a
scheduled PC-off Slack delivery.

## MVP scope

- Public discovery and N-parent component remix from user-published agents.
- Full component customization through the existing canonical handles.
- Private binding to one supported provider path and Slack.
- Slack conversation routed to the bound agent.
- Agent-authored workflow draft, bounded test, evaluation, one evidence-backed
  revision, explicit activation, and durable cloud schedule.
- Canonical export and a public-definition second-account remix proof.
- Failure paths that preserve the draft and explain missing provider, Slack,
  permission, evaluator, or cloud-execution authority without substituting
  maintainer resources.

## Not doing in the first demo

- No finite starter-agent catalog or privileged OpenClaw/Hermes/coding enums;
  those are community compositions over the same substrate.
- No drag-and-drop builder; chatbot composition is the first interface.
- No promise of every app, model provider, or foreign agent format.
- No unrestricted arbitrary-code execution or unreviewed external writes.
- No paid marketplace, bidding, settlement, or ranking optimization.
- No silent self-modification after activation; material workflow changes stay
  versioned, evaluated, and approval-governed.
- No private credential, goal, conversation, or universe binding in a public
  definition, export intended for the commons, or remix lineage.

## Acceptance boundary

The demo is not complete from unit tests, direct MCP calls, or a mocked Slack
adapter. Completion requires a real browser-rendered connector conversation,
a real Slack conversation, stored public/private boundary evidence, a real
scheduled run with the user's computer off, canonical export/re-import, a
second-account remix, and post-fix organic-use evidence or an explicit watch
item if no organic use has occurred yet.

## Open question

Approve the intelligence-agent domain for the first V1 golden path, or choose
the coding-agent direction while accepting its larger sandbox and write-safety
surface.
