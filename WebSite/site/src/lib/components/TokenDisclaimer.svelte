<!--
  TokenDisclaimer - reusable safe-harbor block for currency-related surfaces.
  Keeps live Destiny (tiny) references separate from Workflow's test tiny rail.
-->
<script lang="ts">
  import RitualLabel from './Primitives/RitualLabel.svelte';
  import legal from '$lib/content/legal-info.json';

  let { compact = false } = $props<{ compact?: boolean }>();
</script>

{#if compact}
  <p class="compact">
    <strong>Not an investment.</strong>
    Workflow currently uses <code>{legal.token.workflow_test_currency}</code> only. Real <code>{legal.token.display_name}</code> integration is a later roadmap phase; it does not represent equity, profit-sharing, or yield. <a href="/legal#token-disclosures">Full disclosures</a>
  </p>
{:else}
  <aside class="block">
    <RitualLabel color="var(--signal-idle)">Important - token disclosures</RitualLabel>
    <h3>What <code>{legal.token.display_name}</code> is, and what Workflow touches now.</h3>
    <ul>
      <li>
        <strong>Current Workflow rail:</strong> {legal.token.current_workflow_status}
      </li>
      <li>
        <strong>Real currency reference:</strong> {legal.token.display_name} is the live-token naming convention. Workflow keeps that name so testnet messaging matches the eventual real integration.
      </li>
      <li>
        <strong>Rewards model:</strong> {legal.token.rewards_model}
      </li>
      <li>
        <strong>What it is not:</strong> a security, an investment contract, equity, a profit-sharing instrument, or a yield-bearing product. There is no offer to sell securities, no promise of appreciation, no managed-asset backing.
      </li>
      <li>
        <strong>Risk factors:</strong> smart-contract risk, regulatory risk, liquidity risk, and network-failure risk. Holdings are not insured by the FDIC, SIPC, or any government program.
      </li>
      <li>
        <strong>Forward-looking:</strong> roadmap items (Phase 6 outcome ranking, Phase 7 test tiny settlement, Phase 8 real Destiny integration) are intentions, not commitments.
      </li>
    </ul>
    <p class="meta">
      {legal.review_status}. Targeted regulatory framework: {legal.token.regulatory_framework_targeted.join(' + ')}.
      <a href="/legal#token-disclosures">Read full legal page</a>
    </p>
  </aside>
{/if}

<style>
  .compact {
    font-size: 12.5px;
    color: var(--fg-3);
    line-height: 1.55;
    border-left: 2px solid var(--signal-idle);
    padding: 8px 12px;
    background: rgba(217, 168, 74, 0.04);
    border-radius: 0 6px 6px 0;
    margin: 0;
  }
  .compact strong { color: var(--fg-2); }
  .compact code {
    background: rgba(255, 255, 255, 0.06);
    padding: 1px 5px;
    border-radius: 3px;
    font-family: var(--font-mono);
    font-size: 11.5px;
  }
  .compact a {
    color: var(--ember-600);
    text-decoration: none;
    margin-left: 4px;
  }
  .compact a:hover { text-decoration: underline; }

  .block {
    background: rgba(217, 168, 74, 0.04);
    border: 1px solid rgba(217, 168, 74, 0.25);
    border-radius: 12px;
    padding: 22px 24px;
    margin: 24px 0;
  }
  .block h3 {
    font-family: var(--font-display);
    font-size: 22px;
    font-weight: 500;
    letter-spacing: 0;
    margin: 12px 0 14px;
    color: var(--fg-1);
  }
  .block h3 code {
    background: rgba(255, 255, 255, 0.06);
    padding: 2px 8px;
    border-radius: 4px;
    font-family: var(--font-mono);
    font-size: 18px;
  }
  .block ul {
    list-style: none;
    padding: 0;
    margin: 0 0 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .block li {
    font-size: 13.5px;
    color: var(--fg-2);
    line-height: 1.6;
  }
  .block li strong { color: var(--fg-1); font-weight: 600; }
  .block .meta {
    font-size: 12px;
    color: var(--fg-3);
    font-style: italic;
    margin: 0;
    padding-top: 12px;
    border-top: 1px solid var(--border-1);
  }
  .block .meta a {
    color: var(--ember-600);
    text-decoration: none;
    font-style: normal;
  }
  .block .meta a:hover { text-decoration: underline; }
</style>
