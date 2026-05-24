<script lang="ts">
  import { onMount } from "svelte";
  import RitualLabel from "$lib/components/Primitives/RitualLabel.svelte";
  import {
    fetchPatchLoopFeed,
    type LoopPatchEvent,
    type LoopPatchRun,
    type LoopStageId,
    type PatchLoopFeed,
    type PatchLoopFeedSource,
  } from "$lib/mcp/live";
  import { relativeStamp } from "$lib/live/project";

  type Stage = {
    id: LoopStageId;
    label: string;
  };

  const STAGE_DETAIL: Record<
    LoopStageId,
    { action: string; description: string; empty: string }
  > = {
    intake: {
      action: "File or classify",
      description:
        "User reports, wiki bugs, and daemon requests enter the loop here before they become scoped patch work.",
      empty: "No intake signal is visible in the current feed.",
    },
    investigation: {
      action: "Turn bug into packet",
      description:
        "The loop turns raw friction into a reproducible patch packet with the context a writer needs.",
      empty: "No investigation packet is visible in the current feed.",
    },
    gate: {
      action: "Scope and evidence check",
      description:
        "Evidence gates decide whether the request is ready, blocked, too broad, or needs a different route.",
      empty: "No gate decision is visible in the current feed.",
    },
    coding: {
      action: "Agent team builds",
      description:
        "Writer capacity turns accepted packets into branches, diffs, checks, and review handoffs.",
      empty: "No coding signal is visible in the current feed.",
    },
    release: {
      action: "Ship with rollback path",
      description:
        "Release signals show deploys, PR handoffs, branch landing, and rollback-aware shipping.",
      empty: "No release signal is visible in the current feed.",
    },
    observe: {
      action: "Ratify or loop back",
      description:
        "Watch signals show canaries, user-visible checks, monitoring, and whether work loops back.",
      empty: "No watch signal is visible in the current feed.",
    },
  };

  let {
    stages,
    selectedStageId = "intake",
    onSelectStage = () => {},
  }: {
    stages: Stage[];
    selectedStageId?: LoopStageId;
    onSelectStage?: (stage: LoopStageId) => void;
  } = $props();

  let feed = $state<PatchLoopFeed | null>(null);
  let activeSource = $state<PatchLoopFeedSource>("mcp");
  let loadingSource = $state<PatchLoopFeedSource | null>(null);
  let latestError = $state("");
  let selectedRunId = $state("");

  const activeRun = $derived.by((): LoopPatchRun | null => {
    if (!feed?.runs.length) return null;
    if (selectedRunId) {
      const picked = feed.runs.find((run) => run.run_id === selectedRunId);
      if (picked) return picked;
    }
    const selected = feed.runs.find((run) => run.run_id === feed?.activeRunId);
    if (selected) return selected;
    return feed.runs.find((run) => !isTerminalRunStatus(run.status)) ?? null;
  });

  const headline = $derived.by(() => {
    if (activeRun) return activeRun.name || activeRun.run_id;
    if (feed?.events.length) {
      const sourceName = feed.source.toLowerCase().includes("github")
        ? "GitHub loop monitor"
        : "MCP loop signals";
      return `${sourceName}: ${(feed.overall ?? "active").toUpperCase()}`;
    }
    return "No active patch run is visible right now";
  });

  const subhead = $derived.by(() => {
    if (activeRun)
      return `${activeRun.status} · ${relativeStamp(activeRun.started_at)}`;
    if (feed?.events.length)
      return `${feed.events.length} live stage signal${feed.events.length === 1 ? "" : "s"} · ${relativeStamp(feed.fetchedAt)}`;
    return feed?.live
      ? "showing queue and monitor evidence"
      : "loading durable loop evidence";
  });

  const recentEvents = $derived.by((): LoopPatchEvent[] => {
    return [...(feed?.events ?? [])].slice(-8).reverse();
  });

  const selectableRuns = $derived(feed?.runs ?? []);

  const selectedStage = $derived.by((): Stage => {
    return stages.find((stage) => stage.id === selectedStageId) ?? stages[0];
  });

  const selectedStageNumber = $derived.by(() => {
    return Math.max(
      1,
      stages.findIndex((stage) => stage.id === selectedStageId) + 1,
    );
  });

  const selectedStageEvents = $derived.by((): LoopPatchEvent[] => {
    return eventsFor(selectedStageId);
  });

  const selectedStageRecentEvents = $derived.by((): LoopPatchEvent[] => {
    return [...selectedStageEvents].slice(-8).reverse();
  });

  const selectedStageLatest = $derived.by((): LoopPatchEvent | null => {
    return latestFor(selectedStageId);
  });

  const decisionSignal = $derived(
    selectedStageLatest ?? recentEvents[0] ?? null,
  );

  const loopVoiceQuote = $derived.by(() => {
    const text =
      selectedStageLatest?.detail ||
      activeRun?.error ||
      activeRun?.suggested_action ||
      recentEvents[0]?.detail ||
      "";
    return compactQuote(text);
  });

  const rawStageJson = $derived.by(() =>
    JSON.stringify(
      {
        source: feed?.source ?? activeSource,
        fetchedAt: feed?.fetchedAt,
        selectedStage: selectedStageId,
        activeRun,
        latestSignal: selectedStageLatest,
        stageEvents: selectedStageRecentEvents,
      },
      null,
      2,
    ),
  );

  const relatedStageEvents = $derived.by((): LoopPatchEvent[] => {
    return recentEvents
      .filter((event) => event.stage !== selectedStageId)
      .slice(0, 4);
  });

  $effect(() => {
    if (!feed?.runs.length) {
      selectedRunId = "";
      return;
    }
    if (
      !selectedRunId ||
      !feed.runs.some((run) => run.run_id === selectedRunId)
    ) {
      selectedRunId =
        feed.activeRunId ??
        feed.runs.find((run) => !isTerminalRunStatus(run.status))?.run_id ??
        feed.runs[0]?.run_id ??
        "";
    }
  });

  async function refresh(source: PatchLoopFeedSource = activeSource) {
    activeSource = source;
    loadingSource = source;
    latestError = "";
    try {
      const nextFeed = await fetchPatchLoopFeed(12, source);
      if (source === "mcp" && !nextFeed.live) {
        await showGitHubFallback(nextFeed);
        return;
      }
      feed = nextFeed;
      if (!feed.live && feed.warnings.length) {
        latestError = feed.warnings[feed.warnings.length - 1];
      }
    } catch (error) {
      if (source === "mcp") {
        await showGitHubFallback(null, error);
        return;
      }
      latestError = errorMessage(error);
    } finally {
      loadingSource = null;
    }
  }

  async function showGitHubFallback(
    mcpFeed: PatchLoopFeed | null,
    mcpError?: unknown,
  ) {
    const mcpMessage =
      mcpFeed?.warnings[mcpFeed.warnings.length - 1] ??
      errorMessage(mcpError, "MCP loop feed unavailable");
    try {
      const fallback = await fetchPatchLoopFeed(12, "github");
      activeSource = "github";
      feed = fallback;
      latestError = fallback.live
        ? `${mcpMessage}; showing GitHub monitor instead.`
        : (fallback.warnings[fallback.warnings.length - 1] ??
          `${mcpMessage}; GitHub monitor has no visible events.`);
    } catch (fallbackError) {
      feed = mcpFeed;
      latestError = `${mcpMessage}; GitHub monitor unavailable: ${errorMessage(fallbackError)}`;
    }
  }

  function errorMessage(
    error: unknown,
    fallback = "Loop feed unavailable",
  ): string {
    return error instanceof Error ? error.message : fallback;
  }

  onMount(() => {
    void refresh("mcp");
    const timer = window.setInterval(() => void refresh(activeSource), 30000);
    return () => window.clearInterval(timer);
  });

  function eventsFor(stage: LoopStageId): LoopPatchEvent[] {
    return (feed?.events ?? []).filter((event) => event.stage === stage);
  }

  function latestFor(stage: LoopStageId): LoopPatchEvent | null {
    const matches = eventsFor(stage);
    return matches[matches.length - 1] ?? null;
  }

  type StageVisualStatus = "waiting" | "running" | "done" | "failed";

  function stageVisualStatusFromStatus(
    value: string,
    fallback: StageVisualStatus = "waiting",
  ): StageVisualStatus {
    const status = value.trim().toLowerCase();
    if (!status) return fallback;
    if (
      status === "green" ||
      status === "passed" ||
      status === "pass" ||
      status.includes("complete") ||
      status.includes("success") ||
      status.includes("succeed") ||
      status.includes("done") ||
      status.includes("accept") ||
      status.includes("merged")
    )
      return "done";
    if (
      status === "red" ||
      status.includes("fail") ||
      status.includes("error") ||
      status.includes("revert") ||
      status.includes("block") ||
      status.includes("interrupt") ||
      status.includes("cancel") ||
      status.includes("abort") ||
      status.includes("timeout") ||
      status.includes("timed_out")
    )
      return "failed";
    if (
      status === "yellow" ||
      status.includes("pending") ||
      status.includes("queued") ||
      status.includes("waiting") ||
      status.includes("handoff") ||
      status.includes("attempted") ||
      status.includes("deferred") ||
      status.includes("parked") ||
      status.includes("idle") ||
      status.includes("unknown")
    )
      return "waiting";
    if (
      status.includes("running") ||
      status.includes("active") ||
      status.includes("progress") ||
      status.includes("started")
    )
      return "running";
    return fallback;
  }

  function stageStatus(stage: LoopStageId): StageVisualStatus {
    if (
      activeRun?.current_stage === stage &&
      isTerminalRunStatus(activeRun.status)
    )
      return stageVisualStatusFromStatus(activeRun.status, "failed");
    const latest = latestFor(stage);
    if (!latest)
      return activeRun?.current_stage === stage
        ? stageVisualStatusFromStatus(activeRun.status, "running")
        : "waiting";
    return stageVisualStatusFromStatus(latest.status);
  }

  function statusLabel(stage: LoopStageId): string {
    const count = eventsFor(stage).length;
    if (count) return `${count} event${count === 1 ? "" : "s"}`;
    if (activeRun?.current_stage === stage) return "active run";
    if (feed?.live) return "no event in this run";
    return "waiting for feed";
  }

  function stageTimeLabel(stage: LoopStageId): string {
    const latest = latestFor(stage);
    if (!latest) return statusLabel(stage);
    return `Last ran ${relativeStamp(latest.at)}`;
  }

  function stageEventSummary(stage: LoopStageId): string {
    const latest = latestFor(stage);
    if (!latest)
      return activeRun?.current_stage === stage
        ? "Selected run is parked here"
        : STAGE_DETAIL[stage].description;
    const eventName =
      latest.title || latest.node_id || sourceLabel(latest.source);
    return `${latest.status} - ${eventName}`;
  }

  function stageCueLabel(stage: LoopStageId): string {
    const latest = latestFor(stage);
    if (!latest)
      return activeRun?.current_stage === stage
        ? "Open active stage"
        : "Open stage detail";
    return "See recent events";
  }

  function signalLabel(count: number): string {
    return `${count} live signal${count === 1 ? "" : "s"}`;
  }

  function sourceHref(source?: string): string {
    const value = source?.trim() ?? "";
    return /^https?:\/\//i.test(value) ? value : "";
  }

  function sourceLabel(source?: string): string {
    const value = source?.trim() ?? "";
    if (!value) return "Live feed";
    try {
      const url = new URL(value);
      return url.hostname.replace(/^www\./, "");
    } catch {
      return value;
    }
  }

  function isTerminalRunStatus(status: string): boolean {
    return [
      "completed",
      "succeeded",
      "success",
      "failed",
      "interrupted",
      "cancelled",
      "canceled",
      "aborted",
      "timeout",
      "timed_out",
    ].includes(status.toLowerCase());
  }

  function compactQuote(value: string): string {
    const text = value.replace(/\s+/g, " ").trim();
    if (!text || text === "{}" || text === "[]") return "";
    return text.length > 360 ? `${text.slice(0, 357).trimEnd()}...` : text;
  }
</script>

<section class="live-loop" aria-labelledby="live-loop-title">
  <div class="live-loop__head">
    <div>
      <RitualLabel color="var(--signal-live)"
        >· The loop just decided this ·</RitualLabel
      >
      <h2 id="live-loop-title">Replay the latest durable loop evidence.</h2>
      <p>
        The page does not depend on a fresh event firing while you watch. It
        replays the latest MCP run or GitHub loop monitor signal, then lets you
        click into the stage evidence and raw source data.
      </p>
    </div>
    <div class="live-loop__actions">
      <button
        class="refresh"
        type="button"
        disabled={loadingSource !== null}
        aria-pressed={activeSource === "mcp"}
        aria-busy={loadingSource === "mcp"}
        onclick={() => refresh("mcp")}
      >
        Refresh MCP
      </button>
      <button
        class="refresh"
        type="button"
        disabled={loadingSource !== null}
        aria-pressed={activeSource === "github"}
        aria-busy={loadingSource === "github"}
        onclick={() => refresh("github")}
      >
        Refresh GitHub
      </button>
      <span
        >{loadingSource
          ? `Refreshing ${loadingSource === "mcp" ? "MCP" : "GitHub"} feed`
          : (feed?.source ?? "MCP loop feed")}</span
      >
    </div>
  </div>

  <div class="live-loop__body">
    <div class="loop-overview">
      <div class="run-card">
        <span>{activeRun ? "Selected patch run" : "Durable loop monitor"}</span>
        {#if activeRun}
          <strong>{headline}</strong>
          <p><code>{activeRun.run_id}</code> · {subhead}</p>
        {:else if feed?.events.length}
          <strong>{headline}</strong>
          <p><code>{feed.source}</code> · {subhead}</p>
        {:else}
          <strong>{headline}</strong>
          <p><code>{feed?.branchDefId ?? "fd5c66b1d87d"}</code> · {subhead}</p>
        {/if}
        {#if activeRun?.error}
          <p class="feed-error">{activeRun.error}</p>
        {/if}
        {#if activeRun?.suggested_action}
          <p class="feed-hint">{activeRun.suggested_action}</p>
        {/if}
        {#if latestError}
          <p class="feed-error">{latestError}</p>
        {/if}
        {#if loopVoiceQuote}
          <blockquote class="loop-voice">
            <p>"{loopVoiceQuote}"</p>
            <footer>
              {selectedStageLatest
                ? `${selectedStageLatest.title} · ${sourceLabel(selectedStageLatest.source)}`
                : activeRun
                  ? `Run ${activeRun.run_id}`
                  : sourceLabel(recentEvents[0]?.source)}
            </footer>
          </blockquote>
        {/if}
        {#if selectableRuns.length > 1}
          <label class="run-picker">
            <span>Walk a different run</span>
            <select bind:value={selectedRunId}>
              {#each selectableRuns as run}
                <option value={run.run_id}
                  >{run.name || run.run_id} · {run.status}</option
                >
              {/each}
            </select>
          </label>
        {/if}
      </div>

      <div class="live-rail" aria-label="Live loop stages">
        {#each stages as stage, index}
          {@const latest = latestFor(stage.id)}
          <button
            type="button"
            class={`live-stage live-stage--${stageStatus(stage.id)}`}
            class:selected={selectedStageId === stage.id}
            aria-pressed={selectedStageId === stage.id}
            title={latest?.detail ?? statusLabel(stage.id)}
            onclick={() => onSelectStage(stage.id)}
          >
            <span>{index + 1}. {stage.label}</span>
            <strong>{latest?.title ?? STAGE_DETAIL[stage.id].action}</strong>
            <p class="live-stage__event">{stageEventSummary(stage.id)}</p>
            <div class="live-stage__footer">
              <small>{stageTimeLabel(stage.id)}</small>
              <small class="live-stage__cue">{stageCueLabel(stage.id)}</small>
            </div>
          </button>
        {/each}
      </div>
    </div>

    <div class="stage-detail" aria-live="polite">
      <div class="stage-detail__head">
        <div>
          <span>Selected stage</span>
          <strong
            >Stage {selectedStageNumber} · {selectedStage?.label ??
              "Loop stage"}</strong
          >
          <p>{STAGE_DETAIL[selectedStageId].action}</p>
        </div>
        <div
          class="stage-detail__meta"
          aria-label="Selected stage live feed status"
        >
          <span>{signalLabel(selectedStageEvents.length)}</span>
          <span>{feed?.source ?? "MCP loop feed"}</span>
          <span
            >{feed
              ? `Fetched ${relativeStamp(feed.fetchedAt)}`
              : "Waiting for live feed"}</span
          >
        </div>
      </div>

      <div class="stage-detail__grid">
        <section
          class="stage-card stage-card--about"
          aria-label="Stage purpose"
        >
          <span>What this stage does</span>
          <p>{STAGE_DETAIL[selectedStageId].description}</p>
          <dl>
            <div>
              <dt>Stage state</dt>
              <dd>{stageStatus(selectedStageId)}</dd>
            </div>
            <div>
              <dt>Current source</dt>
              <dd>{feed?.source ?? activeSource.toUpperCase()}</dd>
            </div>
            {#if activeRun}
              <div>
                <dt>Run</dt>
                <dd>{activeRun.run_id}</dd>
              </div>
              <div>
                <dt>Run status</dt>
                <dd>{activeRun.status}</dd>
              </div>
            {/if}
          </dl>
        </section>

        <section
          class="stage-card stage-card--latest"
          aria-label="Latest stage signal"
        >
          <span>Latest live signal</span>
          {#if selectedStageLatest}
            {@const href = sourceHref(selectedStageLatest.source)}
            <strong>{selectedStageLatest.title}</strong>
            <p>{selectedStageLatest.detail}</p>
            <dl>
              <div>
                <dt>Status</dt>
                <dd>{selectedStageLatest.status}</dd>
              </div>
              <div>
                <dt>Seen</dt>
                <dd>{relativeStamp(selectedStageLatest.at)}</dd>
              </div>
              {#if selectedStageLatest.run_id}
                <div>
                  <dt>Run id</dt>
                  <dd>{selectedStageLatest.run_id}</dd>
                </div>
              {/if}
              {#if selectedStageLatest.node_id}
                <div>
                  <dt>Node</dt>
                  <dd>{selectedStageLatest.node_id}</dd>
                </div>
              {/if}
            </dl>
            {#if href}
              <a class="source-link" {href} target="_blank" rel="noreferrer"
                >Open {sourceLabel(selectedStageLatest.source)}</a
              >
            {:else}
              <small>{sourceLabel(selectedStageLatest.source)}</small>
            {/if}
          {:else}
            <p>
              {STAGE_DETAIL[selectedStageId].empty}
              {feed?.events.length
                ? `${signalLabel(feed.events.length)} are visible elsewhere in the loop.`
                : "No active run is visible; the monitor still shows durable source state."}
            </p>
            {#if recentEvents[0]}
              {@const href = sourceHref(recentEvents[0].source)}
              <div class="stage-card__fallback">
                <span>Most recent loop signal</span>
                <strong>{recentEvents[0].title}</strong>
                <p>{recentEvents[0].detail}</p>
                <small
                  >{recentEvents[0].stage} · {recentEvents[0].status} · {relativeStamp(
                    recentEvents[0].at,
                  )}</small
                >
                {#if href}
                  <a {href} target="_blank" rel="noreferrer">Open source</a>
                {/if}
              </div>
            {/if}
          {/if}
        </section>

        <section
          class="stage-card stage-card--events"
          aria-label="Selected stage event history"
        >
          <div class="stage-card__head">
            <span>Stage history</span>
            <strong>{selectedStageEvents.length}</strong>
          </div>
          {#if selectedStageRecentEvents.length}
            <ol>
              {#each selectedStageRecentEvents as event}
                {@const href = sourceHref(event.source)}
                <li>
                  <span>{event.status}</span>
                  <div>
                    <strong>{event.title}</strong>
                    <p>{event.detail}</p>
                    <small>
                      {relativeStamp(event.at)}
                      {#if event.node_id}
                        · {event.node_id}{/if}
                      {#if event.run_id}
                        · {event.run_id}{/if}
                    </small>
                    {#if href}
                      <a {href} target="_blank" rel="noreferrer">Open source</a>
                    {:else}
                      <small>{sourceLabel(event.source)}</small>
                    {/if}
                  </div>
                </li>
              {/each}
            </ol>
          {:else}
            <p class="empty">{STAGE_DETAIL[selectedStageId].empty}</p>
            {#if relatedStageEvents.length}
              <div class="related-signals">
                <span>Visible elsewhere in the loop</span>
                <ol>
                  {#each relatedStageEvents as event}
                    {@const href = sourceHref(event.source)}
                    <li>
                      <span>{event.stage}</span>
                      <div>
                        <strong>{event.title}</strong>
                        <p>{event.detail}</p>
                        <small>{event.status} · {relativeStamp(event.at)}</small
                        >
                        {#if href}
                          <a {href} target="_blank" rel="noreferrer"
                            >Open source</a
                          >
                        {/if}
                      </div>
                    </li>
                  {/each}
                </ol>
              </div>
            {/if}
          {/if}
        </section>
      </div>

      <div class="evidence-chain" aria-label="Evidence chain">
        <span>Evidence chain</span>
        <ol>
          <li>
            <strong>Source</strong><small
              >{feed?.source ?? activeSource.toUpperCase()}</small
            >
          </li>
          {#if activeRun}
            <li><strong>Run</strong><small>{activeRun.run_id}</small></li>
          {/if}
          <li>
            <strong>Stage</strong><small
              >{selectedStage?.label ?? selectedStageId}</small
            >
          </li>
          {#if decisionSignal}
            <li>
              <strong>Signal</strong><small>{decisionSignal.title}</small>
            </li>
            {@const href = sourceHref(decisionSignal.source)}
            {#if href}
              <li>
                <a {href} target="_blank" rel="noreferrer">Open source</a><small
                  >{sourceLabel(decisionSignal.source)}</small
                >
              </li>
            {:else}
              <li>
                <strong>Source readout</strong><small
                  >{sourceLabel(decisionSignal.source)}</small
                >
              </li>
            {/if}
          {/if}
        </ol>
      </div>

      <details class="json-disclosure">
        <summary>Selected-stage JSON</summary>
        <pre>{rawStageJson}</pre>
      </details>

      {#if recentEvents.length}
        <details class="all-events">
          <summary>All recent loop signals</summary>
          <ol>
            {#each recentEvents as event}
              {@const href = sourceHref(event.source)}
              <li>
                <span>{event.stage}</span>
                <div>
                  <strong>{event.title}</strong>
                  <p>{event.detail}</p>
                  <small>{event.status} · {relativeStamp(event.at)}</small>
                  {#if href}
                    <a {href} target="_blank" rel="noreferrer">Open source</a>
                  {/if}
                </div>
              </li>
            {/each}
          </ol>
        </details>
      {/if}
    </div>
  </div>

  {#if feed?.warnings.length}
    <details class="source-trail">
      <summary>Source trail</summary>
      <ul>
        {#each feed.warnings as warning}
          <li>{warning}</li>
        {/each}
      </ul>
    </details>
  {/if}
</section>

<style>
  .live-loop {
    padding: 22px;
    border: 1px solid rgba(109, 211, 166, 0.22);
    border-radius: 8px;
    background:
      linear-gradient(
        135deg,
        rgba(109, 211, 166, 0.055),
        rgba(138, 99, 206, 0.045)
      ),
      var(--bg-inset);
  }

  .live-loop__head {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 18px;
    align-items: start;
    margin-bottom: 18px;
  }

  .live-loop h2 {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: clamp(28px, 4vw, 42px);
    font-weight: 500;
    line-height: 1.04;
    letter-spacing: 0;
    margin: 8px 0 10px;
  }

  .live-loop p {
    color: var(--fg-2);
    font-size: 14.5px;
    line-height: 1.6;
    margin: 0;
    max-width: 72ch;
  }

  .live-loop__actions {
    display: grid;
    grid-template-columns: repeat(2, max-content);
    gap: 8px;
    justify-items: end;
  }

  .live-loop__actions span {
    grid-column: 1 / -1;
    text-align: right;
  }

  .live-loop__actions span,
  .run-card span,
  .run-picker span,
  .stage-detail__head span,
  .stage-detail__meta span,
  .evidence-chain > span,
  .stage-card > span,
  .stage-card__fallback > span,
  .stage-card__head span,
  .stage-card__head strong,
  .related-signals > span,
  .stage-card dt,
  .stage-card small,
  .json-disclosure summary,
  .all-events summary {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10.5px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .refresh {
    min-height: 36px;
    padding: 0 13px;
    border: 1px solid rgba(109, 211, 166, 0.34);
    border-radius: 6px;
    background: rgba(109, 211, 166, 0.08);
    color: var(--signal-live);
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 11px;
    text-transform: uppercase;
    transition:
      border-color var(--dur-base) var(--ease-summon),
      background var(--dur-base) var(--ease-summon);
  }

  .refresh:hover:not(:disabled) {
    border-color: rgba(109, 211, 166, 0.62);
    background: rgba(109, 211, 166, 0.12);
  }

  .refresh[aria-pressed="true"] {
    border-color: rgba(109, 211, 166, 0.72);
    background: rgba(109, 211, 166, 0.14);
  }

  .refresh:disabled {
    cursor: wait;
    opacity: 0.55;
  }

  .live-loop__body {
    display: grid;
    gap: 12px;
    min-width: 0;
  }

  .loop-overview {
    display: grid;
    grid-template-columns: minmax(210px, 0.34fr) minmax(0, 1fr);
    gap: 12px;
    align-items: start;
    min-width: 0;
  }

  .run-card,
  .stage-detail {
    border: 1px solid var(--border-1);
    border-radius: 8px;
    background: rgba(0, 0, 0, 0.16);
    min-width: 0;
  }

  .run-card {
    display: grid;
    align-content: start;
    gap: 9px;
    padding: 15px;
  }

  .run-card strong {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: 24px;
    font-weight: 500;
    line-height: 1.06;
    overflow-wrap: anywhere;
  }

  .run-card code {
    color: var(--violet-200);
    font-family: var(--font-mono);
    font-size: 12px;
    overflow-wrap: anywhere;
  }

  .feed-error {
    color: var(--ember-300) !important;
    font-family: var(--font-mono);
    font-size: 11px !important;
    overflow-wrap: anywhere;
  }

  .feed-hint {
    color: var(--fg-3) !important;
    font-family: var(--font-mono);
    font-size: 11px !important;
    overflow-wrap: anywhere;
  }

  .loop-voice {
    display: grid;
    gap: 8px;
    margin: 2px 0 0;
    padding: 12px;
    border-left: 3px solid rgba(109, 211, 166, 0.58);
    border-radius: 6px;
    background: rgba(109, 211, 166, 0.06);
  }

  .loop-voice p {
    color: var(--fg-1);
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1.5;
    overflow-wrap: anywhere;
  }

  .loop-voice footer {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10px;
    line-height: 1.4;
    text-transform: uppercase;
  }

  .run-picker {
    display: grid;
    gap: 6px;
    min-width: 0;
  }

  .run-picker select {
    width: 100%;
    min-height: 38px;
    border: 1px solid rgba(109, 211, 166, 0.26);
    border-radius: 6px;
    background: rgba(0, 0, 0, 0.18);
    color: var(--fg-1);
    font-family: var(--font-mono);
    font-size: 11px;
  }

  .live-rail {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 8px;
    align-content: start;
    align-items: start;
    min-width: 0;
  }

  .live-stage {
    position: relative;
    display: grid;
    grid-template-rows: auto auto auto auto 1fr;
    gap: 5px;
    min-height: 158px;
    height: 158px;
    min-width: 0;
    padding: 12px;
    border: 1px solid var(--border-1);
    border-radius: 8px;
    background: var(--bg-inset);
    color: var(--fg-2);
    cursor: pointer;
    overflow: hidden;
    text-align: left;
    transition:
      transform var(--dur-fast) var(--ease-standard),
      border-color var(--dur-fast) var(--ease-standard),
      background var(--dur-fast) var(--ease-standard);
  }

  .live-stage::before {
    content: "";
    width: 9px;
    height: 9px;
    border-radius: 999px;
    background: var(--fg-3);
    box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.03);
  }

  .live-stage:hover,
  .live-stage.selected {
    transform: translateY(-1px);
    border-color: rgba(204, 120, 92, 0.55);
    background: rgba(204, 120, 92, 0.065);
  }

  .live-stage.selected {
    border-color: rgba(109, 211, 166, 0.72);
    background: rgba(109, 211, 166, 0.09);
    box-shadow: inset 0 0 0 1px rgba(109, 211, 166, 0.18);
  }

  .live-stage--running::before {
    background: var(--violet-400);
    box-shadow: 0 0 12px rgba(138, 99, 206, 0.9);
    animation: live-pulse 1.6s ease-in-out infinite;
  }

  .live-stage--done::before {
    background: var(--signal-live);
    box-shadow: 0 0 10px rgba(109, 211, 166, 0.75);
  }

  .live-stage--failed::before {
    background: var(--ember-600);
    box-shadow: 0 0 10px rgba(233, 69, 96, 0.75);
  }

  .live-stage span {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10.5px;
    text-transform: uppercase;
  }

  .live-stage strong {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    color: var(--fg-1);
    font-size: 13.5px;
    line-height: 1.2;
    overflow: hidden;
    overflow-wrap: anywhere;
  }

  .live-stage__event {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    color: var(--fg-2) !important;
    font-family: var(--font-mono);
    font-size: 11px !important;
    line-height: 1.35 !important;
    overflow: hidden;
    overflow-wrap: anywhere;
  }

  .live-stage__footer {
    display: grid;
    gap: 3px;
    align-self: end;
    min-width: 0;
  }

  .live-stage__footer small {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 1;
    line-clamp: 1;
    color: var(--fg-3);
    font-size: 11.5px;
    line-height: 1.35;
    overflow: hidden;
    overflow-wrap: anywhere;
  }

  .live-stage__cue {
    color: var(--signal-live) !important;
    font-family: var(--font-mono);
    font-size: 10px !important;
    text-transform: uppercase;
  }

  .stage-detail {
    display: grid;
    overflow: hidden;
  }

  .stage-detail__head {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(220px, max-content);
    gap: 18px;
    align-items: start;
    padding: 16px;
    border-bottom: 1px solid rgba(109, 211, 166, 0.2);
    background: rgba(109, 211, 166, 0.045);
  }

  .stage-detail__head > div:first-child {
    display: grid;
    gap: 6px;
  }

  .stage-detail__head strong {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: clamp(24px, 3.4vw, 34px);
    font-weight: 500;
    line-height: 1.04;
    overflow-wrap: anywhere;
  }

  .stage-detail__head p {
    color: var(--signal-live);
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1.45;
    text-transform: uppercase;
  }

  .stage-detail__meta {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    justify-content: end;
  }

  .stage-detail__meta span {
    max-width: 230px;
    padding: 6px 8px;
    border: 1px solid rgba(109, 211, 166, 0.18);
    border-radius: 999px;
    background: rgba(0, 0, 0, 0.14);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .stage-detail__grid {
    display: grid;
    grid-template-columns: minmax(220px, 0.78fr) minmax(280px, 1fr) minmax(
        340px,
        1.4fr
      );
    align-items: start;
    min-width: 0;
  }

  .stage-card {
    display: grid;
    align-content: start;
    gap: 10px;
    min-width: 0;
    min-height: 0;
    padding: 16px;
    border-left: 1px solid var(--border-1);
  }

  .stage-card:first-child {
    border-left: 0;
  }

  .stage-card > p {
    color: var(--fg-2);
    font-size: 13.5px;
    line-height: 1.55;
    overflow-wrap: anywhere;
  }

  .stage-card > strong {
    color: var(--fg-1);
    font-size: 17px;
    line-height: 1.25;
    overflow-wrap: anywhere;
  }

  .stage-card dl {
    display: grid;
    gap: 8px;
    margin: 0;
  }

  .stage-card dl div {
    display: grid;
    grid-template-columns: 92px minmax(0, 1fr);
    gap: 10px;
  }

  .stage-card dt {
    font-size: 10px;
  }

  .stage-card dd {
    color: var(--fg-2);
    font-family: var(--font-mono);
    font-size: 11.5px;
    line-height: 1.35;
    margin: 0;
    overflow-wrap: anywhere;
  }

  .stage-card__head {
    display: flex;
    justify-content: space-between;
    gap: 10px;
  }

  .stage-card__fallback,
  .related-signals {
    display: grid;
    gap: 8px;
    margin-top: 2px;
    padding-top: 12px;
    border-top: 1px solid var(--border-1);
  }

  .stage-card__fallback strong {
    color: var(--fg-1);
    font-size: 14px;
    line-height: 1.3;
    overflow-wrap: anywhere;
  }

  .stage-card__fallback p {
    color: var(--fg-2);
    font-size: 12.5px;
    line-height: 1.45;
    overflow-wrap: anywhere;
  }

  .stage-card--latest {
    max-height: min(620px, 72vh);
    overflow-y: auto;
    scrollbar-gutter: stable;
  }

  .stage-card--latest > p {
    max-height: min(280px, 36vh);
    overflow-y: auto;
    padding-right: 6px;
    scrollbar-gutter: stable;
  }

  .stage-card--events {
    max-height: min(620px, 72vh);
    overflow: hidden;
  }

  .stage-card--events ol,
  .all-events ol {
    display: grid;
    gap: 0;
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .stage-card--events ol {
    max-height: min(520px, calc(72vh - 82px));
    overflow-y: auto;
    padding-right: 6px;
    scrollbar-gutter: stable;
  }

  .stage-card--events li,
  .all-events li {
    display: grid;
    grid-template-columns: 72px minmax(0, 1fr);
    gap: 10px;
    padding: 12px 0;
    border-top: 1px solid var(--border-1);
  }

  .stage-card--events li:first-child,
  .all-events li:first-child {
    border-top: 0;
  }

  .stage-card--events li > span,
  .all-events li > span,
  .all-events small {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10px;
    text-transform: uppercase;
  }

  .stage-card--events strong,
  .all-events strong {
    display: block;
    color: var(--fg-1);
    font-size: 13px;
    line-height: 1.3;
    margin-bottom: 3px;
    overflow-wrap: anywhere;
  }

  .stage-card--events p,
  .all-events p {
    color: var(--fg-2);
    font-size: 12.5px;
    line-height: 1.45;
    margin-bottom: 5px;
    overflow-wrap: anywhere;
  }

  .stage-card a,
  .source-link {
    color: var(--signal-live);
    font-family: var(--font-mono);
    font-size: 11px;
    text-decoration: none;
    text-transform: uppercase;
    max-width: 100%;
    overflow-wrap: anywhere;
    width: fit-content;
  }

  .stage-card a:hover,
  .source-link:hover {
    text-decoration: underline;
  }

  .evidence-chain {
    display: grid;
    gap: 10px;
    padding: 14px 16px;
    border-top: 1px solid var(--border-1);
    background: rgba(255, 255, 255, 0.018);
  }

  .evidence-chain ol {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 8px;
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .evidence-chain li {
    display: grid;
    gap: 4px;
    min-width: 0;
    padding: 10px;
    border: 1px solid var(--border-1);
    border-radius: 6px;
    background: var(--bg-inset);
  }

  .evidence-chain strong,
  .evidence-chain a {
    color: var(--fg-1);
    font-size: 13px;
    line-height: 1.25;
    overflow-wrap: anywhere;
  }

  .evidence-chain a {
    color: var(--signal-live);
    text-decoration: none;
  }

  .evidence-chain a:hover {
    text-decoration: underline;
  }

  .evidence-chain small {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10.5px;
    line-height: 1.35;
    overflow-wrap: anywhere;
  }

  .json-disclosure {
    border-top: 1px solid var(--border-1);
    padding: 0 16px 4px;
  }

  .json-disclosure summary {
    cursor: pointer;
    padding: 12px 0;
    width: fit-content;
  }

  .json-disclosure pre {
    max-height: min(440px, 58vh);
    margin: 0 0 12px;
    padding: 12px;
    overflow: auto;
    border: 1px solid var(--border-1);
    border-radius: 6px;
    background: rgba(0, 0, 0, 0.22);
    color: var(--fg-2);
    font-family: var(--font-mono);
    font-size: 11px;
    line-height: 1.45;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .empty {
    color: var(--fg-3) !important;
  }

  .all-events {
    border-top: 1px solid var(--border-1);
    padding: 0 16px 4px;
  }

  .all-events summary {
    cursor: pointer;
    padding: 12px 0;
    width: fit-content;
  }

  .all-events[open] summary {
    border-bottom: 1px solid var(--border-1);
  }

  .source-trail {
    margin-top: 12px;
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 11px;
  }

  .source-trail summary {
    cursor: pointer;
    width: fit-content;
  }

  .source-trail ul {
    display: grid;
    gap: 4px;
    margin: 8px 0 0;
    padding-left: 18px;
  }

  @keyframes live-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.4;
    }
  }

  @media (max-width: 1180px) {
    .loop-overview,
    .stage-detail__head,
    .stage-detail__grid {
      grid-template-columns: 1fr;
    }
    .evidence-chain ol {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .stage-detail__meta {
      justify-content: start;
    }
    .stage-card {
      border-left: 0;
      border-top: 1px solid var(--border-1);
    }
    .stage-card:first-child {
      border-top: 0;
    }
  }

  @media (max-width: 860px) {
    .live-loop__head {
      grid-template-columns: 1fr;
    }
    .live-loop__actions {
      justify-items: start;
    }
    .live-loop__actions span {
      text-align: left;
    }
    .live-rail {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @media (max-width: 520px) {
    .live-loop {
      padding: 16px;
    }
    .live-loop__actions {
      grid-template-columns: 1fr 1fr;
    }
    .refresh {
      width: 100%;
    }
    .live-rail {
      grid-template-columns: 1fr;
    }
    .live-stage {
      min-height: 132px;
      height: auto;
    }
    .stage-detail__head,
    .stage-card {
      padding: 14px;
    }
    .stage-detail__meta span {
      max-width: 100%;
    }
    .stage-card dl div,
    .stage-card--events li,
    .all-events li,
    .evidence-chain ol {
      grid-template-columns: 1fr;
    }
  }
</style>
