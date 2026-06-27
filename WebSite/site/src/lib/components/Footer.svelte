<!--
  Footer — full index + the one canonical naming sentence.
  Every built page is reachable from here; nothing orphaned. The token
  line is one honest sentence pointing at disclosures, not a wallet rack.
-->
<script lang="ts">
  import TinyAssetsMark from './WorkflowMark.svelte';
  import legal from '$lib/content/legal-info.json';

  const year = new Date().getFullYear();
</script>

<footer class="footer">
  <div class="container footer__naming">
    <div class="brand">
      <TinyAssetsMark size={22} />
      <p class="naming">
        <strong>TinyAssets</strong> is the platform. <strong>Tiny</strong> is the
        intelligence you meet inside it: a working persona shaped by the
        founder's will and pointed at real multi-step work. He lives at
        <span class="ev">tinyassets.io</span>; the code still lives on
        <a href="https://github.com/Jonnyton/Workflow" target="_blank" rel="noreferrer">GitHub</a>
        while the repository rename migrates.
      </p>
    </div>
  </div>

  <div class="container footer__grid">
    <div class="col">
      <span class="eyebrow">Use Tiny</span>
      <ul>
        <li><a href="/start">Start — connect a chatbot</a></li>
        <li><a href="/goals">Goals — what's being worked on</a></li>
        <li><a href="/host">Host a daemon</a></li>
        <li><a href="/alliance">Work with us</a></li>
      </ul>
    </div>
    <div class="col">
      <span class="eyebrow">Watch Tiny</span>
      <ul>
        <li><a href="/loop">The loop — how he patches himself</a></li>
        <li><a href="/commons">Commons — the public brain</a></li>
        <li><a href="/graph">Graph — the whole map</a></li>
        <li><a href="/fine-print">Vital signs &amp; fine print</a></li>
      </ul>
    </div>
    <div class="col">
      <span class="eyebrow">Build TinyAssets</span>
      <ul>
        <li><a href="/build">Contribute</a></li>
        <li><a href="/soul">Fork the pattern — souls</a></li>
        <li><a href="https://github.com/Jonnyton/Workflow" target="_blank" rel="noreferrer">GitHub ↗</a></li>
        <li><a href="https://github.com/Jonnyton/Workflow/blob/main/PLAN.md" target="_blank" rel="noreferrer">PLAN.md ↗</a></li>
      </ul>
    </div>
    <div class="col">
      <span class="eyebrow">Fine print</span>
      <ul>
        <li><a href="/legal">Terms &amp; privacy</a></li>
        <li><a href="/legal#token-disclosures">Token disclosures</a></li>
        <li><a href="/legal#risk-factors">Risk factors</a></li>
        <li><a href="/legal#dmca">DMCA</a></li>
      </ul>
    </div>
  </div>

  <div class="container footer__supply">
    <p class="supply-line">
      Money note, in one honest sentence: work and credit settle on a
      <em>test rail</em> today — no real currency moves here, and nothing on
      this site is investment advice. <a href="/legal#token-disclosures">Disclosures →</a>
    </p>
  </div>

  <div class="container footer__bottom">
    <span>© {year} TinyAssets · MIT + CC0 · concept-public, instance-private</span>
    <span class="contact">
      <a href="mailto:{legal.contact.general}">{legal.contact.general}</a> ·
      <a href="mailto:{legal.contact.security}">{legal.contact.security}</a>
    </span>
  </div>
</footer>

<style>
  .footer {
    border-top: 1px solid var(--border-1);
    background: var(--bg-2);
    padding-block: var(--s-8) var(--s-5);
    margin-top: var(--s-16);
  }
  .footer__naming { padding-bottom: var(--s-5); border-bottom: 1px solid var(--border-1); }
  .brand { display: flex; align-items: flex-start; gap: 12px; }
  .naming {
    margin: 0;
    font-family: var(--font-voice);
    font-size: 15px;
    line-height: 1.6;
    color: var(--fg-2);
    max-width: 72ch;
  }
  .naming strong { color: var(--fg-1); font-weight: 600; }

  .footer__grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 24px;
    padding: var(--s-6) 0;
    border-bottom: 1px solid var(--border-1);
  }
  @media (max-width: 700px) { .footer__grid { grid-template-columns: repeat(2, 1fr); } }
  .col ul { list-style: none; padding: 0; margin: 12px 0 0; display: flex; flex-direction: column; gap: 8px; }
  .col li a { color: var(--fg-2); text-decoration: none; font-size: 13px; }
  .col li a:hover { color: var(--ember-700); text-decoration: underline; }

  .footer__supply { padding: var(--s-5) 0; border-bottom: 1px solid var(--border-1); }
  .supply-line { margin: 0; font-size: 13px; color: var(--fg-3); max-width: 80ch; }
  .supply-line em { font-style: italic; color: var(--fg-2); }

  .footer__bottom {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 12px;
    margin-top: var(--s-4);
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--fg-3);
  }
  .contact a { color: var(--fg-2); text-decoration: none; }
  .contact a:hover { color: var(--ember-700); }
</style>
