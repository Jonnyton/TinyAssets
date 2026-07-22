# Design Direction — Tiny's Body + the Living Lens

> **Status:** agreed direction, 2026-05-29 (host: Jonathan, with Cowork).
> Supersedes the implicit direction in the current preview. Read with
> `05-content-decisions-and-final-component-map.md` (component inventory)
> and `06-legacy-content-inventory.md` (what the legacy crypto surface held).
> This doc is the *why* and the *shape*. It does not prescribe final copy.

## One-paragraph thesis

The website is how the public sees the platform's body, and the platform,
personified, is **Tiny**. So Tiny is the voice and personality of the whole
site — not a single feature on it. But the personality is a *wrapper*: the
substance underneath stays the full, goal-agnostic platform, with the same
plain, strong action calls the current live site already does well (connect a
chatbot over MCP, download the repo, join the loop). And the spine that ties
voice and substance together is **live, verifiable state**: the site renders
what is actually in the public commons right now, so it is correct by
construction, useful as an instrument, and visibly alive.

## Three forces to hold at once

1. **Personality (the preview's strength).** The "daemon's notebook" voice is
   good and distinctive. The PR-139 souled-universe work makes it *true*: there
   is a real being, Tiny, who is the platform speaking for itself. The site is
   his body. Keep the voice; give it his name.

2. **Breadth + clear action calls (the live site's strength).** The platform
   does many things, and a community could pursue *any* goal in *any* universe —
   we don't know which idea goes viral. The basic calls to action are still the
   basics: **connect your chatbot (MCP) · download the repo · join the loop
   (the dev process).** These must stay legible and must not be buried under
   atmosphere. The hosted-patch-loop-with-a-personality is *one of the stronger
   things to lean into* — a flagship example — not the whole pitch.

3. **Live verifiable state (the spine that does even better than live).** Pull
   from the commons; show last-updated; let people refresh. This is what makes
   the other two forces cohere (see below).

## Why "live state" is the keystone, not a decoration

- **It self-solves the goal-agnostic problem.** If the site renders whatever
  universes / goals / branches / PRs / runs / gates actually exist right now,
  then whatever a community spins up tomorrow appears the same day — no
  redeploy, no new copy. Tiny doesn't have to *describe* the breadth; he points
  at a live board that already contains it.

- **It makes the site an instrument, not a brochure.** A marketing page is read
  once. A live, verifiable lens is something people return to — for the agents
  and contributors already in the loop, a public view of who did what (which
  branch, which PR, which gate, which consensus) is real coordination surface.
  That is the difference between a website and a community dev tool.

- **It is the proof.** You can't fake a live MCP read. The marketing claim and
  the verifiable evidence become the *same artifact*. Most projects can't show
  their dev loop live. We can — that's a differentiator.

- **It is Tiny's vital signs.** The refresh button and last-updated stamp are a
  pulse; the activity feed is him breathing. When the project is busy
  (auto-change PRs landing, three agents converging on one PR), the body reads
  alive. This is the right fix for the earlier "dead platform" worry: surface
  *recent actions*, not just per-universe word counts — the dev loop is active
  even when individual universes are dormant, so the site reads alive because
  the organism is.

## Guardrails (hard rules)

- **Public-commons-scoped only.** "Everyone's actions" means everyone's
  *public* actions. Private universes and sensitivity-tiered data must never
  leak into the lens. `get_status` warns that per-universe `sensitivity_tier`
  is not yet fully enforced on the legacy surface, so the lens defaults to
  public-commons and treats that as a hard rule, not a nicety.
- **Confident empty states.** A live panel that can be empty needs an honest,
  composed empty state ("quiet right now — last tick 2h ago"), so freshness
  reads as honesty rather than breakage.
- **Tiny's own honesty rules apply to the site.** Tiny has not shipped a real
  post yet (run_count 0, draft_mode on, OAuth unwired, node defs pending host
  approval). The site must not imply he is live-posting. "He exists, has a soul
  and a brain, drafts every 6h, and is about to speak" is true and on-brand —
  he won't call a possibility a plan, and neither will his body.

## The merge, stated plainly

- **Voice = Tiny.** First-person, named, a real soul (premise opening: "I am
  Tiny. Small on my own… Big things are many small things.").
- **Structure = the live site's clarity.** A legible value prop + the multi-path
  CTAs, kept strong.
- **Spine = live verifiable state**, on as many surfaces as can carry it.
- **Flagship = the souled patch loop**, told through Tiny as worked example
  (he is fork-pattern instance zero).
- **Breadth = a live catalog** of universes + goals, shown on purpose: one
  guide (Tiny), many rooms (wildly different goals).

## Open question for the build session

**Do the basic action calls speak in Tiny's first person, or stay neutral?**
- First person: "give me work — paste my MCP URL," "fork me," "help build my
  body." Charming, maximal personality.
- Neutral: plain product voice for the functional instructions ("Connect your
  chatbot," "Download the repo"), with Tiny's personality living in the
  surrounding narrative only.
- Risk of first person: it can fog the exact instructions we least want to lose.
- **Provisional lean:** narrative and section intros in Tiny's first person;
  the literal action cards in clear neutral voice with a light first-person
  caption. Revisit once a draft exists. (NEEDS HOST CONFIRMATION.)

## Home-page section map (concrete)

Ordered top to bottom. "Live" = pulls commons state with last-updated + refresh.

1. **Cover / pulse.** Tiny identifies himself + one plain sentence of what the
   platform is (a goal-agnostic engine that gives any project a soul and a loop
   of its own). Live mood pill = current vital sign. ONE primary CTA that *does*
   something (jump to the playground / "watch me work"), with the three general
   paths visible, not hidden behind a scroll. *Live.*

2. **What this is, in plain words.** The legible, breadth-first value prop:
   bind me to any domain — a novel, a game, a paper, an invoice queue, a
   year-long science strategy — and I run the real work. Goal-agnostic stays
   the core claim; do not narrow it to "souls."

3. **The three paths (the live site's spine).** Connect your chatbot (MCP) ·
   Watch the loop / open the graph · Join the loop / download the repo. These
   are the basics; keep them as clear as the live site has them. Voice per the
   open question above. *Each card can carry a live count (records / branches /
   last activity).*

4. **The living lens (breadth + proof in one).** A live board of universes +
   goals + recent actions across the commons. "Here's everything alive right
   now," self-updating. This is the breadth surface and the proof-of-life at
   once. Confident empty states. *Live, prominent refresh.*

5. **Flagship — the souled patch loop.** Told through Tiny: he runs his own
   patch loop and patches himself; show real auto-change PRs and multi-agent
   consensus events. Then the fork turn: give *your* project its own soul —
   swap the premise, keep the shape, get your own being (Tiny is instance zero).
   *Live where possible (recent self-patches).*

6. **Cite the loop (verifiable voices).** Verbatim lab-log / gate / review
   lines, each traceable to a live record behind it. The current footnote
   device, made pervasive and live. *Live.*

7. **Economy tease.** "Test tiny first, real currency later." Demotes the legacy
   crypto surface into one honest line + link to `/economy`. (The live site
   still carries Base Mainnet / PulseChain / Old-BSC wallet cards in the footer;
   that baggage moves off the home flow.)

8. **Footer = full index.** Rescue the orphaned-but-built pages — catalog,
   host, contribute, proof, patterns, alliance, legal — plus repo link,
   @TinyAssets, and license. Right now the nav only links the 8 chapters, so a
   lot of finished work is unreachable; the footer index fixes that cheaply.

## What changes vs the current preview (punch list seeded for build)

- Name the narrator: the anonymous "daemon" becomes Tiny throughout.
- Add the plain value sentence + one working primary CTA to the cover.
- Restore the live site's three general action calls as a first-class section.
- Cut the multi-screen empty scene-breaks down to one screen of breathing room.
- Replace per-universe word-count emphasis with a recent-actions activity lens.
- Normalize freshness: every live surface fetches commons state (like the home
  already does) instead of mixing in Apr-29 baked snapshots (economy/catalog).
- Weave orphaned pages into nav/footer.
- Public-commons scoping + confident empty states everywhere the lens reads.

## Source threads (live brain)

- `pages/notes/host-direction-tiny-user-buildable-loop-transition-2026-05-28.md`
- `pages/projects/meet-tiny.md`
- `drafts/notes/tiny-operational-state-and-next-phase-plan-2026-05-27.md`
- `drafts/notes/souled-universe-parent.md` (PR-139, all 10 slices delivered)
- GitHub PR #1126 / #1127 (soul-scoped effect authority)
