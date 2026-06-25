import * as React from "react";
import Link from "next/link";
import { WorkflowMark } from "./WorkflowMark";
import legal from "../lib/legal-info.json";
import styles from "./Footer.module.css";

export function Footer() {
  const year = 2026;
  const contact = (legal as any)?.contact ?? {};
  return (
    <footer className={styles.footer}>
      <div className={`container ${styles.naming}`}>
        <div className={styles.brand}>
          <WorkflowMark size={22} />
          <p className={styles.namingText}>
            <strong>Tiny</strong> is the public face of <strong>Workflow</strong> — an open-source
            engine that runs real multi-step work for any goal. He lives at{" "}
            <span className="ev">tinyassets.io</span>; his code lives on{" "}
            <a href="https://github.com/Jonnyton/Workflow" target="_blank" rel="noreferrer">GitHub</a>.
            Same thing, one body, two names.
          </p>
        </div>
      </div>

      <div className={`container ${styles.grid}`}>
        <div className={styles.col}>
          <span className="eyebrow">Use him</span>
          <ul>
            <li><Link href="/start">Start — connect a chatbot</Link></li>
            <li><Link href="/goals">Goals — what&apos;s being worked on</Link></li>
            <li><Link href="/host">Host a daemon</Link></li>
            <li><Link href="/alliance">Work with us</Link></li>
          </ul>
        </div>
        <div className={styles.col}>
          <span className="eyebrow">Watch him</span>
          <ul>
            <li><Link href="/loop">The loop — how he patches himself</Link></li>
            <li><Link href="/commons">Commons — the public brain</Link></li>
            <li><Link href="/graph">Graph — the whole map</Link></li>
            <li><Link href="/fine-print">Vital signs &amp; fine print</Link></li>
          </ul>
        </div>
        <div className={styles.col}>
          <span className="eyebrow">Build him</span>
          <ul>
            <li><Link href="/build">Contribute</Link></li>
            <li><Link href="/soul">Fork the pattern — souls</Link></li>
            <li><a href="https://github.com/Jonnyton/Workflow" target="_blank" rel="noreferrer">GitHub ↗</a></li>
            <li><a href="https://github.com/Jonnyton/Workflow/blob/main/PLAN.md" target="_blank" rel="noreferrer">PLAN.md ↗</a></li>
          </ul>
        </div>
        <div className={styles.col}>
          <span className="eyebrow">Fine print</span>
          <ul>
            <li><Link href="/legal">Terms &amp; privacy</Link></li>
            <li><Link href="/legal#token-disclosures">Token disclosures</Link></li>
            <li><Link href="/legal#risk-factors">Risk factors</Link></li>
            <li><Link href="/legal#dmca">DMCA</Link></li>
          </ul>
        </div>
      </div>

      <div className={`container ${styles.supply}`}>
        <p className={styles.supplyLine}>
          Money note, in one honest sentence: work and credit settle on a{" "}
          <em>test rail</em> today — no real currency moves here, and nothing on
          this site is investment advice. <Link href="/legal#token-disclosures">Disclosures →</Link>
        </p>
      </div>

      <div className={`container ${styles.bottom}`}>
        <span>© {year} Tiny Assets · MIT + CC0 · concept-public, instance-private</span>
        <span className={styles.contact}>
          {contact.general && <a href={`mailto:${contact.general}`}>{contact.general}</a>}
          {contact.general && contact.security && " · "}
          {contact.security && <a href={`mailto:${contact.security}`}>{contact.security}</a>}
        </span>
      </div>
    </footer>
  );
}

export default Footer;
