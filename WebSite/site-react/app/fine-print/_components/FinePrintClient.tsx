"use client";

import Term from "../../../components/Term";
import VitalSigns from "../../../components/VitalSigns";
import baked from "../../../lib/mcp-snapshot.json";
import { fmtStampStable } from "../../../lib/fmt";
import styles from "../page.module.css";

const GH_ACTIONS = "https://github.com/Jonnyton/TinyAssets/actions";
const MCP_BARE = "tinyassets.io/mcp";
const bakedFetchedAt: string = baked.fetched_at ?? "";

const UPTIME_CHECKS = [
  {
    file: "uptime-canary.yml",
    what: "Probes the public MCP endpoint on a schedule and after any DNS, tunnel, or Worker change — the out-of-band check that catches a silently-dropped route.",
  },
];

export default function FinePrintClient() {
  const bakedStamp = bakedFetchedAt ? fmtStampStable(bakedFetchedAt) : "";

  return (
    <div className={styles.page}>
      <section className="cover" aria-labelledby="cover-title">
        <div className="container cover__inner">
          <p className="eyebrow">field notes · the ops room</p>
          <h1 id="cover-title" className="cover__title">The instrument panel.</h1>
          <p className="cover__lede">
            Every other page on this site makes a claim. This one explains how the
            claims are measured, what the engine reports about itself, and who
            watches it when no human is looking. No marketing here — just the
            readings and the fine print.
          </p>
          <p className="cover__caption voice">
            — if I&apos;m asleep, this page says so before I do.
          </p>
          <VitalSigns variant="hero" />
          <p className="cover__stamp ev">
            first paint seeded from snapshot {bakedStamp} · every reading
            above is upgraded by a live read on load and carries its own stamp
          </p>
        </div>
      </section>

      <section id="vitals" className="ch" aria-labelledby="vitals-title">
        <div className="container ch__inner">
          <p className="eyebrow">entry one · how the pulse is measured</p>
          <h2 id="vitals-title">Four readings, in plain words.</h2>
          <p className="voice vitals__lede">
            — the pulse strip up top is four separate facts, never collapsed into
            one. Here&apos;s exactly what each one means, so a green dot can never bluff
            you.
          </p>

          <dl className="measures">
            <div className="measure">
              <dt><span className="dot live" aria-hidden="true"></span> server live</dt>
              <dd>
                The <Term def="MCP — the Model Context Protocol. The open standard chatbots use to add outside tools. Tiny is one such tool.">MCP</Term>
                {" "}endpoint at <code>{MCP_BARE}</code> answered <em>this browser&apos;s</em>
                call, just now. It&apos;s reachability measured from where you&apos;re sitting —
                not a status page someone typed by hand. If the call fails, the strip
                says unreachable and shows the real error.
              </dd>
            </div>
            <div className="measure">
              <dt><span className="dot idle" aria-hidden="true"></span> workflow activity</dt>
              <dd>
                A public universe shows activity within the last hour, <em>or</em> a
                user-authored run is executing right now. If neither is true, the
                strip reports no recent workflow activity. This is separate from
                server uptime: activity cannot make the server healthy, and uptime
                cannot prove that user work is moving.
              </dd>
            </div>
            <div className="measure">
              <dt><span className="dot" aria-hidden="true"></span> lifetime runs</dt>
              <dd>
                Public queue counters are unavailable. This browser does not
                request operator status merely to display lifetime run totals.
              </dd>
            </div>
            <div className="measure">
              <dt><span className="dot" aria-hidden="true"></span> deployed</dt>
              <dd>
                A public release receipt is unavailable. The checked-in site
                snapshot is page provenance, not proof of which engine image is
                deployed.
              </dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="ch ch--receipt" aria-labelledby="receipt-title">
        <div className="container ch__inner">
          <p className="eyebrow">entry two · release provenance</p>
          <h2 id="receipt-title">Public release receipt unavailable.</h2>
          <p className="receipt__lede">
            This browser does not download the operator status payload. The
            checked-in public site snapshot is dated {bakedStamp}, but that date
            is not a deployment attestation.
          </p>

          <div className="receipt" aria-live="polite" data-state="unavailable">
            <p className="receipt__msg ev">
              <span className="dot idle" aria-hidden="true"></span>
              release details unavailable on the public website
            </p>
            <p className="receipt__note">
              Build and deploy workflow history remains available from GitHub
              without treating it as an engine-signed release receipt.
            </p>
            <div className="receipt__links">
              <a href={GH_ACTIONS} target="_blank" rel="noreferrer">GitHub Actions ↗</a>
            </div>
          </div>
        </div>
      </section>

      <section className="ch ch--watch" aria-labelledby="watch-title">
        <div className="container ch__inner">
          <p className="eyebrow">entry three · independent uptime evidence</p>
          <h2 id="watch-title">How reachability is checked from outside.</h2>
          <p className="watch__lede">
            A public GitHub Action probes the live system on a schedule. Its run
            history, pass and fail, is visible on the Actions tab. It observes
            platform uptime only; it does not dispatch, repair, or represent user work.
          </p>
          <ul className="watch">
            {UPTIME_CHECKS.map((w) => (
              <li className="watch__item" key={w.file}>
                <code className="watch__file">{w.file}</code>
                <p className="watch__what">{w.what}</p>
              </li>
            ))}
          </ul>
          <p className="watch__foot">
            <a href={GH_ACTIONS} target="_blank" rel="noreferrer">Open the Actions tab on GitHub ↗</a>
            {" "}— the live run history is the truth, not this page.
          </p>
        </div>
      </section>

      <section className="ch ch--legal" aria-labelledby="legal-title">
        <div className="container ch__inner">
          <p className="eyebrow">entry four · the fine print</p>
          <h2 id="legal-title">The part that has to be exact.</h2>
          <p className="legal__money voice">
            On money: any value or credit moving through Tiny today settles on a
            {" "}<em>test rail</em> — there&apos;s no payment method to ask for and nothing to
            buy. <strong>Nothing on this site is investment advice, and none of it
            represents equity, profit-sharing, or a price prediction.</strong>
          </p>
          <ul className="legal">
            <li className="legal__item">
              <a className="legal__link" href="/legal">Terms, token disclosures, risk &amp; DMCA →</a>
              <p className="legal__note">The full legal page: terms of use, token / currency disclosures, the risk statement, and the DMCA / takedown path.</p>
            </li>
          </ul>
        </div>
      </section>

      <section className="ch ch--close" aria-labelledby="close-title">
        <div className="container ch__inner">
          <h2 id="close-title">Seen the gauges. Now watch the work.</h2>
          <nav className="close__cards">
            <a className="close__card" href="/loop">
              <span className="close__k eyebrow">workflow activity</span>
              <strong>See public workflow graphs →</strong>
              <span className="close__sub">Public graph activity with explicit provenance, kept separate from uptime evidence.</span>
            </a>
            <a className="close__card" href="/commons">
              <span className="close__k eyebrow">the public commons</span>
              <strong>Browse the brain — and the glossary →</strong>
              <span className="close__sub">every term of art, plus the searchable wiki it all reads from.</span>
            </a>
          </nav>
        </div>
      </section>
    </div>
  );
}
