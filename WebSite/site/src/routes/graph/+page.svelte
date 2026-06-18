<!--
  /graph — the living map. Obsidian-style force graph, 2026-06-10 rebuild.

  Every wiki page is its own dot (1,200+), clustered around category hubs
  the way Obsidian notes cluster around tags. Goals and universes are their
  own constellations. The layout is a real physics settle (d3-force), not a
  designed diagram — you watch it breathe into place, then pan, zoom, hover
  to focus a neighbourhood, and drag nodes around.

  Honesty rails:
    - bright lines are REAL page→page references from the snapshot;
    - the faintest spokes are filing (page→its category) — metadata,
      labelled as such in the legend, never dressed up as citations;
    - first paint is the baked snapshot, stamped; Refresh MCP re-reads live;
    - dot size = how often a page is actually referenced.

  Interaction: hover = focus neighbourhood · click hub = newest pages panel
  with chatbot-read prompts · click goal = /goals/<id> · click universe =
  detail panel · drag = move a node · wheel = zoom · drag ground = pan.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import baked from '$lib/content/mcp-snapshot.json';
  import { fetchLive, liveToSnapshotShape } from '$lib/mcp/live';
  import type { Snapshot } from '$lib/mcp/types';
  import { fmtStamp, fmtRel } from '$lib/fmt';
  import Tick from '$lib/components/Tick.svelte';
  import { buildAtlas, CATEGORY_BLURB, REPO_URL, type CategoryId, type Snapshotish } from '$lib/graph/atlas';
  import {
    buildForceGraph,
    createSimulation,
    type FNode,
    type ForceGraph,
    type FCluster
  } from '$lib/graph/force';
  import type { Simulation } from 'd3-force';

  const MCP_URL = 'https://tinyassets.io/mcp';
  const PER_CATEGORY = 30;

  // First paint from the baked snapshot; Refresh MCP swaps in a live re-read
  // of the exact same shape, so the whole sky rebuilds against fresh data.
  let snapshot = $state<Snapshot>(baked as unknown as Snapshot);
  let liveStamp = $state<string | null>(null);
  let reading = $state(false);
  let liveErr = $state<string | null>(null);

  const atlas = $derived(buildAtlas(snapshot as unknown as Snapshotish));
  let refCount = $state(0);
  let dotCount = $state(0);

  // ── Selection drives the side panel. Nothing pre-selected. ──
  type Selection = { kind: 'none' } | { kind: 'category'; id: CategoryId } | { kind: 'universe'; id: string };
  let selection = $state<Selection>({ kind: 'none' });

  const selectedCategory = $derived(selection.kind === 'category' ? selection.id : null);
  const selectedUniverse = $derived.by(() => {
    const sel = selection;
    if (sel.kind !== 'universe') return null;
    return (snapshot.universes ?? []).find((x: any) => x.id === sel.id) ?? null;
  });
  const categoryPages = $derived(selectedCategory ? atlas.pagesByCategory[selectedCategory] : []);
  const categoryTitle = $derived(selectedCategory === 'patch' ? 'patch requests & bugs' : (selectedCategory ?? ''));

  function clearSelection() {
    selection = { kind: 'none' };
  }

  // ── Live refresh: re-pull, re-stamp, re-settle. Never fakes a baked number. ──
  async function refresh() {
    reading = true;
    try {
      const live = await fetchLive();
      snapshot = liveToSnapshotShape(live, baked as unknown as Snapshot);
      liveStamp = live.fetchedAt;
      liveErr = null;
      setupGraph();
    } catch (e: any) {
      liveErr = e?.message ?? String(e);
    } finally {
      reading = false;
    }
  }

  // ── Copyable per-row chatbot read prompt — the honest bridge from /commons. ──
  let copiedPath = $state<string | null>(null);
  let copyTimer: number | null = null;
  async function copyReadPrompt(path: string) {
    const clean = path.replace(/\.md$/, '');
    const prompt = `Read the wiki page "${clean}" from my Workflow connector`;
    try {
      await navigator.clipboard.writeText(prompt);
      copiedPath = path;
      if (copyTimer) clearTimeout(copyTimer);
      copyTimer = window.setTimeout(() => (copiedPath = null), 1600);
    } catch {
      /* clipboard unavailable; the path is still visible to copy by hand */
    }
  }

  const wikiTotal = $derived(
    atlas.counts.patch + atlas.counts.plans + atlas.counts.notes + atlas.counts.concepts + atlas.counts.drafts
  );
  const stampLabel = $derived(
    liveStamp ? `live read ${fmtRel(liveStamp)}` : `baked snapshot ${fmtStamp(snapshot.fetched_at)}`
  );
  const universesList = $derived(snapshot.universes ?? []);

  /* ════════════════════ the canvas force graph ════════════════════ */

  let canvasEl: HTMLCanvasElement;
  let wrapEl: HTMLDivElement;
  let graph: ForceGraph | null = null;
  let sim: Simulation<FNode, undefined> | null = null;
  let hovered: FNode | null = null;
  let tf = { x: 0, y: 0, k: 1 };
  let cw = 0;
  let ch = 0;
  let dpr = 1;
  let raf = 0;
  let needsDraw = true;
  let userMoved = false;
  let fittedOnce = false;
  let reduced = false;

  // Field Notes ink on paper — green stays reserved for liveness.
  const FILL: Record<FCluster, string> = {
    patch: '#b62744',
    plans: '#1c1a14',
    notes: '#736d54',
    concepts: '#6b44a8',
    drafts: '#b3a988',
    goals: '#e94560',
    universes: '#6b44a8',
    tags: '#8b6db0'
  };
  const PAPER = '#f4f1e7';
  const INK = '#1c1a14';

  function setupGraph() {
    sim?.stop();
    graph = buildForceGraph(snapshot as unknown as Snapshotish, atlas.pagesByCategory);
    refCount = graph.refLinkCount;
    dotCount = graph.pageCount;
    sim = createSimulation(graph);
    hovered = null;
    fittedOnce = false;
    if (reduced) {
      sim.tick(280);
      fitView();
      fittedOnce = true;
    }
    needsDraw = true;
  }

  function fitView() {
    if (!graph || userMoved) return;
    let minX = Infinity,
      maxX = -Infinity,
      minY = Infinity,
      maxY = -Infinity;
    for (const n of graph.nodes) {
      if (n.x! < minX) minX = n.x!;
      if (n.x! > maxX) maxX = n.x!;
      if (n.y! < minY) minY = n.y!;
      if (n.y! > maxY) maxY = n.y!;
    }
    const w = Math.max(200, maxX - minX);
    const h = Math.max(200, maxY - minY);
    const k = Math.min(1.7, Math.min((cw - 120) / w, (ch - 120) / h));
    tf = { x: -((minX + maxX) / 2) * k, y: -((minY + maxY) / 2) * k, k };
  }

  function toWorld(mx: number, my: number) {
    return { x: (mx - cw / 2 - tf.x) / tf.k, y: (my - ch / 2 - tf.y) / tf.k };
  }

  function nodeAt(mx: number, my: number): FNode | null {
    if (!graph) return null;
    const p = toWorld(mx, my);
    let best: FNode | null = null;
    let bestD = Infinity;
    for (const n of graph.nodes) {
      const d = Math.hypot((n.x ?? 0) - p.x, (n.y ?? 0) - p.y);
      const hit = Math.max(n.r + 2.5, 7 / tf.k);
      if (d < hit && d < bestD) {
        bestD = d;
        best = n;
      }
    }
    return best;
  }

  function kick(alpha: number) {
    if (!sim) return;
    if (sim.alpha() < alpha) sim.alpha(alpha);
    needsDraw = true;
  }

  function truncate(s: string, max: number): string {
    return s.length <= max ? s : s.slice(0, max - 1).trimEnd() + '…';
  }

  function draw() {
    if (!graph || !canvasEl) return;
    const ctx = canvasEl.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cw, ch);
    ctx.translate(cw / 2 + tf.x, ch / 2 + tf.y);
    ctx.scale(tf.k, tf.k);

    const focus = hovered ? graph.adjacency.get(hovered.id) : null;

    // ── edges: filing spokes faint, real references brighter ──
    for (const pass of [0, 1] as const) {
      for (const l of graph.links) {
        const s = l.source as FNode;
        const t = l.target as FNode;
        const isRef = l.kind === 'ref';
        if ((pass === 1) !== isRef) continue;
        const inFocus = hovered && (s === hovered || t === hovered);
        if (focus && !inFocus) {
          ctx.strokeStyle = isRef ? 'rgba(28,26,20,0.045)' : 'rgba(28,26,20,0.018)';
        } else if (inFocus) {
          ctx.strokeStyle = isRef ? 'rgba(182,39,68,0.62)' : 'rgba(28,26,20,0.26)';
        } else {
          ctx.strokeStyle = isRef ? 'rgba(28,26,20,0.17)' : 'rgba(28,26,20,0.05)';
        }
        ctx.lineWidth = (isRef ? (inFocus ? 1.5 : 0.9) : 0.55) / Math.sqrt(tf.k);
        ctx.beginPath();
        ctx.moveTo(s.x!, s.y!);
        ctx.lineTo(t.x!, t.y!);
        ctx.stroke();
      }
    }

    // ── nodes ──
    for (const n of graph.nodes) {
      const dim = focus ? n !== hovered && !focus.has(n.id) : false;
      ctx.globalAlpha = dim ? 0.13 : 1;
      ctx.beginPath();
      ctx.arc(n.x!, n.y!, n.r, 0, Math.PI * 2);
      if (n.kind === 'tag') {
        ctx.fillStyle = PAPER;
        ctx.fill();
        ctx.strokeStyle = FILL[n.cluster];
        ctx.lineWidth = 1.7 / Math.sqrt(tf.k);
        ctx.stroke();
      } else if (n.cluster === 'drafts') {
        ctx.fillStyle = PAPER;
        ctx.fill();
        ctx.strokeStyle = FILL.drafts;
        ctx.lineWidth = 1 / Math.sqrt(tf.k);
        ctx.stroke();
      } else {
        ctx.fillStyle = FILL[n.cluster];
        ctx.fill();
      }
      if (n === hovered) {
        ctx.beginPath();
        ctx.arc(n.x!, n.y!, n.r + 3.5 / tf.k, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(182,39,68,0.85)';
        ctx.lineWidth = 1.6 / tf.k;
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;

    // ── labels (screen-constant size; collision-avoided so they never pile up) ──
    const placed: Array<[number, number, number, number]> = [];
    const overlaps = (b: [number, number, number, number]) =>
      placed.some((q) => b[0] < q[2] && b[2] > q[0] && b[1] < q[3] && b[3] > q[1]);

    const label = (
      text: string,
      x: number,
      y: number,
      px: number,
      fill: string,
      font: string,
      align: CanvasTextAlign = 'left',
      avoid = false
    ): boolean => {
      ctx.font = `${px / tf.k}px ${font}`;
      ctx.textAlign = align;
      const w = ctx.measureText(text).width;
      const h = px / tf.k;
      const x0 = align === 'center' ? x - w / 2 : x;
      const box: [number, number, number, number] = [x0 - 1 / tf.k, y - h, x0 + w + 1 / tf.k, y + h * 0.34];
      if (avoid && overlaps(box)) return false;
      ctx.lineWidth = 3.2 / tf.k;
      ctx.strokeStyle = PAPER;
      ctx.lineJoin = 'round';
      ctx.strokeText(text, x, y);
      ctx.fillStyle = fill;
      ctx.fillText(text, x, y);
      placed.push(box);
      return true;
    };

    for (const n of graph.nodes) {
      const dim = focus ? n !== hovered && !focus.has(n.id) : false;
      if (dim) continue;
      if (n.kind === 'tag' && n.cluster !== 'tags') {
        label(
          `${n.label} · ${n.count?.toLocaleString() ?? ''}`,
          n.x!,
          n.y! + n.r + 14 / tf.k,
          10.5,
          '#45412f',
          "'IBM Plex Mono', monospace",
          'center'
        );
      } else if (n.kind === 'tag' && (tf.k >= 0.75 || n === hovered)) {
        label(
          n.label,
          n.x! + n.r + 4 / tf.k,
          n.y! + 3 / tf.k,
          9,
          '#6a4f97',
          "'IBM Plex Mono', monospace",
          'left',
          n !== hovered
        );
      } else if ((n.kind === 'goal' || n.kind === 'universe') && (tf.k >= 0.55 || n === hovered)) {
        label(
          truncate(n.label, 30),
          n.x! + n.r + 5 / tf.k,
          n.y! + 3 / tf.k,
          n.kind === 'goal' ? 10 : 9,
          n.kind === 'goal' ? '#8a1a33' : '#4a2f76',
          n.kind === 'goal' ? "'Inter', sans-serif" : "'IBM Plex Mono', monospace",
          'left',
          n !== hovered
        );
      } else if (n.kind === 'page' && n !== hovered && tf.k >= 2.3) {
        label(truncate(n.label, 34), n.x! + n.r + 4 / tf.k, n.y! + 2.5 / tf.k, 8.5, '#736d54', "'Inter', sans-serif", 'left', true);
      }
    }

    if (hovered && hovered.kind === 'page') {
      label(
        truncate(hovered.label, 56),
        hovered.x! + hovered.r + 6 / tf.k,
        hovered.y! + 3 / tf.k,
        11,
        INK,
        "'Inter', sans-serif"
      );
    }
  }

  function loop() {
    raf = requestAnimationFrame(loop);
    if (!sim || !graph) return;
    const settling = sim.alpha() > 0.016;
    if (settling && !reduced) {
      sim.tick(2);
      if (!fittedOnce || sim.alpha() > 0.3) fitView();
      needsDraw = true;
    } else if (settling && reduced) {
      sim.tick(280);
      fitView();
      needsDraw = true;
    }
    if (!fittedOnce && !settling) {
      fitView();
      fittedOnce = true;
      needsDraw = true;
    }
    if (needsDraw) {
      needsDraw = false;
      draw();
    }
  }

  // ── pointer interactions: hover focus, drag nodes, pan, zoom ──
  let dragNode: FNode | null = null;
  let panning = false;
  let downAt = { x: 0, y: 0 };
  let movedPx = 0;

  function canvasPos(e: PointerEvent | WheelEvent) {
    const r = canvasEl.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  function onDown(e: PointerEvent) {
    const p = canvasPos(e);
    downAt = p;
    movedPx = 0;
    const n = nodeAt(p.x, p.y);
    if (n) {
      dragNode = n;
      const w = toWorld(p.x, p.y);
      n.fx = w.x;
      n.fy = w.y;
    } else {
      panning = true;
    }
    canvasEl.setPointerCapture(e.pointerId);
  }

  function onMove(e: PointerEvent) {
    const p = canvasPos(e);
    movedPx += Math.hypot(e.movementX, e.movementY);
    if (dragNode) {
      const w = toWorld(p.x, p.y);
      dragNode.fx = w.x;
      dragNode.fy = w.y;
      userMoved = true;
      kick(0.12);
      return;
    }
    if (panning) {
      tf.x += e.movementX;
      tf.y += e.movementY;
      userMoved = true;
      needsDraw = true;
      return;
    }
    const n = nodeAt(p.x, p.y);
    if (n !== hovered) {
      hovered = n;
      canvasEl.style.cursor = n ? 'pointer' : 'grab';
      needsDraw = true;
    }
  }

  function onUp(e: PointerEvent) {
    const clicked = movedPx < 5;
    if (dragNode) {
      const n = dragNode;
      dragNode = null;
      n.fx = null;
      n.fy = null;
      if (clicked) activate(n);
      else kick(0.1);
      return;
    }
    panning = false;
    if (clicked) clearSelection();
  }

  function onWheel(e: WheelEvent) {
    e.preventDefault();
    const p = canvasPos(e);
    const w = toWorld(p.x, p.y);
    const k = Math.min(6, Math.max(0.25, tf.k * Math.exp(-e.deltaY * 0.0016)));
    tf = { k, x: p.x - cw / 2 - w.x * k, y: p.y - ch / 2 - w.y * k };
    userMoved = true;
    needsDraw = true;
  }

  function activate(n: FNode) {
    if (n.kind === 'goal' && n.refId) {
      void goto(`/goals/${n.refId}`);
      return;
    }
    if (n.kind === 'universe' && n.refId) {
      selection =
        selection.kind === 'universe' && selection.id === n.refId ? { kind: 'none' } : { kind: 'universe', id: n.refId };
      return;
    }
    const cat = n.cluster;
    if (cat === 'goals' || cat === 'universes') return;
    selection = selectedCategory === cat ? { kind: 'none' } : { kind: 'category', id: cat };
  }

  onMount(() => {
    reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    dpr = Math.min(2, window.devicePixelRatio || 1);
    const ro = new ResizeObserver(() => {
      cw = wrapEl.clientWidth;
      ch = wrapEl.clientHeight;
      canvasEl.width = Math.round(cw * dpr);
      canvasEl.height = Math.round(ch * dpr);
      if (!userMoved) fitView();
      needsDraw = true;
    });
    ro.observe(wrapEl);
    cw = wrapEl.clientWidth;
    ch = wrapEl.clientHeight;
    canvasEl.width = Math.round(cw * dpr);
    canvasEl.height = Math.round(ch * dpr);
    canvasEl.style.cursor = 'grab';
    setupGraph();
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      sim?.stop();
      ro.disconnect();
    };
  });
</script>

<svelte:head>
  <title>Graph — the living map of Tiny's brain</title>
  <meta
    name="description"
    content="A live force-directed map of Tiny's public brain — every wiki page is a dot clustered around its category, goals and universes are their own constellations, and the bright lines are real page-to-page references. Pan, zoom, hover to focus, click through to read."
  />
</svelte:head>

<!-- 1 · Hero ──────────────────────────────────────────────────────────── -->
<section class="cover">
  <div class="container">
    <p class="eyebrow">field notes · the living map</p>
    <h1 class="cover__title">My head, <em>seen from above</em>.</h1>
    <p class="voice cover__lede">
      Every one of the {wikiTotal.toLocaleString()} pages in my memory is a dot
      in here, settling around its category the way notes cluster around tags.
      Goals burn ember; universes drift violet. The bright lines are real
      page-to-page references — {refCount} of them; the faintest spokes are
      filing and shared-tag clusters, and I'll never dress either up as a
      citation. Hover to light up a
      neighbourhood, scroll to zoom, drag anything that bothers you.
    </p>
    <p class="cover__stamp ev" aria-live="polite">
      <span class="dot" class:live={Boolean(liveStamp)}></span>
      {stampLabel} · {dotCount.toLocaleString()} page dots · {atlas.publicGoalCount} goals ·
      {atlas.universeCount} universes · {refCount} cross-references
      <button type="button" class="refresh" onclick={refresh} disabled={reading} aria-busy={reading}>
        {reading ? 'reading…' : 'Refresh MCP'}
      </button>
    </p>
    {#if liveErr}
      <p class="cover__err ev">
        live read failed — {liveErr}. The same data is reachable directly at
        <a href={MCP_URL}>{MCP_URL.replace('https://', '')}</a> through any MCP client.
      </p>
    {/if}
  </div>
</section>

<!-- 2 · The sky + side panel ──────────────────────────────────────────── -->
<section class="atlas">
  <div class="container atlas__shell">
    <figure class="map" aria-label="Force-directed map: every wiki page, goal, and universe as a dot; lines are real references">
      <div class="map__wrap" bind:this={wrapEl}>
        <canvas
          bind:this={canvasEl}
          onpointerdown={onDown}
          onpointermove={onMove}
          onpointerup={onUp}
          onpointercancel={onUp}
          onwheel={onWheel}
        ></canvas>
        <p class="map__hint ev">hover to focus · scroll to zoom · drag to pan or move a node</p>
      </div>
    </figure>

    <aside class="panel" aria-live="polite">
      {#if selection.kind === 'category'}
        <header class="panel__head">
          <button class="panel__back" type="button" onclick={clearSelection}>← overview</button>
          <p class="panel__kind eyebrow">wiki category</p>
          <h2 class="panel__title">{categoryTitle}</h2>
          <p class="panel__blurb voice">{CATEGORY_BLURB[selection.id]}</p>
          <p class="panel__count ev">
            showing {Math.min(PER_CATEGORY, categoryPages.length)} of {categoryPages.length.toLocaleString()} · newest first
          </p>
        </header>
        {#if categoryPages.length === 0}
          <p class="panel__empty ev">
            this category read as empty at {stampLabel}. A loose end, not a hidden link.
          </p>
        {:else}
          <ul class="rows">
            {#each categoryPages.slice(0, PER_CATEGORY) as p (p.path)}
              <li class="row">
                <span class="row__main">
                  <span class="row__title">{p.title}</span>
                  <span class="row__meta ev">{p.dateLabel ? p.dateLabel + ' · ' : ''}{p.path}</span>
                </span>
                <button
                  type="button"
                  class="row__copy"
                  onclick={() => copyReadPrompt(p.path)}
                  title={`Copy: Read the wiki page "${p.path}" from my Workflow connector`}
                >{copiedPath === p.path ? 'copied ✓' : 'copy read prompt'}</button>
              </li>
            {/each}
          </ul>
        {/if}
      {:else if selection.kind === 'universe' && selectedUniverse}
        <header class="panel__head">
          <button class="panel__back" type="button" onclick={clearSelection}>← overview</button>
          <p class="panel__kind eyebrow">universe</p>
          <h2 class="panel__title">{selectedUniverse.id}</h2>
        </header>
        <dl class="facts">
          <div><dt>phase</dt><dd class="ev">{selectedUniverse.phase ?? 'unknown'}</dd></div>
          <div><dt>words</dt><dd class="ev">{(selectedUniverse.word_count ?? 0).toLocaleString()}</dd></div>
          <div>
            <dt>last activity</dt>
            <dd class="ev">{selectedUniverse.last_activity_at ? `${fmtStamp(selectedUniverse.last_activity_at)} · ${fmtRel(selectedUniverse.last_activity_at)}` : 'no activity recorded'}</dd>
          </div>
        </dl>
        <p class="panel__note voice">
          Universes don't cross-bleed; only public ones appear here. Private
          universes live on their keepers' machines, never in mine.
        </p>
      {:else}
        <!-- Overview: legend + how to read the sky. Nothing pre-selected. -->
        <header class="panel__head">
          <p class="panel__kind eyebrow">how to read it</p>
          <h2 class="panel__title">Read it like a night sky.</h2>
        </header>
        <ul class="legend">
          <li><span class="swatch swatch--page"></span><span><strong>pages</strong> — one dot per wiki page, {dotCount.toLocaleString()} of them, sized by how often other pages actually reference them. Hover one to see its title; zoom in and titles appear on their own.</span></li>
          <li><span class="swatch swatch--hub"></span><span><strong>category hubs</strong> — the labelled anchors each page files under. Click one to read its newest pages the way your chatbot would.</span></li>
          <li><span class="swatch swatch--goal"></span><span><strong>goals</strong> — {atlas.publicGoalCount} public goals in ember. Click one to open its page.</span></li>
          <li><span class="swatch swatch--universe"></span><span><strong>universes</strong> — {atlas.universeCount} tailored memory containers in violet. Click one for its phase and last activity.</span></li>
        </ul>
        <p class="panel__note voice">
          Three kinds of lines, honestly drawn: the bright ones are the
          {refCount} real page-to-page references in my memory; the faint
          spokes are filing (a page to its category) and shared-tag clusters
          (pages carrying the same tag). Filing and tags aren't citations, so
          they're drawn like they barely exist.
        </p>
        <p class="panel__foot">
          <Tick href="/commons" label="browse every page in the commons" />
        </p>
        <p class="panel__foot">
          <Tick href={REPO_URL} label="the repo behind all of it" external />
        </p>
      {/if}
    </aside>
  </div>
</section>

<!-- 3 · Mobile list-map (shown only on narrow screens) ───────────────── -->
<section class="listmap" aria-label="The map as a list (mobile)">
  <div class="container">
    <p class="eyebrow">the same map, read top to bottom</p>

    <div class="listmap__group">
      <h3>wiki — {wikiTotal.toLocaleString()} pages</h3>
      <ul class="hublist">
        {#each atlas.nodes.filter((n) => n.kind === 'hub') as h (h.id)}
          <li>
            <button type="button" class="hubrow" onclick={() => h.category && (selection = { kind: 'category', id: h.category })}>
              <span class="hubrow__label">{h.label}</span>
              <span class="hubrow__count ev">{h.sub}</span>
            </button>
          </li>
        {/each}
      </ul>
    </div>

    <div class="listmap__group">
      <h3>goals — {atlas.publicGoalCount} public</h3>
      <ul class="leaflist">
        {#each atlas.nodes.filter((n) => n.kind === 'goal') as g (g.id)}
          <li><a class="leafrow leafrow--goal" href={`/goals/${g.refId}`}>{g.label}</a></li>
        {/each}
      </ul>
    </div>

    <div class="listmap__group">
      <h3>universes — {atlas.universeCount}</h3>
      <ul class="leaflist">
        {#each universesList as u (u.id)}
          <li>
            <button type="button" class="leafrow leafrow--universe" onclick={() => (selection = { kind: 'universe', id: u.id })}>
              <span>{u.id}</span>
              <span class="ev">{u.phase ?? ''}</span>
            </button>
          </li>
        {/each}
      </ul>
    </div>
  </div>
</section>

<style>
  .container { max-width: 1180px; margin: 0 auto; padding-inline: clamp(16px, 4vw, 32px); }

  /* ── Cover ── */
  .cover { padding: clamp(44px, 7vw, 84px) 0 clamp(20px, 3vw, 32px); border-bottom: 1px solid var(--border-1); }
  .cover__title {
    font-family: var(--font-display);
    font-size: clamp(42px, 7.2vw, 88px);
    font-weight: 400;
    line-height: 0.98;
    letter-spacing: -0.035em;
    margin: 12px 0 18px;
  }
  .cover__title em { font-style: italic; color: var(--ember-700); }
  .cover__lede { margin: 0 0 18px; max-width: 70ch; }
  .cover__stamp {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px 12px;
    font-size: 11.5px;
    color: var(--fg-3);
    max-width: none;
    margin: 0;
  }
  .cover__stamp .dot { width: 8px; height: 8px; }
  .cover__err { color: var(--signal-error); font-size: 12px; margin: 10px 0 0; max-width: none; }
  .cover__err a { color: var(--live-700); }
  .refresh {
    margin-left: 4px;
    background: transparent;
    border: 1px solid var(--border-2);
    border-radius: var(--radius-pill);
    color: var(--live-700);
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 5px 13px;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard);
  }
  .refresh:hover:not(:disabled) { border-color: var(--live-600); background: var(--live-100); }
  .refresh:disabled { opacity: 0.6; cursor: default; }

  /* ── Map layout ── */
  .atlas { padding: clamp(20px, 3vw, 36px) 0 clamp(40px, 6vw, 72px); }
  .atlas__shell {
    display: grid;
    grid-template-columns: minmax(0, 1.55fr) minmax(300px, 0.95fr);
    gap: clamp(18px, 2.4vw, 36px);
    align-items: start;
  }

  .map {
    margin: 0;
    background:
      radial-gradient(circle at 50% 46%, rgba(28, 26, 20, 0.04), rgba(28, 26, 20, 0) 60%),
      var(--paper-100);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
    overflow: hidden;
    box-shadow: var(--shadow-sm);
  }
  .map__wrap {
    position: relative;
    width: 100%;
    height: clamp(480px, 64vh, 700px);
  }
  .map__wrap canvas {
    display: block;
    width: 100%;
    height: 100%;
    touch-action: none;
  }
  .map__hint {
    position: absolute;
    left: 14px;
    bottom: 10px;
    margin: 0;
    font-size: 10px;
    color: var(--fg-4);
    pointer-events: none;
    background: color-mix(in srgb, var(--paper-100) 78%, transparent);
    border-radius: var(--radius-pill);
    padding: 3px 10px;
  }

  /* ── Side panel ── */
  .panel {
    position: sticky;
    top: 88px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
    padding: 20px 22px;
    max-height: calc(100vh - 116px);
    overflow-y: auto;
  }
  .panel__head { display: grid; gap: 4px; }
  .panel__back {
    justify-self: start;
    background: transparent;
    border: 1px solid var(--border-1);
    border-radius: var(--radius-pill);
    color: var(--fg-2);
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.08em;
    padding: 4px 11px;
    margin-bottom: 6px;
    transition: border-color var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard);
  }
  .panel__back:hover { border-color: var(--border-2); color: var(--fg-1); }
  .panel__kind { display: block; }
  .panel__title {
    font-family: var(--font-display);
    font-size: clamp(20px, 2.4vw, 26px);
    font-weight: 500;
    letter-spacing: -0.015em;
    line-height: 1.1;
    margin: 2px 0 0;
    overflow-wrap: anywhere;
  }
  .panel__blurb { font-size: 14px; font-style: italic; color: var(--fg-3); margin: 4px 0 0; max-width: none; }
  .panel__count { display: block; font-size: 10.5px; color: var(--fg-3); margin: 8px 0 0; }
  .panel__empty { display: block; font-size: 12.5px; color: var(--fg-3); margin: 14px 0 0; }
  .panel__note { font-size: 14px; line-height: 1.6; color: var(--fg-2); margin: 16px 0 0; max-width: none; }
  .panel__foot { margin: 14px 0 0; }

  .legend { list-style: none; margin: 14px 0 0; padding: 0; display: grid; gap: 12px; }
  .legend li { display: grid; grid-template-columns: 16px minmax(0, 1fr); gap: 11px; align-items: start; font-size: 13.5px; line-height: 1.5; color: var(--fg-2); }
  .legend strong { color: var(--fg-1); font-weight: 600; }
  .swatch { width: 14px; height: 14px; border-radius: 50%; margin-top: 2px; border: 1.6px solid; }
  .swatch--page { background: var(--ink-text-500); border-color: var(--ink-text-700); width: 9px; height: 9px; margin-left: 2px; }
  .swatch--hub { background: var(--paper-50); border-color: var(--ink-text-700); }
  .swatch--goal { background: var(--ember-100); border-color: var(--ember-700); }
  .swatch--universe { background: var(--violet-100); border-color: var(--violet-200); }

  .facts { display: grid; gap: 0; margin: 14px 0 0; }
  .facts div { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 12px; padding: 10px 0; border-top: 1px solid var(--border-1); }
  .facts div:last-child { border-bottom: 1px solid var(--border-1); }
  .facts dt { font-family: var(--font-mono); font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--fg-3); }
  .facts dd { margin: 0; font-size: 12px; color: var(--fg-1); overflow-wrap: anywhere; }

  /* category page rows — reuse the /commons row idiom */
  .rows { list-style: none; margin: 10px 0 0; padding: 0; }
  .row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 12px;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid var(--border-1);
  }
  .row:first-child { border-top: 1px solid var(--border-1); }
  .row__main { min-width: 0; display: grid; gap: 3px; }
  .row__title { font-family: var(--font-voice); font-size: 15px; line-height: 1.3; color: var(--fg-1); overflow-wrap: anywhere; }
  .row__meta { font-size: 10px; color: var(--fg-3); overflow-wrap: anywhere; }
  .row__copy {
    justify-self: start;
    background: transparent;
    border: 1px solid var(--border-2);
    border-radius: var(--radius-pill);
    color: var(--ember-700);
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 9.5px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    padding: 5px 11px;
    white-space: nowrap;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard);
  }
  .row__copy:hover { border-color: var(--ember-700); background: var(--accent-quiet); }
  @media (max-width: 560px) {
    .row { grid-template-columns: 1fr; gap: 6px; }
  }

  /* ── Mobile list-map: hidden on wide screens. ── */
  .listmap { display: none; padding: 0 0 clamp(48px, 8vw, 80px); }
  .listmap__group { margin-top: 28px; }
  .listmap__group h3 {
    font-family: var(--font-mono);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--fg-3);
    margin: 0 0 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border-1);
  }
  .hublist, .leaflist { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
  .hubrow, .leafrow {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    width: 100%;
    text-align: left;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-md);
    color: var(--fg-1);
    cursor: pointer;
    padding: 12px 14px;
    font: inherit;
    text-decoration: none;
  }
  .hubrow:hover, .leafrow:hover { border-color: var(--border-2); }
  .hubrow__label { font-family: var(--font-voice); font-size: 15px; }
  .hubrow__count { color: var(--live-700); font-weight: 600; }
  .leafrow--goal { border-left: 3px solid var(--ember-600); }
  .leafrow--universe { border-left: 3px solid var(--violet-400); }
  .leafrow .ev { color: var(--fg-3); font-size: 10.5px; }

  /* ── Responsive ── */
  @media (max-width: 920px) {
    .atlas__shell { grid-template-columns: 1fr; }
    .panel { position: static; max-height: none; }
  }
  @media (max-width: 620px) {
    .map__wrap { height: clamp(360px, 56vh, 480px); }
    .listmap { display: block; }
  }
</style>
