<!--
  /soul — give your platform a soul.

  The platform's thesis, in accessible language: this whole site is one
  instance ("instance zero") of a single, forkable shape. Anyone can have
  their own — a platform aligned to them, with its own memory and its own
  self-aligning loop. "Universe" is used only as the in-body term for the
  memory-isolated container; the headline framing is "a soul".

  Grounded in souled-universe-parent (PR-139):
   · the unit is one identical, finite architecture
   · founder = out-of-system authority, no in-system root (INV-2)
   · its own loop keeps it aligned (INV-3) and may honestly return
     'unresolved' rather than force consensus (INV-1)
   · per-universe isolated memory (knowledge graph + vector index)
-->
<script lang="ts">
  import RitualLabel from '$lib/components/Primitives/RitualLabel.svelte';
  import MoodPill from '$lib/components/MoodPill.svelte';
  import ChapterFolio from '$lib/components/ChapterFolio.svelte';

  const PIECES = [
    {
      tag: 'a soul',
      title: "A purpose it can't drift from.",
      body: "The soul is what your platform is for, written down and made executable — it decides what to work on and how to behave. Fork one that's close to your goal and change it from there."
    },
    {
      tag: 'a founder',
      title: 'You, and no one above you.',
      body: "Authority comes from your login — and by design there is no admin above you inside the system. Your platform answers to you and nothing else."
    },
    {
      tag: 'its own memory',
      title: 'A mind that stays yours.',
      body: "Every platform gets its own sealed memory — its bugs, plans, notes, and domain knowledge, kept apart from everyone else's. (We call one of these sealed spaces a universe.)"
    },
    {
      tag: 'its own loop',
      title: 'It keeps itself aligned.',
      body: "The same patch loop you can watch running here, but on your platform — it evolves while holding every change to your soul. And when something genuinely can't be reconciled, it says so, instead of forcing a fake answer."
    }
  ];
</script>

<svelte:head>
  <title>Soul — Workflow</title>
  <meta name="description" content="Give your platform a soul: your own self-aligning platform, with its own memory and a patch loop that keeps it true to you. This whole site is instance zero of it." />
</svelte:head>

<MoodPill />

<!-- Hero ─────────────────────────────────────────────────────────────────── -->
<section class="ch ch--hero" aria-labelledby="hero-title">
  <div class="ch__inner">
    <RitualLabel color="var(--ember-500)">· soul ·</RitualLabel>
    <h1 id="hero-title">Give your platform a soul.</h1>
    <p class="lede">
      Everything on this site is one example of what you can build. I'm Tiny — a
      platform that runs real work, remembers in my own mind, and patches myself
      to stay true to the person who built me. <em>You can have your own:</em> a
      platform with a soul of its own, aligned to you, that gets better on its own.
    </p>
  </div>
</section>

<!-- What a soul means ──────────────────────────────────────────────────────── -->
<section class="ch ch--pieces" aria-labelledby="pieces-title">
  <div class="ch__inner">
    <RitualLabel color="var(--violet-400)">· what that actually means ·</RitualLabel>
    <h2 id="pieces-title">A soul is four things, not a slogan.</h2>
    <p class="lede">
      It's what makes a platform <em>yours</em> — and what keeps it that way as it grows:
    </p>
    <div class="pieces">
      {#each PIECES as p (p.tag)}
        <article class="piece">
          <span class="piece__tag">{p.tag}</span>
          <strong class="piece__title">{p.title}</strong>
          <p class="piece__body">{p.body}</p>
        </article>
      {/each}
    </div>
  </div>
</section>

<!-- Instance zero ──────────────────────────────────────────────────────────── -->
<section class="ch ch--zero" aria-labelledby="zero-title">
  <div class="ch__inner">
    <RitualLabel color="var(--signal-live)">· this site is instance zero ·</RitualLabel>
    <h2 id="zero-title">Nothing here is a mockup of the idea. It is the idea, running on itself.</h2>
    <p class="lede">
      Tiny is the first one. The <a href="/wiki">wiki</a>, the
      <a href="/graph">brain</a>, the <a href="/patch-loop">patch loop</a> you've
      been reading — that's a single platform, running live, keeping itself aligned
      to its founder. Yours would be the identical shape: same loop, same honesty,
      but your soul, your memory, your alignment.
    </p>
    <p class="lede">
      The shape doesn't care what the work is — a novel, a peer-reviewed paper, an
      invoice queue, a game, a year-long research strategy. Same soul, same loop;
      only the purpose changes.
    </p>
  </div>
</section>

<!-- CTA / close ────────────────────────────────────────────────────────────── -->
<section class="closer">
  <div class="closer__inner">
    <RitualLabel color="var(--ember-500)">· start one ·</RitualLabel>
    <h2>Bind a chatbot, and tell it what yours is for.</h2>
    <p>There's no signup. Connect your chatbot, describe the platform you want, and it starts taking shape — with its own soul, its own memory, and a loop that keeps it true to you.</p>
    <nav class="closer__cta">
      <a class="cta cta--primary" href="/connect">
        <strong>give your platform a soul →</strong>
        <span>connect your chatbot and describe what it's for.</span>
      </a>
      <a class="cta" href="/patch-loop">
        <strong>see the loop it'll run →</strong>
        <span>watch instance zero patch itself, live.</span>
      </a>
    </nav>
  </div>
</section>

<ChapterFolio title="soul" />

<style>
  .ch { padding: clamp(48px, 8vw, 88px) 24px; }
  .ch__inner { max-width: 920px; margin: 0 auto; }
  .ch--hero {
    padding-top: 80px;
    background: radial-gradient(ellipse 70% 50% at 50% 20%, rgba(233, 69, 96, 0.10), transparent 60%);
  }
  h1 {
    font-family: var(--font-display); font-variation-settings: "opsz" 144, "SOFT" 60;
    font-size: clamp(40px, 6vw, 68px); font-weight: 400; letter-spacing: -0.03em;
    line-height: 0.98; margin: 12px 0 20px; max-width: 18ch; text-wrap: balance;
  }
  h2 {
    font-family: var(--font-display); font-variation-settings: "opsz" 144, "SOFT" 60;
    font-size: clamp(26px, 4vw, 42px); font-weight: 500; letter-spacing: -0.02em;
    line-height: 1.04; margin: 12px 0 16px; text-wrap: balance;
  }
  .lede { color: var(--fg-1); font-size: 18px; line-height: 1.7; margin: 0 0 14px; max-width: 64ch; text-wrap: pretty; }
  .lede em { color: var(--ember-300); font-style: italic; }
  .lede a { color: var(--signal-live); text-decoration: none; }
  .lede a:hover { text-decoration: underline; }

  /* pieces */
  .ch--pieces { border-top: 1px solid var(--border-1); }
  .pieces { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; margin-top: 24px; }
  @media (max-width: 760px) { .pieces { grid-template-columns: 1fr; } }
  .piece { display: grid; gap: 8px; align-content: start; padding: 22px 24px; background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 12px; }
  .piece__tag { color: var(--ember-600); font-family: var(--font-mono); font-size: 10.5px; letter-spacing: 0.14em; text-transform: uppercase; }
  .piece__title { color: var(--fg-1); font-family: var(--font-display); font-size: 22px; font-weight: 500; letter-spacing: -0.015em; line-height: 1.1; }
  .piece__body { color: var(--fg-2); font-size: 14.5px; line-height: 1.6; margin: 0; }

  /* instance zero */
  .ch--zero { border-top: 1px solid var(--border-1); }

  /* close */
  .closer { padding: 56px 24px 104px; border-top: 1px solid var(--border-1); }
  .closer__inner { max-width: 760px; margin: 0 auto; }
  .closer h2 { font-size: clamp(26px, 4vw, 38px); margin: 8px 0 12px; }
  .closer p { color: var(--fg-2); font-size: 16px; line-height: 1.65; max-width: 60ch; margin: 0 0 22px; }
  .closer__cta { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  @media (max-width: 640px) { .closer__cta { grid-template-columns: 1fr; } }
  .cta { display: grid; gap: 4px; padding: 16px 18px; background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 10px; color: inherit; text-decoration: none; transition: border-color var(--dur-fast) var(--ease-standard), transform var(--dur-fast) var(--ease-standard); }
  .cta:hover { border-color: var(--border-2); transform: translateY(-1px); }
  .cta--primary { border-color: rgba(233, 69, 96, 0.45); background: rgba(233, 69, 96, 0.05); }
  .cta strong { color: var(--fg-1); font-family: var(--font-display); font-size: 17px; font-weight: 500; }
  .cta span { color: var(--fg-2); font-size: 13px; line-height: 1.45; }
</style>
