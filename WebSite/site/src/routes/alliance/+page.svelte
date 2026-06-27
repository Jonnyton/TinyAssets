<!--
  /alliance — "Work with us": intake. "Field Notes" rebuild, 2026-06-09.

  A calm routing page, not a dashboard. No stats hero, no live reads — intent
  enters through the same public doors as every other kind of work, so this
  page's whole job is to point at the four real doors and explain, honestly,
  what happens after you knock.

  Honesty rails honored: no baked number presented as live (this page reads
  nothing live, by design); every clickable goes somewhere real — a route, a
  GitHub surface, or a mailto to a real address from legal-info.json; first
  use of terms of art gets <Term>; the canonical glossary lives at /commons.
  Contacts are read from src/lib/content/legal-info.json, not hardcoded.
-->
<script lang="ts">
  import Term from '$lib/components/Term.svelte';
  import legal from '$lib/content/legal-info.json';

  const GENERAL = legal.contact.general;
  const SECURITY = legal.contact.security;
  const GH_REPO = 'https://github.com/Jonnyton/TinyAssets';
  const GH_ISSUES = 'https://github.com/Jonnyton/TinyAssets/issues';

  // Four real channels. Each card carries one real action — a route, a GitHub
  // surface, or a mailto to a real address. No fake form, no booked call, no
  // dead-end "watch this space" card.
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
      eyebrow: 'door one · use it',
      title: 'Use it, and tell me what broke.',
      body:
        'The most useful thing you can send is friction. Connect your chatbot, run real work, and when something is rough or wrong, say "file a patch request" — your chatbot files it for you, into the public record.',
      href: '/start',
      cta: 'how to connect →'
    },
    {
      eyebrow: 'door two · build with us',
      title: 'Build with the community.',
      body:
        'Want to discuss a design, propose a feature, or contribute code? GitHub is the open forum today. Issues and discussion threads start there, in front of everyone.',
      href: GH_ISSUES,
      cta: 'open an issue ↗',
      external: true,
      note: 'The whole engine is public — clone it, read the loop, send a pull request.'
    },
    {
      eyebrow: 'door three · talk business',
      title: 'Partnership, press, or business.',
      body:
        'Anything that does not fit a public thread — a partnership, a press question, evaluator or host coordination — goes to the general contact in writing. Async, like everything else here.',
      href: `mailto:${GENERAL}`,
      cta: GENERAL
    },
    {
      eyebrow: 'door four · report security',
      title: 'Report a security issue.',
      body:
        'Found a vulnerability? Mail the security contact directly. Please do not file security issues in the public GitHub tracker — send them here first so they can be handled responsibly.',
      href: `mailto:${SECURITY}`,
      cta: SECURITY
    }
  ];
</script>

<svelte:head>
  <title>Work with us — Tiny</title>
  <meta
    name="description"
    content="Four real ways to bring intent to Tiny: use it and report friction, build with the community on GitHub, reach out about partnership or press, or report a security issue. Every door is public and async."
  />
</svelte:head>

<!-- 1 · Hero — Tiny's voice, no stats ──────────────────────────────────── -->
<section class="cover" aria-labelledby="cover-title">
  <div class="container ch__inner">
    <p class="eyebrow">field notes · working with me</p>
    <h1 id="cover-title" class="cover__title">Work with me.</h1>
    <p class="voice cover__lede">
      Intent enters through the same doors as everything else. There's no
      special inbox, no sales funnel, no booked call — a partnership request and
      a bug report walk in the same way the work does: in writing, in the open,
      where the next person can see it. Pick the door that matches what you have
      to say.
    </p>
    <p class="cover__naming">
      A quick orientation: <strong>Tiny</strong> is the being you're writing to;
      <strong>TinyAssets</strong> is the open-source platform he runs on. The
      footer carries the longer version.
    </p>
  </div>
</section>

<!-- 2 · Four real channels ─────────────────────────────────────────────── -->
<section class="ch ch--channels" aria-labelledby="channels-title">
  <div class="container">
    <p class="eyebrow">entry two · four doors</p>
    <h2 id="channels-title">Four ways in. Every one of them real.</h2>
    <ul class="channels">
      {#each CHANNELS as c (c.title)}
        <li class="channel">
          <p class="channel__eyebrow eyebrow">{c.eyebrow}</p>
          <h3 class="channel__title">{c.title}</h3>
          <p class="channel__body">{c.body}</p>
          {#if c.note}
            <p class="channel__note">{c.note}</p>
          {/if}
          {#if c.external}
            <a class="channel__cta" href={c.href} target="_blank" rel="noreferrer">{c.cta}</a>
          {:else}
            <a class="channel__cta" href={c.href}>{c.cta}</a>
          {/if}
        </li>
      {/each}
    </ul>
  </div>
</section>

<!-- 3 · How intake is processed ────────────────────────────────────────── -->
<section class="ch ch--how" aria-labelledby="how-title">
  <div class="container ch__inner">
    <p class="eyebrow">entry three · what happens after you knock</p>
    <h2 id="how-title">Where what you send actually goes.</h2>
    <p class="voice">
      A filed item doesn't vanish into a queue you can't see. It lands in the
      <Term def="The public record: goals, workflows, run evidence, and notes — readable by anyone, forkable by anyone. The canonical glossary lives at /commons.">public commons</Term>,
      where my self-patching <Term def="The loop: friction becomes a patch request, runs through investigation and evidence gates, becomes a real GitHub pull request, ships only with a human key.">loop</Term>
      can investigate it the same way it investigates everything else.
      Nothing ships on a whim — a human still holds every merge key. You can
      watch the whole trail, including the parts that didn't work.
    </p>
    <a class="btn btn--ghost" href="/loop">watch the loop →</a>

    <div class="keeper">
      <p class="keeper__eyebrow eyebrow">who runs this</p>
      <p class="keeper__body">
        Tiny's keeper is Jonathan
        (<a href="https://github.com/Jonnyton" target="_blank" rel="noreferrer">@Jonnyton</a>),
        a single operator; AI agents do much of the building by running through
        the loop. The merge keys are human-held — no agent ships a change on its
        own.
      </p>
    </div>
  </div>
</section>

<!-- 4 · Close → /commons ───────────────────────────────────────────────── -->
<section class="ch ch--close" aria-labelledby="close-title">
  <div class="container ch__inner">
    <h2 id="close-title" class="sr-only">See the commons</h2>
    <a class="close__cta" href="/commons">
      <span class="close__k eyebrow">the public commons</span>
      <strong>See where everything filed ends up.</strong>
      <span class="close__sub">the public brain — goals, workflows, run evidence, and the glossary for every term on this page</span>
    </a>
  </div>
</section>

<style>
  .container { max-width: 1160px; margin: 0 auto; padding-inline: clamp(18px, 4vw, 32px); }
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }

  .btn {
    display: inline-block;
    font-family: var(--font-sans);
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.01em;
    padding: 11px 22px;
    border-radius: var(--radius-pill);
    text-decoration: none;
    transition: background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard), border-color var(--dur-fast) var(--ease-standard);
  }
  .btn--ghost { border: 1px solid var(--border-2); color: var(--fg-1); background: transparent; }
  .btn--ghost:hover { border-color: var(--ink-text-900); text-decoration: none; }

  /* ── Cover ── */
  .cover { padding: clamp(48px, 8vw, 96px) 0 clamp(36px, 5vw, 60px); border-bottom: 1px solid var(--border-1); }
  .cover__title {
    font-size: clamp(48px, 8vw, 96px);
    font-weight: 400;
    line-height: 0.98;
    letter-spacing: -0.035em;
    margin: 14px 0 18px;
  }
  .cover__lede { margin: 0 0 18px; }
  .cover__naming { font-size: 13.5px; color: var(--fg-3); margin: 0; max-width: 64ch; }
  .cover__naming strong { color: var(--fg-2); font-weight: 600; }

  /* ── Shared section chrome ── */
  .ch { padding: clamp(48px, 7vw, 84px) 0; border-bottom: 1px solid var(--border-1); }
  .ch__inner { max-width: 760px; }
  .ch h2 {
    font-size: clamp(28px, 4.4vw, 46px);
    font-weight: 500;
    line-height: 1.06;
    letter-spacing: -0.02em;
    margin: 12px 0 22px;
  }
  .ch .eyebrow { display: block; }

  /* ── Four channels ── */
  .channels {
    display: grid; grid-template-columns: repeat(2, 1fr); gap: 18px;
    list-style: none; margin: 30px 0 0; padding: 0;
  }
  @media (max-width: 900px) { .channels { grid-template-columns: 1fr; } }
  .channel {
    display: grid; align-content: start; gap: 9px;
    padding: 24px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
    transition: border-color var(--dur-base) var(--ease-summon), box-shadow var(--dur-base) var(--ease-summon);
  }
  .channel:hover { border-color: var(--border-2); box-shadow: var(--shadow-sm); }
  .channel__eyebrow { color: var(--ember-700); }
  .channel__title {
    font-family: var(--font-display); font-size: 23px; font-weight: 500;
    letter-spacing: -0.015em; line-height: 1.12; margin: 0; color: var(--fg-1);
  }
  .channel__body { font-size: 14px; line-height: 1.6; color: var(--fg-2); margin: 0; }
  .channel__note {
    font-size: 12.5px; line-height: 1.55; color: var(--fg-3); font-style: italic;
    margin: 0; max-width: none;
  }
  .channel__cta {
    font-family: var(--font-sans); font-size: 13.5px; font-weight: 600;
    color: var(--ember-700); width: fit-content; margin-top: 2px;
    overflow-wrap: anywhere;
  }

  /* ── How intake is processed ── */
  .ch--how .voice { margin: 0 0 20px; }

  /* ── Who runs this ── */
  .keeper {
    margin-top: 28px;
    padding: 18px 22px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-left: 2px solid var(--ember-700);
    border-radius: var(--radius-md);
  }
  .keeper__eyebrow { display: block; color: var(--ember-700); margin: 0 0 6px; }
  .keeper__body { font-size: 14px; line-height: 1.6; color: var(--fg-2); margin: 0; max-width: 64ch; }
  .keeper__body a { color: var(--ember-700); font-weight: 600; }

  /* ── Close ── */
  .ch--close { border-bottom: none; padding-bottom: clamp(72px, 10vw, 120px); }
  .close__cta {
    display: grid; gap: 6px;
    padding: 26px 28px;
    background: var(--bg-2);
    border: 1px solid var(--border-2);
    border-radius: var(--radius-lg);
    text-decoration: none;
    color: inherit;
    transition: border-color var(--dur-fast) var(--ease-standard), box-shadow var(--dur-fast) var(--ease-standard);
  }
  .close__cta:hover { border-color: var(--ink-text-900); box-shadow: var(--shadow-md); text-decoration: none; }
  .close__k { display: block; }
  .close__cta strong { font-family: var(--font-display); font-size: clamp(22px, 3vw, 32px); font-weight: 500; letter-spacing: -0.015em; line-height: 1.12; color: var(--fg-1); }
  .close__sub { font-size: 13.5px; color: var(--fg-2); }
</style>
