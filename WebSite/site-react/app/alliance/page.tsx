import type { Metadata } from "next";
import Term from "../../components/Term";
import legal from "../../lib/legal-info.json";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Work with us — Tiny",
  description:
    "Four real ways to bring intent to Tiny: use it and report friction, build with the community on GitHub, reach out about partnership or press, or report a security issue. Every door is public and async.",
  alternates: { canonical: "https://tinyassets.io/alliance" },
};

const GENERAL = legal.contact.general;
const SECURITY = legal.contact.security;
const GH_ISSUES = "https://github.com/Jonnyton/Workflow/issues";

type Channel = {
  eyebrow: string;
  title: string;
  body: string;
  href: string;
  cta: string;
  external?: boolean;
  note?: string;
};

const CHANNELS: Channel[] = [
  {
    eyebrow: "door one · use it",
    title: "Use it, and tell me what broke.",
    body:
      'The most useful thing you can send is friction. Connect your chatbot, run real work, and when something is rough or wrong, say "file a patch request" — your chatbot files it for you, into the public record.',
    href: "/start",
    cta: "how to connect →",
  },
  {
    eyebrow: "door two · build with us",
    title: "Build with the community.",
    body:
      "Want to discuss a design, propose a feature, or contribute code? GitHub is the open forum today. Issues and discussion threads start there, in front of everyone.",
    href: GH_ISSUES,
    cta: "open an issue ↗",
    external: true,
    note: "The whole engine is public — clone it, read the loop, send a pull request.",
  },
  {
    eyebrow: "door three · talk business",
    title: "Partnership, press, or business.",
    body:
      "Anything that does not fit a public thread — a partnership, a press question, evaluator or host coordination — goes to the general contact in writing. Async, like everything else here.",
    href: `mailto:${GENERAL}`,
    cta: GENERAL,
  },
  {
    eyebrow: "door four · report security",
    title: "Report a security issue.",
    body:
      "Found a vulnerability? Mail the security contact directly. Please do not file security issues in the public GitHub tracker — send them here first so they can be handled responsibly.",
    href: `mailto:${SECURITY}`,
    cta: SECURITY,
  },
];

export default function AlliancePage() {
  return (
    <div className={styles.page}>
      <section className="cover" aria-labelledby="cover-title">
        <div className="container ch__inner">
          <p className="eyebrow">field notes · working with me</p>
          <h1 id="cover-title" className="cover__title">Work with me.</h1>
          <p className="voice cover__lede">
            Intent enters through the same doors as everything else. There&apos;s no
            special inbox, no sales funnel, no booked call — a partnership request and
            a bug report walk in the same way the work does: in writing, in the open,
            where the next person can see it. Pick the door that matches what you have
            to say.
          </p>
          <p className="cover__naming">
            A quick orientation: <strong>Tiny</strong> is the being you&apos;re writing to;
            {" "}<strong>Workflow</strong> is the open-source engine he runs on. One body,
            two names — the footer carries the longer version.
          </p>
        </div>
      </section>

      <section className="ch ch--channels" aria-labelledby="channels-title">
        <div className="container">
          <p className="eyebrow">entry two · four doors</p>
          <h2 id="channels-title">Four ways in. Every one of them real.</h2>
          <ul className="channels">
            {CHANNELS.map((c) => (
              <li className="channel" key={c.title}>
                <p className="channel__eyebrow eyebrow">{c.eyebrow}</p>
                <h3 className="channel__title">{c.title}</h3>
                <p className="channel__body">{c.body}</p>
                {c.note ? <p className="channel__note">{c.note}</p> : null}
                {c.external ? (
                  <a className="channel__cta" href={c.href} target="_blank" rel="noreferrer">{c.cta}</a>
                ) : (
                  <a className="channel__cta" href={c.href}>{c.cta}</a>
                )}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="ch ch--how" aria-labelledby="how-title">
        <div className="container ch__inner">
          <p className="eyebrow">entry three · what happens after you knock</p>
          <h2 id="how-title">Where what you send actually goes.</h2>
          <p className="voice">
            A filed item doesn&apos;t vanish into a queue you can&apos;t see. It lands in the{" "}
            <Term def="The public record: goals, workflows, run evidence, and notes — readable by anyone, forkable by anyone. The canonical glossary lives at /commons.">public commons</Term>,
            where my self-patching{" "}
            <Term def="The loop: friction becomes a patch request, runs through investigation and evidence gates, becomes a real GitHub pull request, ships only with a human key.">loop</Term>
            {" "}can investigate it the same way it investigates everything else.
            Nothing ships on a whim — a human still holds every merge key. You can
            watch the whole trail, including the parts that didn&apos;t work.
          </p>
          <a className="btn btn--ghost" href="/loop">watch the loop →</a>

          <div className="keeper">
            <p className="keeper__eyebrow eyebrow">who runs this</p>
            <p className="keeper__body">
              Tiny&apos;s keeper is Jonathan{" "}
              (<a href="https://github.com/Jonnyton" target="_blank" rel="noreferrer">@Jonnyton</a>),
              a single operator; AI agents do much of the building by running through
              the loop. The merge keys are human-held — no agent ships a change on its
              own.
            </p>
          </div>
        </div>
      </section>

      <section className="ch ch--close" aria-labelledby="close-title">
        <div className="container ch__inner">
          <h2 id="close-title" className="sr-only">See the commons</h2>
          <a className="close__cta" href="/commons">
            <span className="close__k eyebrow">the public commons</span>
            <strong>See where everything filed ends up.</strong>
            <span className="close__sub">the public brain — goals, workflows, run evidence, and the glossary for every term on this page</span>
          </a>
        </div>
      </section>
    </div>
  );
}
