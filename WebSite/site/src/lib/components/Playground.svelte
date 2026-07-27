<!--
  Playground — live MCP console, embedded in /connect.
  Type a tool call, watch the JSON-RPC envelope go out, see the response,
  and inspect the same public discovery surface a chatbot uses.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import RitualLabel from '$lib/components/Primitives/RitualLabel.svelte';
  import {
    callTool,
    parseInput,
    summarize,
    type CallResult
  } from '$lib/mcp/playground';

  type DisclosureMode = 'pretty' | 'json' | 'wire';

  type HistoryEntry = {
    id: number; canonical: string; tool: string; args: Record<string, unknown>;
    status: 'pending' | 'ok' | 'error'; elapsedMs: number;
    summary: string | null; parsed: any; raw: any; trace: any; initTrace: any;
    error?: string; at: string;
  };
  type Chip = { label: string; sub: string; canonical: string; color: string };

  const CHIPS: Chip[] = [
    { label: 'Browse discovery pages', sub: 'read_page changed_since=1970-01-01T00:00:00Z max_results=100', canonical: 'read_page changed_since=1970-01-01T00:00:00Z max_results=100', color: 'var(--ember-500)' },
    { label: 'Active universes', sub: 'read_graph target=graphs limit=100', canonical: 'read_graph target=graphs limit=100', color: 'var(--signal-live)' }
  ];

  let inputValue = $state('read_graph target=graphs limit=100');
  let inputError = $state<string | null>(null);
  let busy = $state(false);
  let mode = $state<DisclosureMode>('pretty');
  let history = $state<HistoryEntry[]>([]);
  let nextHistoryId = 1;

  const current = $derived<HistoryEntry | null>(history[0] ?? null);

  function nowStamp(): string {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  async function run(canonical?: string) {
    const text = canonical ?? inputValue;
    const parsedInput = parseInput(text);
    if (!parsedInput.ok) { inputError = parsedInput.error; return; }
    inputError = null;
    inputValue = parsedInput.canonical;

    const id = nextHistoryId++;
    const at = nowStamp();
    const placeholder: HistoryEntry = {
      id, canonical: parsedInput.canonical, tool: parsedInput.tool, args: parsedInput.args,
      status: 'pending', elapsedMs: 0, summary: null, parsed: null, raw: null, trace: null, initTrace: null, at
    };
    history = [placeholder, ...history].slice(0, 12);
    busy = true;

    const t0 = performance.now();
    try {
      const res: CallResult = await callTool(parsedInput.tool, parsedInput.args as Record<string, any>);
      const elapsedMs = Math.round(performance.now() - t0);
      const summary = summarize(parsedInput.tool, res.parsed);
      history = [{ ...placeholder, status: 'ok', elapsedMs, parsed: res.parsed, raw: res.raw, trace: res.trace, initTrace: res.initTrace ?? null, summary }, ...history.slice(1)];
    } catch (err: any) {
      const elapsedMs = Math.round(performance.now() - t0);
      const trace = err?.trace ?? null;
      history = [{ ...placeholder, status: 'error', elapsedMs, error: err?.message ?? String(err), trace, initTrace: null, parsed: trace?.response?.body ?? null, raw: null, summary: null }, ...history.slice(1)];
    } finally {
      busy = false;
    }
  }

  function onKeydown(e: KeyboardEvent) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void run(); } }
  function selectChip(c: Chip) { inputValue = c.canonical; void run(); }
  function setMode(m: DisclosureMode) { mode = m; }
  function jsonPretty(v: unknown): string { if (v == null) return 'null'; try { return JSON.stringify(v, null, 2); } catch { return String(v); } }
  function statusTone(s: HistoryEntry['status']): string { return s === 'ok' ? 'var(--signal-live)' : s === 'error' ? 'var(--signal-error)' : 'var(--signal-idle)'; }

  onMount(() => {
    void run();
  });
</script>

<section class="ch ch--hero" aria-labelledby="pg-title">
  <div class="ch__inner">
    <RitualLabel color="var(--signal-live)">· try it live ·</RitualLabel>
    <h2 id="pg-title">Or just fire a call right here.</h2>
    <p class="lede">
      No setup, no account. Type a call to <code>tinyassets.io/mcp</code> — or
      tap a chip — and watch the real JSON-RPC envelope leave your browser and
      the response come back. This is the exact surface your chatbot uses when
      you say <em>"browse the wiki."</em>
    </p>

    <form class="repl" onsubmit={(e) => { e.preventDefault(); void run(); }}>
      <div class="repl__row">
        <span class="repl__prompt" aria-hidden="true">›</span>
        <input class="repl__input" type="text" spellcheck="false" autocomplete="off" autocorrect="off" autocapitalize="off" placeholder="read_graph target=graphs limit=100" bind:value={inputValue} onkeydown={onKeydown} aria-label="MCP tool call" disabled={busy} />
        <button class="repl__run" type="submit" disabled={busy} aria-busy={busy}>{busy ? 'Calling…' : 'Run'}</button>
      </div>
      {#if inputError}
        <p class="repl__error">{inputError}</p>
      {:else}
        <p class="repl__hint">Format: <code>tool target=value key=value …</code>. Press Enter to send.</p>
      {/if}
    </form>

    <div class="chips" role="toolbar" aria-label="Starter calls">
      {#each CHIPS as chip}
        <button type="button" class="chip" style:--chip-color={chip.color} onclick={() => selectChip(chip)} disabled={busy}>
          <strong>{chip.label}</strong>
          <code>{chip.sub}</code>
        </button>
      {/each}
    </div>
  </div>
</section>

<section class="board">
  <div class="board__grid">
    <aside class="voice" aria-label="User-buildable workflow design">
      <header class="voice__head">
        <RitualLabel color="var(--violet-400)">· user-buildable ·</RitualLabel>
      </header>
      <p class="voice__lede">
        Each universe is user-buildable. Define the stages, tools, and review
        gates that fit the work instead of inheriting a fixed pipeline.
      </p>
      <ul class="guide__list">
        <li>Start with the shape of your own project.</li>
        <li>Give the daemon tools without scripting every decision.</li>
        <li>Keep human review where the work needs judgment.</li>
      </ul>
    </aside>

    <article class="terminal" aria-label="MCP call output">
      <header class="terminal__head">
        <div class="terminal__title">
          <RitualLabel color="var(--ember-500)">· last call ·</RitualLabel>
          {#if current}
            <code class="terminal__call" title={current.canonical}>{current.canonical}</code>
            <span class="terminal__status" style:color={statusTone(current.status)}>
              {current.status === 'pending' ? '…' : current.status === 'ok' ? `✓ ${current.elapsedMs}ms` : `✗ ${current.elapsedMs}ms`}
            </span>
          {:else}
            <p class="terminal__placeholder">Hit Enter or pick a chip to fire the first call.</p>
          {/if}
        </div>
        <div class="terminal__tabs" role="tablist" aria-label="Disclosure mode">
          {#each ['pretty', 'json', 'wire'] as m}
            <button type="button" role="tab" aria-selected={mode === m} class:active={mode === m} onclick={() => setMode(m as DisclosureMode)}>{m}</button>
          {/each}
        </div>
      </header>

      <div class="terminal__body">
        {#if !current}
          <div class="terminal__empty"><p>The terminal is loaded with <code>read_graph target=graphs limit=100</code> and will fire automatically.</p></div>
        {:else if current.status === 'pending'}
          <div class="terminal__pending">
            <span class="dot"></span>
            <p>Sending JSON-RPC over HTTP to <code>{import.meta.env.DEV ? '/mcp-live' : '/mcp'}</code>…</p>
          </div>
        {:else if mode === 'pretty'}
          <div class="pane pane--pretty">
            {#if current.status === 'error'}
              <p class="pane__error">{current.error}</p>
              {#if current.trace}<p class="pane__hint">Switch to <strong>wire</strong> to see the failed envelope.</p>{/if}
            {:else if current.summary}
              <p class="pane__sum">{current.summary}</p>
              <p class="pane__nudge">That's the plain-English read. Switch to <strong>json</strong> for the parsed payload, or <strong>wire</strong> for the actual JSON-RPC envelope.</p>
            {:else}
              <p class="pane__sum">Response parsed cleanly but doesn't have a known summary shape. Switch to <strong>json</strong> to see the full structure.</p>
            {/if}
          </div>
        {:else if mode === 'json'}
          <div class="pane pane--json"><pre><code>{jsonPretty(current.parsed)}</code></pre></div>
        {:else}
          <div class="pane pane--wire">
            <h3>Request</h3>
            <pre><code>POST {current.trace?.request?.url ?? '?'}
{Object.entries(current.trace?.request?.headers ?? {}).map(([k, v]) => `${k}: ${v}`).join('\n')}

{jsonPretty(current.trace?.request?.body)}</code></pre>

            <h3>Response · {current.trace?.response?.status ?? '?'} {current.trace?.response?.statusText ?? ''} · {current.trace?.response?.timeMs ?? 0}ms</h3>
            <pre><code>{Object.entries(current.trace?.response?.headers ?? {}).map(([k, v]) => `${k}: ${v}`).join('\n')}

{jsonPretty(current.trace?.response?.body)}</code></pre>

            {#if current.initTrace}
              <details class="wire__init">
                <summary>One-time MCP <code>initialize</code> handshake (this session)</summary>
                <pre><code>{jsonPretty(current.initTrace)}</code></pre>
              </details>
            {/if}
          </div>
        {/if}
      </div>

      {#if history.length > 1}
        <footer class="terminal__history">
          <RitualLabel>· call history ·</RitualLabel>
          <ol>
            {#each history.slice(1, 6) as h}
              <li>
                <button type="button" onclick={() => { inputValue = h.canonical; void run(); }}>
                  <span class="dot" style:background={statusTone(h.status)}></span>
                  <code>{h.canonical}</code>
                  <small>{h.elapsedMs}ms · {h.at}</small>
                </button>
              </li>
            {/each}
          </ol>
        </footer>
      {/if}
    </article>

    <aside class="pulse" aria-label="Remixable universe discovery">
      <header class="pulse__head">
        <RitualLabel color="var(--signal-live)">· remixable ·</RitualLabel>
      </header>
      <p class="pulse__lede">
        Public graph discovery shows which universes are available to explore.
        Open one as a pattern, then remix its structure for a different domain.
      </p>
      <ul class="guide__list">
        <li>Discover public universe metadata.</li>
        <li>Study the workflow shape and its declared purpose.</li>
        <li>Remix the useful pattern without copying private state.</li>
      </ul>
    </aside>
  </div>
</section>

<style>
  /* ── Hero ─────────────────────────────────────────────────────────── */
  .ch--hero {
    padding: 80px 24px 36px;
    background:
      radial-gradient(ellipse 80% 60% at 30% 0%, rgba(138, 99, 206, 0.10), transparent 60%),
      radial-gradient(ellipse 50% 40% at 80% 30%, rgba(109, 211, 166, 0.06), transparent 60%);
  }
  .ch__inner { max-width: 1100px; margin: 0 auto; }
  #pg-title {
    font-family: var(--font-display);
    font-variation-settings: "opsz" 144, "SOFT" 60;
    font-size: clamp(40px, 6.2vw, 68px);
    font-weight: 400;
    letter-spacing: -0.025em;
    line-height: 0.98;
    margin: 12px 0 18px;
    max-width: 22ch;
    text-wrap: balance;
  }
  .lede {
    font-size: 17px;
    line-height: 1.65;
    color: var(--fg-2);
    max-width: 64ch;
    margin: 0 0 28px;
  }
  .lede em { font-style: italic; color: var(--ember-300); }
  .lede code {
    font-family: var(--font-mono);
    font-size: 0.92em;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid var(--border-1);
    padding: 1px 6px;
    border-radius: 4px;
    color: var(--violet-200);
  }

  .repl { margin: 8px 0 18px; }
  .repl__row {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: stretch;
    border: 1px solid rgba(109, 211, 166, 0.42);
    background: var(--bg-inset);
    border-radius: 10px;
    overflow: hidden;
    transition: border-color var(--dur-base) var(--ease-summon), box-shadow var(--dur-base) var(--ease-summon);
  }
  .repl__row:focus-within { border-color: rgba(109, 211, 166, 0.85); box-shadow: 0 0 0 3px rgba(109, 211, 166, 0.18); }
  .repl__prompt {
    display: grid; place-items: center; width: 44px;
    color: var(--signal-live);
    font-family: var(--font-mono); font-size: 22px; line-height: 1;
    background: rgba(109, 211, 166, 0.06);
    border-right: 1px solid var(--border-1);
  }
  .repl__input {
    background: transparent; border: 0;
    color: var(--fg-1);
    font-family: var(--font-mono); font-size: 17px; line-height: 1.4;
    min-height: 56px; padding: 0 14px; outline: none; width: 100%;
  }
  .repl__input::placeholder { color: var(--fg-3); }
  .repl__run {
    background: var(--ember-600); border: 0; color: var(--fg-on-ember);
    cursor: pointer; font-family: var(--font-mono); font-size: 12px;
    letter-spacing: 0.14em; padding: 0 22px; text-transform: uppercase;
    transition: background var(--dur-fast) var(--ease-standard);
  }
  .repl__run:hover:not(:disabled) { background: var(--ember-500); }
  .repl__run:disabled { background: var(--ember-700); cursor: wait; opacity: 0.7; }
  .repl__hint, .repl__error {
    margin: 8px 0 0;
    font-family: var(--font-mono); font-size: 11.5px;
    color: var(--fg-3);
  }
  .repl__hint code { background: rgba(255,255,255,0.04); border: 1px solid var(--border-1); padding: 1px 5px; border-radius: 3px; color: var(--violet-200); }
  .repl__error { color: var(--signal-error); }

  .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; }
  .chip {
    --chip-color: var(--ember-500);
    display: grid; gap: 3px;
    padding: 9px 13px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: 8px;
    color: inherit; cursor: pointer; text-align: left;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard), transform var(--dur-fast) var(--ease-standard);
  }
  .chip:hover:not(:disabled) { border-color: var(--chip-color); background: rgba(255,255,255,0.04); transform: translateY(-1px); }
  .chip:disabled { opacity: 0.55; cursor: wait; }
  .chip strong { color: var(--fg-1); font-family: var(--font-sans); font-size: 13px; font-weight: 600; line-height: 1.25; }
  .chip code { background: transparent; border: 0; padding: 0; color: var(--chip-color); font-family: var(--font-mono); font-size: 10.5px; line-height: 1.35; }

  /* ── Board ────────────────────────────────────────────────────────── */
  .board {
    padding: 28px 24px 64px;
    border-top: 1px solid var(--border-1);
    background: var(--bg-1);
  }
  .board__grid {
    max-width: 1380px;
    margin: 0 auto;
    display: grid;
    grid-template-columns: minmax(220px, 0.75fr) minmax(0, 1.5fr) minmax(220px, 0.75fr);
    gap: 16px;
    align-items: start;
  }
  @media (max-width: 1180px) {
    .board__grid { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
    .terminal { grid-column: 1 / -1; order: -1; }
  }
  @media (max-width: 760px) { .board__grid { grid-template-columns: 1fr; } }

  .voice, .pulse {
    padding: 16px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: 10px;
    min-height: 200px;
  }
  .voice__head, .pulse__head { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; }
  .voice__lede, .pulse__lede { color: var(--fg-3); font-size: 12px; line-height: 1.55; margin: 0 0 12px; }
  .guide__list { color: var(--fg-2); display: grid; font-size: 12px; gap: 8px; line-height: 1.5; margin: 0; padding-left: 18px; }
  .guide__list li::marker { color: var(--signal-live); }

  /* ── Terminal ─────────────────────────────────────────────────────── */
  .terminal {
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: 10px;
    overflow: hidden;
    min-width: 0;
  }
  .terminal__head {
    display: grid; grid-template-columns: minmax(0, 1fr) auto;
    gap: 12px; align-items: start;
    padding: 14px 16px;
    background: var(--bg-inset);
    border-bottom: 1px solid var(--border-1);
  }
  .terminal__title { display: grid; gap: 4px; min-width: 0; }
  .terminal__call { color: var(--fg-1); font-family: var(--font-mono); font-size: 13px; overflow-wrap: anywhere; background: transparent; border: 0; padding: 0; }
  .terminal__status { font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; }
  .terminal__placeholder { margin: 0; color: var(--fg-2); font-size: 13px; }
  .terminal__tabs {
    display: flex; gap: 4px;
    background: rgba(0,0,0,0.25); border: 1px solid var(--border-1); border-radius: 6px; padding: 3px;
  }
  .terminal__tabs button {
    background: transparent; border: 0; border-radius: 4px;
    color: var(--fg-3); cursor: pointer;
    font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.1em;
    padding: 5px 10px; text-transform: uppercase;
  }
  .terminal__tabs button.active { background: var(--ember-600); color: var(--fg-on-ember); }
  .terminal__tabs button:hover:not(.active) { color: var(--fg-1); }
  .terminal__body { padding: 0; min-height: 220px; }
  .terminal__empty, .terminal__pending {
    align-items: center; color: var(--fg-2); display: flex; gap: 12px;
    padding: 36px 24px;
  }
  .terminal__pending .dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--violet-400);
    box-shadow: 0 0 12px rgba(138,99,206,0.7);
    animation: live-pulse 1.6s ease-in-out infinite;
  }
  @keyframes live-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }

  .pane { padding: 18px 22px; min-height: 200px; }
  .pane--pretty p { color: var(--fg-1); font-size: 16px; line-height: 1.6; max-width: 70ch; }
  .pane__sum {
    color: var(--fg-1);
    font-family: var(--font-display); font-size: 22px !important; font-weight: 400;
    line-height: 1.35 !important;
  }
  .pane__nudge { color: var(--fg-3) !important; font-size: 13px !important; margin-top: 14px !important; }
  .pane__nudge strong { color: var(--ember-500); font-weight: 500; }
  .pane__error { color: var(--signal-error) !important; font-family: var(--font-mono); font-size: 13px !important; }
  .pane__hint { color: var(--fg-3) !important; font-size: 12px !important; margin-top: 10px; }
  .pane__hint strong { color: var(--ember-500); }

  .pane--json pre, .pane--wire pre {
    background: var(--bg-inset); border: 1px solid var(--border-1); border-radius: 6px;
    margin: 0; max-height: 460px; overflow: auto; padding: 14px;
  }
  .pane--json code, .pane--wire code {
    background: transparent; border: 0; color: var(--fg-1);
    font-family: var(--font-mono); font-size: 12px; line-height: 1.55;
    padding: 0; white-space: pre;
  }
  .pane--wire { display: grid; gap: 14px; }
  .pane--wire h3 {
    color: var(--ember-500);
    font-family: var(--font-mono); font-size: 11px; font-weight: 500;
    letter-spacing: 0.14em; margin: 0; text-transform: uppercase;
  }
  .pane--wire pre { max-height: 280px; }
  .wire__init { margin-top: 4px; }
  .wire__init summary {
    color: var(--fg-3); cursor: pointer;
    font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.08em;
    padding: 6px 0; text-transform: uppercase; width: fit-content;
  }
  .wire__init code {
    background: rgba(255,255,255,0.04); border: 1px solid var(--border-1);
    padding: 1px 4px; border-radius: 3px; color: var(--violet-200); font-size: 10.5px;
  }

  .terminal__history { border-top: 1px solid var(--border-1); padding: 12px 16px; }
  .terminal__history ol { list-style: none; margin: 8px 0 0; padding: 0; display: grid; gap: 4px; }
  .terminal__history button {
    align-items: center; background: transparent; border: 0; color: inherit;
    cursor: pointer; display: grid; gap: 8px;
    grid-template-columns: 10px minmax(0, 1fr) auto;
    padding: 6px 4px; text-align: left; width: 100%;
  }
  .terminal__history button:hover { background: rgba(255,255,255,0.03); }
  .terminal__history .dot { width: 8px; height: 8px; border-radius: 50%; }
  .terminal__history code {
    background: transparent; border: 0;
    color: var(--fg-2); font-family: var(--font-mono); font-size: 11.5px;
    overflow: hidden; padding: 0; text-overflow: ellipsis; white-space: nowrap;
  }
  .terminal__history small { color: var(--fg-3); font-family: var(--font-mono); font-size: 10px; }

</style>
