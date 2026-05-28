<!--
  /loop — "The loop." Leads with the three concrete entry paths and uses a
  snapshot-backed patch-loop playground to show how live work moves.
-->
<script lang="ts">
  import baked from "$lib/content/mcp-snapshot.json";
  import type { Snapshot } from "$lib/mcp/types";
  import LoopLiveFeed from "$lib/components/LoopLiveFeed.svelte";
  import RitualLabel from "$lib/components/Primitives/RitualLabel.svelte";
  import { compactNumber, createPulse, shortHash } from "$lib/live/project";

  type StageId =
    | "intake"
    | "investigation"
    | "gate"
    | "coding"
    | "release"
    | "observe";

  const snapshot = baked as unknown as Snapshot;
  const pulse = createPulse();
  const repoUrl =
    pulse.repo.repo.remote_url?.replace(/\.git$/, "") ||
    "https://github.com/Jonnyton/Workflow";

  const STAGES: Array<{
    id: StageId;
    label: string;
  }> = [
    {
      id: "intake",
      label: "Intake",
    },
    {
      id: "investigation",
      label: "Investigation",
    },
    {
      id: "gate",
      label: "Gate",
    },
    {
      id: "coding",
      label: "Coding",
    },
    {
      id: "release",
      label: "Release",
    },
    {
      id: "observe",
      label: "Watch",
    },
  ];

  let selectedStageId = $state<StageId>("intake");
</script>

<svelte:head>
  <title>The loop - Workflow</title>
  <meta
    name="description"
    content="Watch live Workflow wiki bugs, work targets, branches, and gates move through the public contribution loop."
  />
</svelte:head>

<section class="join-loop join-loop--hero" aria-labelledby="join-loop-title">
  <div class="container">
    <div class="join-copy">
      <RitualLabel color="var(--signal-live)">· Live loop replay ·</RitualLabel>
      <h1 id="join-loop-title">The loop is a decision trail, not a feed.</h1>
      <p class="lead">
        Start with the latest durable MCP or GitHub evidence, click into the
        stage that made the call, then choose how you want to join the next
        pass.
      </p>

      <div class="entry-steps" aria-label="Loop action choices">
        <a
          class="entry-step"
          href={`${repoUrl}/blob/main/CONTRIBUTING.md`}
          target="_blank"
          rel="noreferrer"
        >
          <span class="entry-step__number">1</span>
          <strong>Contribute through GitHub</strong>
          <p>Open the repo path.</p>
          <small
            >{compactNumber(pulse.mcp.wiki.bugs.length)} wiki bugs · {compactNumber(
              pulse.branchCount,
            )} branches · head {shortHash(pulse.repo.repo.head)}</small
          >
        </a>
        <a class="entry-step" href="/connect">
          <span class="entry-step__number">2</span>
          <strong>Connect your MCP</strong>
          <p>Use it from your chatbot.</p>
          <small
            >{pulse.mcp.source} · {compactNumber(pulse.mcp.goals.length)} work targets
            · {compactNumber(pulse.mcp.wiki.bugs.length)} bugs</small
          >
        </a>
        <a class="entry-step" href="/host">
          <span class="entry-step__number">3</span>
          <strong>Host a daemon</strong>
          <p>Add capacity to the loop.</p>
          <small
            >{compactNumber(pulse.mcp.universes.length)} universes · {compactNumber(
              pulse.repo.workflow_branches.length,
            )} workflow branches</small
          >
        </a>
      </div>
    </div>
  </div>
</section>

<section id="loop-playground" class="playground">
  <div class="container">
    <div class="playground__header">
      <div>
        <RitualLabel color="var(--violet-400)"
          >· Patch loop replay ·</RitualLabel
        >
        <h2>Click through the latest evidence</h2>
        <p>
          The 1-6 route is the scaffold. The story is the selected run or
          monitor signal: source, stage, verdict, and the raw JSON behind it.
        </p>
      </div>
      <div class="snapshot-meter" aria-label="MCP snapshot counts">
        <span><strong>{snapshot.stats.wiki_promoted}</strong> wiki pages</span>
        <span><strong>{snapshot.stats.goals}</strong> work targets</span>
        <span
          ><strong>{snapshot.stats.edges ?? snapshot.edges?.length ?? 0}</strong
          > edges</span
        >
      </div>
    </div>

    <LoopLiveFeed
      stages={STAGES}
      {selectedStageId}
      onSelectStage={(stage) => (selectedStageId = stage)}
    />
  </div>
</section>

<style>
  .playground,
  .join-loop {
    padding-block: 56px;
    border-top: 1px solid var(--border-1);
  }
  .join-loop--hero {
    padding-top: 72px;
    border-top: none;
  }
  h1 {
    font-family: var(--font-display);
    font-size: clamp(42px, 7vw, 68px);
    font-weight: 400;
    letter-spacing: 0;
    margin: 8px 0 14px;
    line-height: 0.98;
    text-wrap: balance;
  }
  h2 {
    font-family: var(--font-display);
    font-size: clamp(28px, 5vw, 40px);
    font-weight: 500;
    letter-spacing: 0;
    margin: 8px 0 14px;
    line-height: 1.05;
  }
  .lead {
    font-size: 17px;
    color: var(--fg-2);
    line-height: 1.65;
    margin: 0 0 14px;
    max-width: 64ch;
  }

  .join-loop {
    background: var(--bg-0);
  }
  .join-copy {
    min-width: 0;
  }
  .entry-steps {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
    margin-top: 24px;
  }
  .entry-step {
    display: grid;
    gap: 8px;
    grid-template-rows: auto auto 1fr auto;
    min-height: 188px;
    min-width: 0;
    padding: 18px;
    color: inherit;
    text-decoration: none;
    border: 1px solid var(--border-1);
    border-radius: 8px;
    background: var(--bg-inset);
    transition:
      border-color var(--dur-base) var(--ease-summon),
      background var(--dur-base) var(--ease-summon),
      transform var(--dur-base) var(--ease-summon);
  }
  .entry-step:hover {
    border-color: rgba(109, 211, 166, 0.42);
    background: rgba(109, 211, 166, 0.045);
    transform: translateY(-1px);
  }
  .entry-step__number,
  .entry-step small {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10.5px;
    line-height: 1.45;
    text-transform: uppercase;
  }
  .entry-step__number {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    border: 1px solid rgba(109, 211, 166, 0.32);
    border-radius: 50%;
    background: rgba(109, 211, 166, 0.08);
    color: var(--signal-live);
  }
  .entry-step strong {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: clamp(24px, 3vw, 34px);
    font-weight: 500;
    line-height: 1.08;
    overflow-wrap: anywhere;
  }
  .entry-step p {
    color: var(--fg-2);
    font-size: 15px;
    line-height: 1.45;
    margin: 0;
  }

  .playground {
    background:
      linear-gradient(
        180deg,
        rgba(255, 255, 255, 0.025),
        rgba(255, 255, 255, 0)
      ),
      var(--bg-1);
  }
  .playground__header {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 24px;
    align-items: end;
    margin-bottom: 18px;
  }
  .playground__header p {
    color: var(--fg-2);
    font-size: 15px;
    line-height: 1.65;
    max-width: 70ch;
    margin: 0;
  }
  .snapshot-meter {
    display: grid;
    grid-template-columns: repeat(3, minmax(86px, 1fr));
    border: 1px solid var(--border-1);
    background: var(--bg-inset);
    border-radius: 8px;
    overflow: hidden;
  }
  .snapshot-meter span {
    display: grid;
    gap: 2px;
    padding: 10px 12px;
    border-left: 1px solid var(--border-1);
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10.5px;
    text-transform: uppercase;
  }
  .snapshot-meter span:first-child {
    border-left: 0;
  }
  .snapshot-meter strong {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: 24px;
    font-weight: 500;
    line-height: 1;
    text-transform: none;
  }
  @media (max-width: 1100px) {
    .playground__header {
      grid-template-columns: 1fr;
      align-items: start;
    }
  }

  @media (max-width: 700px) {
    .playground,
    .join-loop {
      padding-block: 40px;
    }
    .join-loop--hero {
      padding-top: 48px;
    }
    .entry-steps,
    .snapshot-meter {
      grid-template-columns: 1fr;
    }
    .entry-step {
      min-height: 188px;
      padding: 18px;
    }
  }
</style>
