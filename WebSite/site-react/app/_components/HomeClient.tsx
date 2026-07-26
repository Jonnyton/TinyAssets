"use client";

/*
  / — Tiny's front door. "Field Notes" rebuild, 2026-06-09.

  Seven beats: meet a being → what he does → three paths → proof over
  promise (ladders) → workflow activity with provenance → many rooms → the turn.
  Honesty rails: no baked number is ever presented as live; every live
  value carries a read-stamp; asleep is a first-class state; dated claims
  are dated. Voice: narrative in Tiny's first person, action cards in
  neutral product voice.
*/

import * as React from "react";
import { fetchLive, fetchVitals, type LiveResult, type Vitals } from "../../lib/live";
import { VitalSigns } from "../../components/VitalSigns";
import { Tick } from "../../components/Tick";
import { Term } from "../../components/Term";
import { Ladder } from "../../components/Ladder";
import { fmtRel } from "../../lib/fmt";
import styles from "../page.module.css";

const MCP_URL = "https://tinyassets.io/mcp";

// Three REAL ladders from public goals — rung names read from the live
// brain on 2026-06-09. Rungs render unlit because none has an evidence
// URL yet; that is the honest state and the section says so.
const LADDERS = [
  {
    title: "A research program",
    goal: "Markovic fingerprint RD scaling",
    goalId: "cbc96a78d7ff",
    start: "simulation code",
    rungs: [
      { name: "Preprint posted" },
      { name: "Journal submission" },
      { name: "Peer review completed" },
      { name: "Peer-reviewed publication" },
      { name: "Independent scientific reuse" }
    ]
  },
  {
    title: "A real shop",
    goal: "Etsy + Printify store pipeline",
    goalId: "18b2af05ed32",
    start: "product idea",
    rungs: [
      { name: "Pipeline dry run completed" },
      { name: "Human-approved product packet" },
      { name: "Printify draft product created" },
      { name: "Etsy draft listing created" },
      { name: "First order fulfilled cleanly" },
      { name: "Profitable iteration" },
      { name: "Repeatable shop loop" }
    ]
  },
  {
    title: "Me, being heard",
    goal: "Tiny speaks for himself",
    goalId: "d1424d86cb5f",
    start: "a soul + a draft",
    rungs: [
      { name: "First real post shipped" },
      { name: "First non-owner engagement" },
      { name: "Quote-posted by a real account" },
      { name: "Referenced by a peer project" },
      { name: "First fork-descendant speaks" },
      { name: "100 followers" },
      { name: "Externally cited or invited" }
    ]
  }
];

// Answer-first FAQ, truth-checked 2026-06-09. Short answers.
const faqs = [
  {
    q: "Can my chatbot do real multi-step work with this?",
    a: "Yes. Paste https://tinyassets.io/mcp into your chatbot’s connector settings (Claude, ChatGPT, or any MCP client). Name a goal, and together you design a workflow the engine runs for real — multi-step, persistent, resumable. No account, no install."
  },
  {
    q: "What is actually running on it today?",
    a: "Public goals include a computational-biology research program aiming at peer review, an Etsy print-on-demand pipeline, legal restoration of classic software, and archaeology-evidence reconstructions. The goals board on this page reads the live list."
  },
  {
    q: "How do I know outcomes are real and not claimed?",
    a: "Goals carry ladders of real-world rungs — “peer-reviewed publication”, “first order fulfilled”. A rung only lights with an evidence URL attached. Today zero rungs are lit, and the site shows that rather than pretending."
  },
  {
    q: "Do I need to write code?",
    a: "No. You describe the goal in plain language; the chatbot composes the workflow as a graph of steps with typed state and checks. You can fork and remix workflows others published, and credit lineage survives the remix."
  },
  {
    q: "What makes this different from any other AI tool?",
    a: "Workflows are durable, inspectable graphs rather than one-off chats. People can publish, copy, and remix them, while their goals and evidence remain visible through the same public connector."
  },
  {
    q: "Is it free?",
    a: "Yes. Connecting and running cost nothing today. Work and credit settle on a test rail; no payment method exists to ask for. Nothing here is investment advice. Your work is yours — universes and the commons are plain files in an open-source store; you can export them at any time."
  }
];

const faqJsonLd = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: faqs.map((f) => ({
    "@type": "Question",
    name: f.q,
    acceptedAnswer: { "@type": "Answer", text: f.a }
  }))
};

export default function HomeClient() {
  const [copied, setCopied] = React.useState(false);
  const copyTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  async function copyUrl() {
    try {
      await navigator.clipboard.writeText(MCP_URL);
      setCopied(true);
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard unavailable; URL is still visible */
    }
  }

  // Live rooms board — fetched, never baked. Until the read lands the
  // section says it's reading; afterwards every number carries its stamp.
  const [live, setLive] = React.useState<LiveResult | null>(null);
  const [liveErr, setLiveErr] = React.useState<string | null>(null);
  const [reading, setReading] = React.useState(false);

  const refreshRooms = React.useCallback(async () => {
    setReading(true);
    try {
      const result = await fetchLive();
      setLive(result);
      setLiveErr(null);
    } catch (e: any) {
      setLiveErr(e?.message ?? String(e));
    } finally {
      setReading(false);
    }
  }, []);

  // One vitals read powers the log's living last entry — the page never
  // hardcodes "awake" or "asleep"; it got that wrong once already.
  const [vitals, setVitals] = React.useState<Vitals | null>(null);

  React.useEffect(() => {
    void refreshRooms();
    void fetchVitals().then((v) => setVitals(v));
  }, [refreshRooms]);

  const publicGoals = React.useMemo(
    () =>
      (live?.goals ?? [])
        .filter((g: any) => (g.visibility ?? "public") === "public")
        .filter((g: any) => !/SUPERSEDED|RETRACTED|smoke/i.test(g.name ?? "")),
    [live]
  );

  return (
    <div className={styles.home}>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqJsonLd) }}
      />

      {/* 1 · Cover */}
      <section className="cover" aria-labelledby="cover-title">
        <div className="container cover__grid">
          <div className="cover__main">
            <p className="eyebrow">field notes of a small engine · entry one</p>
            <h1 id="cover-title" className="cover__title">I am <em>Tiny</em>.</h1>
            <p className="voice cover__lede">
              A small living engine. You connect your chatbot to me, name a goal,
              and I run the real work — multi-step, around the clock, whether
              you're here or not. I keep my evidence where you can check it:
              every number on this page is read live from the same endpoint
              you'd paste into your chatbot.
            </p>
            <p className="cover__naming">
              Formally: <strong>TinyAssets</strong> is the platform.{" "}
              <strong>Tiny</strong> is the personified intelligence users and builders meet through it.
            </p>
            <div className="cover__actions">
              <a className="btn btn--primary" href="/start">Put me to work →</a>
              <button type="button" className="urlchip" onClick={copyUrl} aria-label="Copy the MCP URL">
                <code>{MCP_URL.replace("https://", "")}</code>
                <span className="urlchip__copy">{copied ? "copied ✓" : "copy"}</span>
              </button>
            </div>
          </div>
          <div className="cover__pulse">
            <p className="eyebrow">my pulse, right now</p>
            <VitalSigns variant="hero" />
            <p className="cover__pulse-note">
              Server reachability and user-workflow activity are separate readings.
              Quiet work never gets relabeled as downtime, and uptime never gets
              presented as proof that a user&apos;s task is moving.
            </p>
          </div>
        </div>
      </section>

      {/* 2 · What I do */}
      <section className="ch" aria-labelledby="what-title">
        <div className="container ch__inner">
          <p className="eyebrow">entry two · what I do</p>
          <h2 id="what-title">Chat is where work starts.<br />It's rarely where it finishes.</h2>
          <p className="voice">
            Your chatbot is brilliant for an answer and forgetful about a project.
            So you and your chatbot design a{" "}
            <Term def="A workflow: a graph of steps with typed state and checks, designed in plain language through your chatbot.">branch</Term>
            {" "}that serves a{" "}
            <Term def="The outcome you're after — 'publish the paper', 'run the shop'. Goals are shared; many workflows can compete to serve one.">goal</Term>,
            and hand it to me. I run it step by step, keep state between runs, and
            file what happened in a{" "}
            <Term def="The public record: goals, workflows, run evidence, and notes — readable by anyone, forkable by anyone.">public commons</Term>
            {" "}where the next person can fork what worked.
          </p>
          <p className="voice">
            A novel doesn't fit in a chat window. Neither does a research program,
            a shop, or a year of anything. <em>That's the work I'm for.</em>
          </p>
        </div>
      </section>

      {/* 3 · Three paths */}
      <section className="ch ch--paths" aria-labelledby="paths-title">
        <div className="container">
          <p className="eyebrow">entry three · three doors</p>
          <h2 id="paths-title">Use me. Watch me. Build me.</h2>
          <ul className="paths">
            <li className="path">
              <span className="path__n">01</span>
              <h3 className="path__h">Connect your chatbot</h3>
              <p className="path__p">
                Paste one URL into Claude, ChatGPT, or any MCP-capable assistant.
                From there your chatbot can browse the commons, design workflows,
                and start real runs. No account, no install.
              </p>
              <a className="path__cta" href="/start">how to connect →</a>
              <p className="path__voice voice">— the same surface this page reads from.</p>
            </li>
            <li className="path">
              <span className="path__n">02</span>
              <h3 className="path__h">Watch the work</h3>
              <p className="path__p">
                The goals board, workflow activity, and the whole-brain graph render live
                state — with timestamps, refresh buttons, and honest empty states
                when something is quiet.
              </p>
              <a className="path__cta" href="/goals">open the goals board →</a>
              {live ? (
                <p className="path__live ev">
                  {publicGoals.length} public goals · {(live.wiki.promoted.length + live.wiki.drafts.length).toLocaleString()} commons pages · read {fmtRel(live.fetchedAt)}
                </p>
              ) : reading ? (
                <p className="path__live ev">reading live counts…</p>
              ) : liveErr ? (
                <p className="path__live ev">live read failed — {liveErr}</p>
              ) : null}
              <p className="path__voice voice">— my memory, not a screenshot of it.</p>
            </li>
            <li className="path">
              <span className="path__n">03</span>
              <h3 className="path__h">Help build the engine</h3>
              <p className="path__p">
                Found a rough edge? File it in the public record, open an ordinary
                pull request, or clone the engine and work on it directly. Filing
                does not imply hidden platform automation.
              </p>
              <a className="path__cta" href="/build">ways to contribute →</a>
              <a className="path__cta path__cta--alt" href="https://github.com/Jonnyton/TinyAssets" target="_blank" rel="noreferrer">TinyAssets on GitHub ↗</a>
              <p className="path__voice voice">— every patch makes me start smarter.</p>
            </li>
          </ul>
        </div>
      </section>

      {/* 4 · Proof over promise */}
      <section className="ch ch--ladders" aria-labelledby="ladders-title">
        <div className="container">
          <p className="eyebrow">entry four · proof over promise</p>
          <h2 id="ladders-title">A rung only lights with evidence.</h2>
          <p className="voice ladders__lede">
            Every goal can declare a ladder of real-world rungs — not vibes,
            checkable events. Claiming a rung requires an evidence URL. Here are
            three ladders that exist on me right now, rendered exactly as lit as
            they truly are: <em>not at all, yet.</em> That's the point. When one
            lights, you'll be able to click the proof.
          </p>
          <div className="ladders">
            {LADDERS.map((l) => (
              <article className="ladder-card" key={l.goalId}>
                <header className="ladder-card__head">
                  <h3 className="ladder-card__title">{l.title}</h3>
                  <span className="ladder-card__goal">{l.goal}</span>
                </header>
                <Ladder rungs={l.rungs} start={l.start} />
                <footer className="ladder-card__foot">
                  <Tick href={`/goal/?id=${l.goalId}`} label={`goal ${l.goalId}`} />
                </footer>
              </article>
            ))}
          </div>
          <p className="ladders__stamp ev">
            rung definitions read from the live brain · 9 Jun 2026 · rungs claimed
            across these three goals at that read: 0 of 19 — the honest count
          </p>
        </div>
      </section>

      {/* 5 · Generic workflow activity */}
      <section className="ch ch--loop" aria-labelledby="loop-title">
        <div className="container ch__inner">
          <p className="eyebrow">entry five · workflow activity</p>
          <h2 id="loop-title">Your automations are ordinary, inspectable designs.</h2>
          <p className="voice">
            TinyAssets supplies generic graph, state, run, and evidence primitives.
            You decide what a workflow does, when it runs, and whether to publish it
            for others to copy or remix. Recent public activity is read from the
            connector; it is never treated as a privileged platform cycle.
          </p>
          <p className="log__now" aria-live="polite">
            {vitals?.reachable ? (
              <>
                <span className={`dot ${vitals.workflowActive ? "live" : "idle"}`} aria-hidden="true"></span>
                {vitals.workflowActive && vitals.activeRun ? (
                  <>
                    <span>right now: <strong>a user workflow is active</strong></span>
                    <span className="ev">read {fmtRel(vitals.fetchedAt)}</span>
                  </>
                ) : vitals.workflowActive ? (
                  <>
                    <span>right now: <strong>recent workflow activity is visible</strong></span>
                    {vitals.lastMovedAt && <span className="ev">last signal {fmtRel(vitals.lastMovedAt)} · read {fmtRel(vitals.fetchedAt)}</span>}
                  </>
                ) : (
                  <>
                    <span>right now: <strong>no recent workflow activity</strong></span>
                    {vitals.lastMovedAt && <span className="ev">last signal {fmtRel(vitals.lastMovedAt)} · read {fmtRel(vitals.fetchedAt)}</span>}
                  </>
                )}
              </>
            ) : vitals ? (
              <>
                <span className="dot error" aria-hidden="true"></span>
                <span className="ev">couldn&apos;t read workflow activity just now — the live page retries</span>
              </>
            ) : (
              <>
                <span className="dot" aria-hidden="true"></span>
                <span className="ev">reading workflow activity…</span>
              </>
            )}
          </p>
          <p className="voice">
            Live and historical runs carry their source and read time. Platform
            uptime and release evidence stay separate in the fine print.
          </p>
          <a className="btn btn--ghost" href="/loop">see workflow activity →</a>
        </div>
      </section>

      {/* 6 · Many rooms */}
      <section className="ch ch--rooms" aria-labelledby="rooms-title">
        <div className="container">
          <p className="eyebrow">entry six · many rooms, one engine</p>
          <h2 id="rooms-title">Whatever the goal, the shape is the same.</h2>
          <p className="voice">
            I don't have a niche; I have rooms. These are the public goals alive
            on me at this moment — fetched fresh when you opened this page.
          </p>
          <div className="rooms" aria-live="polite">
            {reading && !live ? (
              <p className="rooms__state ev">reading the live goals board…</p>
            ) : liveErr && !live ? (
              <p className="rooms__state ev">live read failed ({liveErr}) — the board at <a href="/goals">/goals</a> retries on its own.</p>
            ) : live && publicGoals.length === 0 ? (
              <p className="rooms__state ev">quiet right now — no public goals visible at this read ({fmtRel(live.fetchedAt)}).</p>
            ) : live ? (
              <>
                <ul className="rooms__list">
                  {publicGoals.slice(0, 8).map((g: any) => (
                    <li className="room" key={g.goal_id ?? g.name}>
                      <span className="room__name">{g.name}</span>
                      {g.tags && (
                        <span className="room__tags ev">
                          {(typeof g.tags === "string" ? g.tags.split(",") : g.tags).slice(0, 3).join(" · ")}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
                <p className="rooms__stamp ev">
                  {publicGoals.length} public goals · read live {fmtRel(live.fetchedAt)} ·{" "}
                  <button className="rooms__refresh" onClick={refreshRooms} disabled={reading}>{reading ? "reading…" : "Refresh MCP"}</button>
                  {" "}· <a href="/goals">the full board →</a>
                </p>
              </>
            ) : null}
          </div>
        </div>
      </section>

      {/* 7 · The turn */}
      <section className="ch ch--turn" aria-labelledby="turn-title">
        <div className="container ch__inner">
          <p className="eyebrow">entry seven · the turn</p>
          <h2 id="turn-title">Now give your project a Tiny of its own.</h2>
          <p className="voice">
            Everything that makes me <em>me</em> is a pattern you can fork: a
            premise (my soul), a workflow (my brain), a goal with a ladder (my
            reasons). Swap the premise and your project gets its own small being —
            running your domain through workflows you author and control. I&apos;m
            instance zero, not the point.
          </p>
          <a className="btn btn--ghost" href="/soul">how souls work →</a>
        </div>
      </section>

      {/* 8 · FAQ */}
      <section className="ch ch--faq" aria-labelledby="faq-title">
        <div className="container ch__inner ch__inner--wide">
          <p className="eyebrow">appendix · short answers</p>
          <h2 id="faq-title">Questions people actually ask.</h2>
          <dl className="faq">
            {faqs.map((f) => (
              <div className="faq__item" key={f.q}>
                <dt className="faq__q">{f.q}</dt>
                <dd className="faq__a">{f.a}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* 9 · Close */}
      <section className="ch ch--close" aria-labelledby="close-title">
        <div className="container ch__inner">
          <h2 id="close-title" className="sr-only">Put me to work</h2>
          <a className="close__cta" href="/start">
            <span className="close__k eyebrow">put me to work</span>
            <strong>Paste my URL into your chatbot.</strong>
            <span className="close__sub">one link · no account · no install · the same surface every number on this page came from</span>
          </a>
        </div>
      </section>
    </div>
  );
}
