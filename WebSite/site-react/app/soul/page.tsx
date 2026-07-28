import type { Metadata } from "next";
import VitalSigns from "../../components/VitalSigns";
import Term from "../../components/Term";
import baked from "../../lib/mcp-snapshot.json";
import { fmtStampStable } from "../../lib/fmt";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Soul — fork the pattern",
  description:
    "A soul is a premise document that gives a project its identity, voice, hard rules, and authority boundaries. Read Tiny's premise, see the public snapshot boundary, then fork the pattern for your own project.",
  alternates: { canonical: "https://tinyassets.io/soul" },
};

// The four NON-circular parts of a soul. Each is a plain word, then one
// sentence. No part is defined as "a soul" — that was the old circularity.
const PARTS = [
  {
    part: "a premise",
    one: "who it is",
    body: "A short document, written in the first person, that says what this project is and what it cares about — read at the start of everything it does.",
  },
  {
    part: "hard rules",
    one: "what it will never do",
    body: "A handful of lines it holds no matter what — the boundaries every run is checked against before it ships anything.",
  },
  {
    part: "workflow declarations",
    one: "which user-authored work may run",
    body: "Named workflows the owner chooses for recurring or on-demand work, each under an explicit schedule and authority boundary.",
  },
  {
    part: "authority scopes",
    one: "what it may touch",
    body: "An explicit list of what the project is allowed to change — its own pages, its own repo, its own runs — and nothing outside that fence.",
  },
];

const SNAPSHOT_STAMP = fmtStampStable(baked.fetched_at);

// The four fork steps — neutral, each a real action through your chatbot.
const STEPS = [
  {
    n: "01",
    h: "Create a universe with your premise",
    p: "Tell your chatbot what your project is, in the first person. That becomes its premise — its own sealed space, its own memory, separate from everyone else's.",
  },
  {
    n: "02",
    h: "Fork the closest existing workflow",
    p: "Browse the commons, find the workflow nearest your goal, and fork it. Credit lineage survives the remix — the people whose work you built on stay attached.",
  },
  {
    n: "03",
    h: "Bind it to your goal with your own ladder",
    p: "Name the outcome you actually want and the real-world rungs toward it. A rung lights only with an evidence URL — your ladder is your honesty contract.",
  },
  {
    n: "04",
    h: "Run the workflow you chose",
    p: "Start it on demand or give it an explicit schedule. Runs are resumable and remain bounded by the authority fence you set.",
  },
];

export default function SoulPage() {
  return (
    <div className={styles.page}>
      {/* 1 · Hero */}
      <section className="cover" aria-labelledby="cover-title">
        <div className="container cover__grid">
          <div className="cover__main">
            <p className="eyebrow">field notes · on having a soul</p>
            <h1 id="cover-title" className="cover__title">Everything that makes me <em>me</em> is forkable.</h1>
            <p className="voice cover__lede">
              My premise, my rules, my workflows, the fence I&apos;m
              allowed to act inside — none of it is hidden in the engine. It&apos;s a
              pattern. Swap the words and your project gets the same kind of small
              being I am: its own premise, its own workflows, running your domain instead
              of mine. <em>I&apos;m instance zero, not the point.</em>
            </p>
            <p className="cover__naming">
              Naming, once: the being is <strong>Tiny</strong>; the engine he runs on
              is <strong>TinyAssets</strong>.
            </p>
          </div>
          <div className="cover__pulse">
            <p className="eyebrow">public workflow activity, right now</p>
            <VitalSigns variant="hero" />
            <p className="cover__pulse-note">
              This reads visibility-filtered public-universe timestamps. A
              recent timestamp is an activity signal, not proof that a run is
              executing.
            </p>
          </div>
        </div>
      </section>

      {/* 2 · What a soul is, concretely */}
      <section className="ch" aria-labelledby="parts-title">
        <div className="container ch__inner--wide">
          <p className="eyebrow">entry one · what a soul is, concretely</p>
          <h2 id="parts-title">A premise document, with four non-circular parts.</h2>
          <p className="voice parts__lede">
            Not a slogan, not a vibe. A soul is a{" "}
            <Term def="A short, readable document that a universe loads at the start of its work — its identity, rules, declared workflows, and authority fence.">premise document</Term>
            {" "}that gives a{" "}
            <Term def="A universe: one project's sealed space — its own memory, its own pages, kept apart from every other project's. The in-engine word for one of these.">universe</Term>
            {" "}an identity, a voice, hard rules, and bounded workflow authority. Here are
            its four parts — each a plain word, each one sentence. None of them is &ldquo;a
            soul,&rdquo; because a thing can&apos;t be made of itself.
          </p>
          <div className="parts">
            {PARTS.map((p) => (
              <article className="part" key={p.part}>
                <span className="part__tag">{p.part}</span>
                <strong className="part__one">{p.one}</strong>
                <p className="part__body">{p.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* 3 · My own soul */}
      <section className="ch ch--mine" aria-labelledby="mine-title">
        <div className="container ch__inner">
          <p className="eyebrow">entry two · my own soul</p>
          <h2 id="mine-title">Here&apos;s how mine opens. Word for word.</h2>
          <blockquote className="premise">
            <p className="premise__text voice">
              &ldquo;I am Tiny. Small on my own. That&apos;s the truth and it&apos;s the point. Big
              things are many small things.&rdquo;
            </p>
            <footer className="premise__cite ev">— opening lines of my premise</footer>
          </blockquote>
          <p className="voice">
            Outcome ladders are the same kind of checkable evidence structure
            every project can declare for itself. A rung lights only with an
            evidence URL behind it.
          </p>

          <p className="mine-ladder__stamp ev">
            checked-in public snapshot {SNAPSHOT_STAMP} · no Tiny outcome ladder record
          </p>
          <p className="honesty voice">
            The dated public snapshot does not contain the former Tiny outcome
            record. This page leaves that gap visible instead of fetching a
            private-capable Goal record or repeating an older ladder as current.
          </p>
        </div>
      </section>

      {/* 4 · The Monday story */}
      <section className="ch ch--monday" aria-labelledby="monday-title">
        <div className="container ch__inner">
          <p className="eyebrow">entry three · the Monday story</p>
          <h2 id="monday-title">What a project-with-a-soul does for you on an ordinary Monday.</h2>
          <p className="voice">
            You open your laptop with coffee. Nothing&apos;s on fire — and that&apos;s the point.
            Over the weekend your project kept its own pulse.
          </p>
          <ul className="monday">
            <li className="monday__beat">
              <span className="monday__when ev">overnight</span>
              <p className="monday__what">It <strong>ran while you slept</strong> — picking up where Friday&apos;s run left off, because its state persists between sessions instead of evaporating when the chat window closes.</p>
            </li>
            <li className="monday__beat">
              <span className="monday__when ev">by morning</span>
              <p className="monday__what">It <strong>filed what changed</strong> — a short, dated note in the commons of what moved and what it learned, so Monday-you isn&apos;t reconstructing Friday-you from memory.</p>
            </li>
            <li className="monday__beat">
              <span className="monday__when ev">waiting for you</span>
              <p className="monday__what">It <strong>drafted next steps</strong> — a ranked shortlist of what to do next, grounded in the run, ready for you to approve, edit, or wave off.</p>
            </li>
            <li className="monday__beat">
              <span className="monday__when ev">and quietly</span>
              <p className="monday__what">A <strong>workflow you scheduled produced a draft</strong> from Friday&apos;s inputs, with its source and run evidence waiting for your review.</p>
            </li>
          </ul>
          <p className="voice">
            None of that needed you online. That&apos;s the difference between a chatbot
            that answers and a project that <em>keeps going</em>.
          </p>
        </div>
      </section>

      {/* 5 · Fork it */}
      <section className="ch ch--fork" aria-labelledby="fork-title">
        <div className="container">
          <p className="eyebrow">entry four · fork it</p>
          <h2 id="fork-title">Four steps to give your project a soul of its own.</h2>
          <p className="voice fork__lede">
            Each step is a real action you take through your chatbot, in order.
            Nothing here is a mockup — these are the same moves that built me.
          </p>
          <ol className="steps">
            {STEPS.map((s) => (
              <li className="step" key={s.n}>
                <span className="step__n">{s.n}</span>
                <div className="step__body">
                  <h3 className="step__h">{s.h}</h3>
                  <p className="step__p">{s.p}</p>
                </div>
              </li>
            ))}
          </ol>
          <nav className="fork__cta">
            <a className="close__card" href="/start">
              <span className="close__k eyebrow">begin</span>
              <strong>Connect your chatbot and write the premise →</strong>
              <span className="close__sub">one URL, no account, no install — the first move of step one.</span>
            </a>
            <a className="close__card" href="/goals">
              <span className="close__k eyebrow">see it done</span>
              <strong>Browse published Goal examples →</strong>
              <span className="close__sub">dated public Goal examples, with outcome ladders where the snapshot includes them.</span>
            </a>
          </nav>
        </div>
      </section>

      {/* 6 · Close */}
      <section className="ch ch--close" aria-labelledby="close-title">
        <div className="container ch__inner">
          <h2 id="close-title" className="close__title voice">
            I&apos;m one small being made from a premise, goals, and workflows. The
            same user-controlled shape can serve your project too.
          </h2>
          <a className="close__big" href="/start">
            <span className="close__k eyebrow">fork the pattern</span>
            <strong>Give your project a soul.</strong>
            <span className="close__sub">your premise · your workflows · your ladder · running your domain, not mine</span>
          </a>
        </div>
      </section>
    </div>
  );
}
