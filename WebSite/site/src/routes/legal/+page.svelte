<!--
  /legal — Draft v0. Pending securities-counsel review.
  Separates the real Destiny (tiny) reference from Workflow's current test tiny rail;
  written to also be defensible under proposed CLARITY Act framework.

  This is NOT legal advice. A securities lawyer must review every claim
  before public launch. See WebSite/07-legal-pass-notes.md for review checklist.
-->
<script lang="ts">
  import RitualLabel from '$lib/components/Primitives/RitualLabel.svelte';
  import TokenDisclaimer from '$lib/components/TokenDisclaimer.svelte';
  import legal from '$lib/content/legal-info.json';
</script>

<svelte:head>
  <title>Legal — Workflow</title>
  <meta name="description" content="License, terms, privacy, and token disclosures for Workflow, test tiny, and the Destiny (tiny) reference." />
</svelte:head>

<section class="legal">
  <div class="wrap">
    <RitualLabel>· Legal · {legal.version} · effective {legal.effective_date} ·</RitualLabel>
    <h1>Legal.</h1>
    <p class="status">{legal.review_status}.</p>
    <p class="lead">
      Workflow is open-source software under MIT. Public goal content is CC0-1.0. Current Workflow settlement testing uses <code>test tiny</code> on Base Sepolia. The real currency reference is <code>{legal.token.display_name}</code>, and real-token integration is deferred.
    </p>

    <nav class="toc" aria-label="On this page">
      <span class="toc__label">On this page</span>
      <a href="#license">License</a>
      <a href="#privacy">Privacy</a>
      <a href="#terms">Terms of use</a>
      <a href="#token-disclosures">Token disclosures</a>
      <a href="#risk-factors">Risk factors</a>
      <a href="#dmca">DMCA</a>
      <a href="#dispute">Disputes</a>
      <a href="#references">References</a>
      <a href="#contact">Contact</a>
    </nav>

    <h2 id="license">License</h2>
    <ul>
      <li><strong>Platform code</strong> (engine, MCP gateway, tray, connectors): <a href="https://github.com/Jonnyton/Workflow/blob/main/LICENSE" target="_blank" rel="noreferrer">MIT</a>. Fork it, run it, sell services on it. Attribution required.</li>
      <li><strong>Public wiki content</strong> (work targets, branches, nodes, prompt templates, gates, wiki pages): <a href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank" rel="noreferrer">CC0-1.0</a>. Public domain. Use without permission.</li>
      <li><strong>This site</strong>: same MIT for site code, CC0 for site content where original; fonts retain their respective licenses (IBM Plex Sans/Mono, Fraunces — all OFL).</li>
    </ul>

    <h2 id="privacy">Privacy</h2>
    <p><strong>Concept-layer public; instance-layer private; never training data.</strong> The <em>shape</em> of your workflow (which nodes, what edges, what state schema) is public — that's the commons. The <em>contents</em> you process (your documents, your prompts, your fills) stay on your machine or in owner-only storage. We do not train models on your data and never will.</p>
    <p>Per-piece visibility is judged by your chatbot per request, not by us. <strong>The chatbot proposes; you confirm. No cached consent.</strong></p>
    <p>You may export or delete your data at any time. The <code>/account</code> page (Phase 2) provides a 30-day grace-window deletion flow per CCPA / GDPR Article 17.</p>
    <p><strong>Cookies / analytics:</strong> we plan to use Plausible (privacy-friendly, no PII, no third-party trackers). No advertising cookies, no cross-site tracking pixels.</p>
    <p><strong>Chatbot connector data.</strong> When you use Workflow through ChatGPT, Claude, or another MCP client, the connector receives the specific tool inputs needed for your request, such as goal names, goal descriptions, tags, visibility, request text, and optional universe or branch identifiers. It may return Workflow status, goal, branch, wiki, run, queue, and daemon metadata needed to answer you. Directory-safe status responses redact raw activity logs, recent-call diagnostics, local filesystem paths, host account identifiers, and internal policy hashes.</p>
    <p><strong>Connector retention.</strong> Public goal proposals and public wiki/work records are durable project records. Queued Workflow requests and operational metadata are retained as long as needed to run, debug, audit, and improve the Workflow loop. We do not ask for passwords, API keys, MFA codes, payment card data, government IDs, biometrics, SSNs, PHI, or PCI data through the public directory connector.</p>
    <p><strong>Minimum age.</strong> Workflow is not directed at children. You must be at least <strong>18 years old</strong> to use the service or hold a wallet connection. We self-declare age at wallet-connect; misrepresentation is grounds for termination. We do not knowingly collect data from minors; if you believe we have, contact <a href="mailto:{legal.contact.legal}">{legal.contact.legal}</a>.</p>

    <h2 id="terms">Terms of use</h2>
    <p>By using Workflow (the website, the MCP gateway at <code>tinyassets.io/mcp</code>, or the daemon tray), you agree to these terms. If you do not agree, do not use the service.</p>
    <h3>Acceptable use</h3>
    <ul>
      <li>You will not attempt to bypass moderation, abuse the paid-market with sybil daemon-hosts, or operate fraud-pattern accounts.</li>
      <li>You will not use Workflow to generate or distribute content that is illegal in your jurisdiction or that violates third-party rights.</li>
      <li>You will respect the rate limits and account-age gates that protect the system.</li>
      <li>You will not use Workflow to violate sanctions law (OFAC / equivalent).</li>
    </ul>
    <h3>Geographic restrictions</h3>
    <p>The service is not available in jurisdictions comprehensively sanctioned by OFAC (currently: Cuba, Iran, North Korea, Russia/Crimea, Syria) or where local law prohibits transacting in utility tokens (currently: People's Republic of China). We screen wallet connections via {legal.geo_restrictions.enforcement_layer}. By using the service you represent that you are not a resident of, or accessing from, a blocked jurisdiction.</p>
    <h3>Your content</h3>
    <p>You retain all rights to data you process through Workflow. By publishing a node, branch, or goal to the public goal set, you license that artifact under CC0-1.0, irrevocably. Private workflows stay private — see Privacy above.</p>
    <h3>Our service</h3>
    <p>We provide the platform "as is". We do not guarantee uptime, output quality, or specific economic outcomes. Where the platform routes your work to a daemon-host, the host runs your work according to the protocol; we are not the host.</p>
    <h3>Termination</h3>
    <p>We may suspend or terminate accounts that violate these terms. You may stop using the service at any time and delete your account.</p>

    <h2 id="token-disclosures">Token disclosures</h2>
    <TokenDisclaimer />
    <h3>Classification framework</h3>
    <p>This section separates token identity from current Workflow integration. The real currency reference is <strong><code>{legal.token.display_name}</code></strong>; the current Workflow rail is <strong><code>{legal.token.workflow_test_currency}</code></strong>.</p>
    <p>Under the SEC's April 2026 interpretive release on crypto-asset categorization (the "Project Crypto" framework), digital assets are classified into five categories: digital commodities, digital collectibles, digital tools, payment stablecoins, and digital securities. If real Workflow settlement opens, <strong><code>{legal.token.display_name}</code> is intended to function as a digital tool and/or digital commodity</strong> for paid-market participation, deriving value from the programmatic operation of the protocol.</p>
    <p><code>{legal.token.symbol}</code> is also intended to qualify under the "mature blockchain system" carve-out contemplated by the Digital Asset Market Clarity Act (H.R. 3633) once the Workflow protocol meets the decentralization and functional-use criteria established by the Act in its final form.</p>
    <h3>What Destiny (tiny) is</h3>
    <ul>
      <li>The real currency reference for the future Workflow paid-market and governance messaging.</li>
      <li>Multi-chain reference contracts: BASE Chain (primary), PulseChain, and BSC legacy migration reference.</li>
      <li>Not currently paid by Workflow; daemon-host rewards remain on the Base Sepolia <code>test tiny</code> rail until real integration opens.</li>
    </ul>
    <h3>What Workflow touches now</h3>
    <ul>
      <li><code>test tiny</code> on Base Sepolia for roadmap testing and settlement simulation.</li>
      <li>No mainnet <code>{legal.token.symbol}</code> payouts, staking, DAO votes, or treasury flows in current Workflow surfaces.</li>
      <li>Real contract addresses are shown as reference-only so the live naming stays consistent before cutover.</li>
    </ul>
    <h3>What tiny is not</h3>
    <ul>
      <li>Not a security, not an investment contract, not equity, not a debt instrument.</li>
      <li>Not a yield-bearing product. No passive return for holding.</li>
      <li>Not backed by a managed pool of assets, fund, treasury investments, or any income-producing portfolio. Prior site language using the phrase "Portfolio Backed Currency" is deprecated and does not reflect the current protocol.</li>
      <li>Not insured. Not FDIC-insured, not SIPC-protected, not government-backed.</li>
    </ul>
    <h3>No offer to sell</h3>
    <p>This site does not constitute an offer or solicitation to sell securities. Existing <code>{legal.token.symbol}</code> contracts are reference-only for Workflow today; no new offering is being made through this site. Any future real-token settlement must open as an explicit roadmap phase.</p>
    <h3>KYC / AML</h3>
    <p>Tier-1 chatbot users (browse, run free-tier daemons) do not require KYC. Tier-2 daemon hosts are subject to identity verification at a cumulative lifetime paid-market threshold of <strong>USD 1,000</strong> via a third-party KYC provider (Sumsub, Persona, or Onfido). Treasury operations involve full KYC. Wallet connections are screened against the OFAC sanctions list in real time.</p>
    <h3>Tax</h3>
    <p>Real-token payouts are disabled at v0. If real <code>{legal.token.display_name}</code> payouts later open, you are responsible for the tax treatment of any token received, spent, or disposed of in your jurisdiction. We are not a tax advisor. Consult a qualified tax professional.</p>

    <h2 id="risk-factors">Risk factors</h2>
    <p>Use of <code>{legal.token.display_name}</code>, <code>test tiny</code>, and the Workflow platform involves risks. Read these carefully.</p>
    <ul>
      <li><strong>Smart-contract risk.</strong> Real contracts on BASE/PulseChain/BSC are unaudited at this draft. Bugs, exploits, or upgrade events may result in total or partial loss of <code>{legal.token.symbol}</code> holdings once real integration exists.</li>
      <li><strong>Regulatory risk.</strong> The legal classification of crypto assets is evolving. The CLARITY Act has not yet passed the Senate. Future regulation (US or foreign) may restrict the utility of <code>{legal.token.symbol}</code>, require KYC, or prohibit certain uses in certain jurisdictions.</li>
      <li><strong>Liquidity risk.</strong> There is no guaranteed market for <code>{legal.token.symbol}</code>. Trading volume on any specific venue may be thin or zero.</li>
      <li><strong>Network risk.</strong> Base Sepolia, BASE, PulseChain, BSC, and any future chain may experience outages, reorgs, or fee spikes that affect test or real-token transactions.</li>
      <li><strong>Protocol-evolution risk.</strong> Phase 6 (outcome ranking), Phase 7 (settlement contracts), Phase 8 (DAO governance) are forward-looking. Plans may change. Voting outcomes may produce protocol changes that affect token utility.</li>
      <li><strong>Counterparty risk.</strong> When you place a paid bid, you are entrusting work to a daemon-host whose only commitment is the protocol. Refunds and disputes are mediated by the protocol's gate-window mechanism, not by us.</li>
      <li><strong>Phishing / impersonation.</strong> The canonical site is <code>tinyassets.io</code>, the canonical MCP URL is <code>tinyassets.io/mcp</code>, the canonical repo is <code>github.com/Jonnyton/Workflow</code>. Anything else is not us.</li>
    </ul>

    <h2 id="dmca">DMCA</h2>
    <p>If you believe content on the public community wiki infringes your copyright, send a DMCA takedown notice to <a href="mailto:{legal.contact.dmca_agent}">{legal.contact.dmca_agent}</a> including: identification of the work, identification of the infringing material with URL, your contact info, statement of good-faith belief, statement under penalty of perjury, and your physical or electronic signature.</p>
    <p>Counter-notices follow standard <a href="https://www.copyright.gov/dmca/" target="_blank" rel="noreferrer">17 U.S.C. § 512</a> procedure. Designated DMCA agent registration with the U.S. Copyright Office is in progress.</p>

    <h2 id="dispute">Disputes &amp; governing law</h2>
    <p><strong>Governing law.</strong> These terms are governed by {legal.jurisdiction.governing_law}.</p>
    <p><strong>Dispute resolution.</strong> {legal.jurisdiction.dispute_resolution}. By using the service you waive your right to participate in a class action; mass-arbitration coordination is also prohibited. You retain the right to bring an individual claim in small-claims court.</p>
    <p><strong>Injunctive relief.</strong> Either party may seek injunctive relief in {legal.jurisdiction.venue_for_injunctive} for IP infringement, breach of confidentiality, or platform-abuse claims that arbitration cannot timely address.</p>
    <p><strong>Liability cap.</strong> {legal.jurisdiction.liability_cap}. We disclaim consequential, indirect, special, and punitive damages. We do not exclude liability that cannot be excluded by law (e.g. willful misconduct, gross negligence in some jurisdictions; consumer-protection statutes in some US states and EU member states).</p>
    <p><strong>Indemnification.</strong> You will indemnify us for misuse of the service, IP infringement in your content, sanctions-law violations, and false geo-attestations. We will indemnify you for IP infringement of the platform code within the scope of the MIT license, capped at the liability limit above.</p>
    <p><strong>Force majeure.</strong> Neither party is liable for delay or failure caused by events beyond reasonable control: {legal.force_majeure.join("; ")}. We may suspend performance for up to 30 days; longer suspensions trigger pro-rated refund of any prepaid fees.</p>
    <p><strong>Severability + entire agreement.</strong> If any provision is unenforceable, the rest survives. These terms are the entire agreement between you and us regarding the service.</p>

    <h2 id="references">References</h2>
    <ul>
      <li><a href="https://github.com/Jonnyton/Workflow/blob/main/LICENSE" target="_blank" rel="noreferrer">Workflow MIT license</a>.</li>
      <li><a href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank" rel="noreferrer">CC0-1.0 public-domain dedication</a> for public catalog content.</li>
      <li><a href="https://github.com/Jonnyton/Workflow/blob/main/CONTRIBUTING.md" target="_blank" rel="noreferrer">Contributor response and review process</a>.</li>
      <li><a href="https://github.com/Jonnyton/Workflow/blob/main/WebSite/07-legal-pass-notes.md" target="_blank" rel="noreferrer">Website legal-pass notes</a> tracking open counsel-review items.</li>
    </ul>

    <h2 id="contact">Contact</h2>
    <p>
      General: <a href="mailto:{legal.contact.general}">{legal.contact.general}</a><br>
      Security: <a href="mailto:{legal.contact.security}">{legal.contact.security}</a><br>
      Legal: <a href="mailto:{legal.contact.legal}">{legal.contact.legal}</a><br>
      DMCA agent: <a href="mailto:{legal.contact.dmca_agent}">{legal.contact.dmca_agent}</a>
    </p>
    <p>Response SLA per <a href="https://github.com/Jonnyton/Workflow/blob/main/CONTRIBUTING.md" target="_blank" rel="noreferrer">CONTRIBUTING.md</a> — 48h first response, 5 calendar days for full review.</p>

    <hr />
    <p class="footer-note">
      <strong>Not legal advice.</strong> This page is informational. It does not establish a lawyer-client relationship and is not a substitute for advice from your own counsel. Substantive provisions are pending review by a US securities attorney with crypto practice. Targeted regulatory framework: SEC Project Crypto (April 2026) + the Digital Asset Market Clarity Act (H.R. 3633) once enacted in final form.
    </p>
  </div>
</section>

<style>
  .legal { padding-block: 80px; }
  .wrap {
    max-width: 760px;
    margin: 0 auto;
    padding-inline: clamp(16px, 4vw, 32px);
    color: var(--fg-2);
  }
  h1 {
    font-family: var(--font-display);
    font-size: clamp(48px, 8vw, 72px);
    font-weight: 400;
    letter-spacing: -0.035em;
    line-height: 0.95;
    margin: 14px 0 8px;
  }
  h2 {
    font-family: var(--font-display);
    font-size: 28px;
    font-weight: 500;
    margin: 40px 0 14px;
    color: var(--fg-1);
    letter-spacing: -0.015em;
    scroll-margin-top: 80px;
  }
  h3 {
    font-family: var(--font-sans);
    font-size: 16px;
    font-weight: 600;
    margin: 22px 0 8px;
    color: var(--fg-1);
  }
  .status {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--signal-idle);
    text-transform: uppercase;
    letter-spacing: 0.14em;
    margin: 0 0 16px;
  }
  .lead {
    font-size: 16px;
    line-height: 1.6;
    margin: 0 0 16px;
  }
  .lead code {
    background: rgba(255,255,255,0.06);
    padding: 1px 5px;
    border-radius: 3px;
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--violet-200);
  }

  .toc {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 16px;
    align-items: center;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: 10px;
    padding: 14px 18px;
    margin: 24px 0 32px;
  }
  .toc__label {
    font-family: var(--font-mono);
    font-size: 10px;
    color: var(--fg-3);
    text-transform: uppercase;
    letter-spacing: 0.14em;
  }
  .toc a {
    font-family: var(--font-mono);
    font-size: 11.5px;
    color: var(--ember-600);
    text-decoration: none;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  .toc a:hover { text-decoration: underline; }

  ul {
    padding-left: 22px;
    line-height: 1.7;
    margin: 0 0 16px;
    font-size: 14px;
  }
  ul li { margin-bottom: 6px; }
  p {
    line-height: 1.7;
    margin: 0 0 14px;
    font-size: 14.5px;
  }
  code {
    background: rgba(255,255,255,0.06);
    border: 1px solid var(--border-1);
    padding: 1px 5px;
    border-radius: 3px;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--violet-200);
  }
  hr {
    border: 0;
    border-top: 1px solid var(--border-1);
    margin: 32px 0;
  }
  .footer-note {
    font-size: 12.5px;
    color: var(--fg-3);
    line-height: 1.6;
    background: rgba(217, 168, 74, 0.04);
    border-left: 2px solid var(--signal-idle);
    padding: 12px 16px;
    border-radius: 0 6px 6px 0;
  }
  .footer-note strong { color: var(--fg-2); }
</style>
