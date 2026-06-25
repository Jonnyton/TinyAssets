/*
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
*/
"use client";

import * as React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { Simulation } from "d3-force";
import baked from "../../../lib/mcp-snapshot.json";
import { fetchLive, liveToSnapshotShape } from "../../../lib/live";
import type { Snapshot } from "../../../lib/types";
import { fmtCount, fmtRel, fmtStamp, fmtStampStable } from "../../../lib/fmt";
import { useMounted } from "../../../lib/useMounted";
import Tick from "../../../components/Tick";
import {
  buildAtlas,
  CATEGORY_BLURB,
  REPO_URL,
  type CategoryId,
  type Snapshotish,
} from "../../../lib/graph/atlas";
import {
  buildForceGraph,
  createSimulation,
  type FCluster,
  type FNode,
  type ForceGraph,
} from "../../../lib/graph/force";
import styles from "../page.module.css";

const MCP_URL = "https://tinyassets.io/mcp";
const PER_CATEGORY = 30;

type Selection =
  | { kind: "none" }
  | { kind: "category"; id: CategoryId }
  | { kind: "universe"; id: string };

type Transform = { x: number; y: number; k: number };

// Field Notes ink on paper — green stays reserved for liveness.
const FILL: Record<FCluster, string> = {
  patch: "#e0667d",
  plans: "#d8cfb4",
  notes: "#b9a982",
  concepts: "#a98fe0",
  drafts: "#b3a988",
  goals: "#e94560",
  universes: "#a98fe0",
  tags: "#917bb5",
};
const PAPER = "#16150f";
const INK = "#f4f1e7";

function truncate(s: string, max: number): string {
  return s.length <= max ? s : s.slice(0, max - 1).trimEnd() + "…";
}

export default function GraphClient() {
  const router = useRouter();
  const mounted = useMounted();

  // First paint from the baked snapshot; Refresh MCP swaps in a live re-read
  // of the exact same shape, so the whole sky rebuilds against fresh data.
  const [snapshot, setSnapshot] = useState<Snapshot>(baked as unknown as Snapshot);
  const [liveStamp, setLiveStamp] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  const [liveErr, setLiveErr] = useState<string | null>(null);

  const atlas = useMemo(() => buildAtlas(snapshot as unknown as Snapshotish), [snapshot]);
  const [refCount, setRefCount] = useState(0);
  const [dotCount, setDotCount] = useState(0);

  // Selection drives the side panel. Nothing pre-selected.
  const [selection, setSelection] = useState<Selection>({ kind: "none" });

  const selectedCategory = selection.kind === "category" ? selection.id : null;
  const selectedUniverse = useMemo(() => {
    if (selection.kind !== "universe") return null;
    return (snapshot.universes ?? []).find((x) => x.id === selection.id) ?? null;
  }, [selection, snapshot.universes]);
  const categoryPages = selectedCategory ? atlas.pagesByCategory[selectedCategory] : [];
  const categoryTitle = selectedCategory === "patch" ? "patch requests & bugs" : selectedCategory ?? "";

  const clearSelection = useCallback(() => {
    setSelection({ kind: "none" });
  }, []);

  // Live refresh: re-pull, re-stamp, re-settle. Never fakes a baked number.
  const refresh = useCallback(async () => {
    setReading(true);
    try {
      const live = await fetchLive();
      setSnapshot(liveToSnapshotShape(live, baked as unknown as Snapshot));
      setLiveStamp(live.fetchedAt);
      setLiveErr(null);
    } catch (e: any) {
      setLiveErr(e?.message ?? String(e));
    } finally {
      setReading(false);
    }
  }, []);

  // Copyable per-row chatbot read prompt — the honest bridge from /commons.
  const [copiedPath, setCopiedPath] = useState<string | null>(null);
  const copyTimer = useRef<number | null>(null);
  const copyReadPrompt = useCallback(async (path: string) => {
    const clean = path.replace(/\.md$/, "");
    const prompt = `Read the wiki page "${clean}" from my Workflow connector`;
    try {
      await navigator.clipboard.writeText(prompt);
      setCopiedPath(path);
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopiedPath(null), 1600);
    } catch {
      /* clipboard unavailable; the path is still visible to copy by hand */
    }
  }, []);

  useEffect(() => {
    return () => {
      if (copyTimer.current) clearTimeout(copyTimer.current);
    };
  }, []);

  const wikiTotal =
    atlas.counts.patch + atlas.counts.plans + atlas.counts.notes + atlas.counts.concepts + atlas.counts.drafts;
  const stampLabel = liveStamp
    ? `live read ${fmtRel(liveStamp)}`
    : `baked snapshot ${mounted ? fmtStamp(snapshot.fetched_at) : fmtStampStable(snapshot.fetched_at)}`;
  const universesList = snapshot.universes ?? [];

  /* ─────────────────── the canvas force graph ─────────────────── */

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<ForceGraph | null>(null);
  const simRef = useRef<Simulation<FNode, undefined> | null>(null);
  const hoveredRef = useRef<FNode | null>(null);
  const tfRef = useRef<Transform>({ x: 0, y: 0, k: 1 });
  const sizeRef = useRef({ cw: 0, ch: 0, dpr: 1 });
  const rafRef = useRef(0);
  const needsDrawRef = useRef(true);
  const userMovedRef = useRef(false);
  const fittedOnceRef = useRef(false);
  const reducedRef = useRef(false);

  const dragNodeRef = useRef<FNode | null>(null);
  const panningRef = useRef(false);
  const movedPxRef = useRef(0);

  const fitView = useCallback(() => {
    const graph = graphRef.current;
    if (!graph || userMovedRef.current) return;
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const n of graph.nodes) {
      if (n.x! < minX) minX = n.x!;
      if (n.x! > maxX) maxX = n.x!;
      if (n.y! < minY) minY = n.y!;
      if (n.y! > maxY) maxY = n.y!;
    }
    const w = Math.max(200, maxX - minX);
    const h = Math.max(200, maxY - minY);
    const { cw, ch } = sizeRef.current;
    const k = Math.min(1.7, Math.min((cw - 120) / w, (ch - 120) / h));
    tfRef.current = { x: -((minX + maxX) / 2) * k, y: -((minY + maxY) / 2) * k, k };
  }, []);

  const toWorld = useCallback((mx: number, my: number) => {
    const { cw, ch } = sizeRef.current;
    const tf = tfRef.current;
    return { x: (mx - cw / 2 - tf.x) / tf.k, y: (my - ch / 2 - tf.y) / tf.k };
  }, []);

  const nodeAt = useCallback(
    (mx: number, my: number): FNode | null => {
      const graph = graphRef.current;
      if (!graph) return null;
      const p = toWorld(mx, my);
      const tf = tfRef.current;
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
    },
    [toWorld]
  );

  const kick = useCallback((alpha: number) => {
    const sim = simRef.current;
    if (!sim) return;
    if (sim.alpha() < alpha) sim.alpha(alpha);
    needsDrawRef.current = true;
  }, []);

  const draw = useCallback(() => {
    const graph = graphRef.current;
    const canvasEl = canvasRef.current;
    if (!graph || !canvasEl) return;
    const ctx = canvasEl.getContext("2d");
    if (!ctx) return;
    const hovered = hoveredRef.current;
    const tf = tfRef.current;
    const { cw, ch, dpr } = sizeRef.current;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cw, ch);
    ctx.translate(cw / 2 + tf.x, ch / 2 + tf.y);
    ctx.scale(tf.k, tf.k);

    const focus = hovered ? graph.adjacency.get(hovered.id) : null;

    // edges: filing spokes faint, real references brighter
    for (const pass of [0, 1] as const) {
      for (const l of graph.links) {
        const s = l.source as FNode;
        const t = l.target as FNode;
        const isRef = l.kind === "ref";
        if ((pass === 1) !== isRef) continue;
        const inFocus = hovered && (s === hovered || t === hovered);
        if (focus && !inFocus) {
          ctx.strokeStyle = isRef ? "rgba(244,241,231,0.06)" : "rgba(244,241,231,0.03)";
        } else if (inFocus) {
          ctx.strokeStyle = isRef ? "rgba(233,69,96,0.72)" : "rgba(244,241,231,0.32)";
        } else {
          ctx.strokeStyle = isRef ? "rgba(244,241,231,0.2)" : "rgba(244,241,231,0.06)";
        }
        ctx.lineWidth = (isRef ? (inFocus ? 1.5 : 0.9) : 0.55) / Math.sqrt(tf.k);
        ctx.beginPath();
        ctx.moveTo(s.x!, s.y!);
        ctx.lineTo(t.x!, t.y!);
        ctx.stroke();
      }
    }

    // nodes
    for (const n of graph.nodes) {
      const dim = focus ? n !== hovered && !focus.has(n.id) : false;
      ctx.globalAlpha = dim ? 0.13 : 1;
      ctx.beginPath();
      ctx.arc(n.x!, n.y!, n.r, 0, Math.PI * 2);
      if (n.kind === "tag") {
        ctx.fillStyle = PAPER;
        ctx.fill();
        ctx.strokeStyle = FILL[n.cluster];
        ctx.lineWidth = 1.7 / Math.sqrt(tf.k);
        ctx.stroke();
      } else if (n.cluster === "drafts") {
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
        ctx.strokeStyle = "rgba(233,69,96,0.9)";
        ctx.lineWidth = 1.6 / tf.k;
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;

    // labels (screen-constant size; collision-avoided so they never pile up)
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
      align: CanvasTextAlign = "left",
      avoid = false
    ): boolean => {
      ctx.font = `${px / tf.k}px ${font}`;
      ctx.textAlign = align;
      const w = ctx.measureText(text).width;
      const h = px / tf.k;
      const x0 = align === "center" ? x - w / 2 : x;
      const box: [number, number, number, number] = [x0 - 1 / tf.k, y - h, x0 + w + 1 / tf.k, y + h * 0.34];
      if (avoid && overlaps(box)) return false;
      ctx.lineWidth = 3.2 / tf.k;
      ctx.strokeStyle = PAPER;
      ctx.lineJoin = "round";
      ctx.strokeText(text, x, y);
      ctx.fillStyle = fill;
      ctx.fillText(text, x, y);
      placed.push(box);
      return true;
    };

    for (const n of graph.nodes) {
      const dim = focus ? n !== hovered && !focus.has(n.id) : false;
      if (dim) continue;
      if (n.kind === "tag" && n.cluster !== "tags") {
        label(
          `${n.label} · ${n.count === undefined ? "" : fmtCount(n.count)}`,
          n.x!,
          n.y! + n.r + 14 / tf.k,
          10.5,
          "#cfc6ad",
          "'IBM Plex Mono', monospace",
          "center"
        );
      } else if (n.kind === "tag" && (tf.k >= 0.75 || n === hovered)) {
        label(n.label, n.x! + n.r + 4 / tf.k, n.y! + 3 / tf.k, 9, "#a98fe0", "'IBM Plex Mono', monospace", "left", n !== hovered);
      } else if ((n.kind === "goal" || n.kind === "universe") && (tf.k >= 0.55 || n === hovered)) {
        label(
          truncate(n.label, 30),
          n.x! + n.r + 5 / tf.k,
          n.y! + 3 / tf.k,
          n.kind === "goal" ? 10 : 9,
          n.kind === "goal" ? "#f0a6b4" : "#a98fe0",
          n.kind === "goal" ? "'Inter', sans-serif" : "'IBM Plex Mono', monospace",
          "left",
          n !== hovered
        );
      } else if (n.kind === "page" && n !== hovered && tf.k >= 2.3) {
        label(
          truncate(n.label, 34),
          n.x! + n.r + 4 / tf.k,
          n.y! + 2.5 / tf.k,
          8.5,
          "#b9a982",
          "'Inter', sans-serif",
          "left",
          true
        );
      }
    }

    if (hovered && hovered.kind === "page") {
      label(
        truncate(hovered.label, 56),
        hovered.x! + hovered.r + 6 / tf.k,
        hovered.y! + 3 / tf.k,
        11,
        INK,
        "'Inter', sans-serif"
      );
    }
  }, []);

  const activate = useCallback(
    (n: FNode) => {
      if (n.kind === "goal" && n.refId) {
        router.push(`/goal/?id=${n.refId}`);
        return;
      }
      if (n.kind === "universe" && n.refId) {
        setSelection((current) =>
          current.kind === "universe" && current.id === n.refId ? { kind: "none" } : { kind: "universe", id: n.refId! }
        );
        return;
      }
      const cat = n.cluster;
      if (cat === "goals" || cat === "universes") return;
      setSelection((current) => {
        const id = cat as CategoryId;
        return current.kind === "category" && current.id === id ? { kind: "none" } : { kind: "category", id };
      });
    },
    [router]
  );

  const canvasPos = useCallback((e: React.PointerEvent<HTMLCanvasElement> | React.WheelEvent<HTMLCanvasElement>) => {
    const canvasEl = canvasRef.current;
    if (!canvasEl) return { x: 0, y: 0 };
    const r = canvasEl.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }, []);

  const onDown = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      const canvasEl = canvasRef.current;
      if (!canvasEl) return;
      const p = canvasPos(e);
      movedPxRef.current = 0;
      const n = nodeAt(p.x, p.y);
      if (n) {
        dragNodeRef.current = n;
        const w = toWorld(p.x, p.y);
        n.fx = w.x;
        n.fy = w.y;
      } else {
        panningRef.current = true;
      }
      canvasEl.setPointerCapture(e.pointerId);
    },
    [canvasPos, nodeAt, toWorld]
  );

  const onMove = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      const canvasEl = canvasRef.current;
      if (!canvasEl) return;
      const p = canvasPos(e);
      movedPxRef.current += Math.hypot(e.movementX, e.movementY);
      const dragNode = dragNodeRef.current;
      if (dragNode) {
        const w = toWorld(p.x, p.y);
        dragNode.fx = w.x;
        dragNode.fy = w.y;
        userMovedRef.current = true;
        kick(0.12);
        return;
      }
      if (panningRef.current) {
        const tf = tfRef.current;
        tfRef.current = { ...tf, x: tf.x + e.movementX, y: tf.y + e.movementY };
        userMovedRef.current = true;
        needsDrawRef.current = true;
        return;
      }
      const n = nodeAt(p.x, p.y);
      if (n !== hoveredRef.current) {
        hoveredRef.current = n;
        canvasEl.style.cursor = n ? "pointer" : "grab";
        needsDrawRef.current = true;
      }
    },
    [canvasPos, kick, nodeAt, toWorld]
  );

  const onUp = useCallback(
    (_e: React.PointerEvent<HTMLCanvasElement>) => {
      const clicked = movedPxRef.current < 5;
      const dragNode = dragNodeRef.current;
      if (dragNode) {
        dragNodeRef.current = null;
        dragNode.fx = null;
        dragNode.fy = null;
        if (clicked) activate(dragNode);
        else kick(0.1);
        return;
      }
      panningRef.current = false;
      if (clicked) clearSelection();
    },
    [activate, clearSelection, kick]
  );

  const onWheel = useCallback(
    (e: React.WheelEvent<HTMLCanvasElement>) => {
      e.preventDefault();
      const p = canvasPos(e);
      const w = toWorld(p.x, p.y);
      const tf = tfRef.current;
      const { cw, ch } = sizeRef.current;
      const k = Math.min(6, Math.max(0.25, tf.k * Math.exp(-e.deltaY * 0.0016)));
      tfRef.current = { k, x: p.x - cw / 2 - w.x * k, y: p.y - ch / 2 - w.y * k };
      userMovedRef.current = true;
      needsDrawRef.current = true;
    },
    [canvasPos, toWorld]
  );

  useEffect(() => {
    const canvasEl = canvasRef.current;
    const wrapEl = wrapRef.current;
    if (!canvasEl || !wrapEl) return;

    reducedRef.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    sizeRef.current.dpr = Math.min(2, window.devicePixelRatio || 1);

    const resize = () => {
      const { dpr } = sizeRef.current;
      const cw = wrapEl.clientWidth;
      const ch = wrapEl.clientHeight;
      sizeRef.current = { cw, ch, dpr };
      canvasEl.width = Math.round(cw * dpr);
      canvasEl.height = Math.round(ch * dpr);
      if (!userMovedRef.current) fitView();
      needsDrawRef.current = true;
    };

    const ro = new ResizeObserver(resize);
    ro.observe(wrapEl);
    resize();
    canvasEl.style.cursor = "grab";

    const loop = () => {
      rafRef.current = requestAnimationFrame(loop);
      const sim = simRef.current;
      const graph = graphRef.current;
      if (!sim || !graph) return;
      const settling = sim.alpha() > 0.016;
      if (settling && !reducedRef.current) {
        sim.tick(2);
        if (!fittedOnceRef.current || sim.alpha() > 0.3) fitView();
        needsDrawRef.current = true;
      } else if (settling && reducedRef.current) {
        sim.tick(280);
        fitView();
        needsDrawRef.current = true;
      }
      if (!fittedOnceRef.current && !settling) {
        fitView();
        fittedOnceRef.current = true;
        needsDrawRef.current = true;
      }
      if (needsDrawRef.current) {
        needsDrawRef.current = false;
        draw();
      }
    };

    rafRef.current = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(rafRef.current);
      simRef.current?.stop();
      ro.disconnect();
    };
  }, [draw, fitView]);

  useEffect(() => {
    simRef.current?.stop();
    const nextGraph = buildForceGraph(snapshot as unknown as Snapshotish, atlas.pagesByCategory);
    graphRef.current = nextGraph;
    setRefCount(nextGraph.refLinkCount);
    setDotCount(nextGraph.pageCount);
    const nextSim = createSimulation(nextGraph);
    simRef.current = nextSim;
    hoveredRef.current = null;
    fittedOnceRef.current = false;
    if (reducedRef.current) {
      nextSim.tick(280);
      fitView();
      fittedOnceRef.current = true;
    }
    needsDrawRef.current = true;
  }, [atlas.pagesByCategory, fitView, snapshot]);

  return (
    <div className={styles.page}>
      {/* 1 · Hero ──────────────────────────────────────────────────────────── */}
      <section className="cover">
        <div className="container">
          <p className="eyebrow">field notes · the living map</p>
          <h1 className="cover__title">
            My head, <em>seen from above</em>.
          </h1>
          <p className="voice cover__lede">
            Every one of the {fmtCount(wikiTotal)} pages in my memory is a dot in here, settling around its
            category the way notes cluster around tags. Goals burn ember; universes drift violet. The bright lines are
            real page-to-page references — {refCount} of them; the faintest spokes are filing and shared-tag clusters,
            and I'll never dress either up as a citation. Hover to light up a neighbourhood, scroll to zoom, drag
            anything that bothers you.
          </p>
          <p className="cover__stamp ev" aria-live="polite">
            <span className={liveStamp ? "dot live" : "dot"}></span>
            {stampLabel} · {fmtCount(dotCount)} page dots · {atlas.publicGoalCount} goals ·{" "}
            {atlas.universeCount} universes · {refCount} cross-references
            <button type="button" className="refresh" onClick={refresh} disabled={reading} aria-busy={reading}>
              {reading ? "reading…" : "Refresh MCP"}
            </button>
          </p>
          {liveErr && (
            <p className="cover__err ev">
              live read failed — {liveErr}. The same data is reachable directly at{" "}
              <a href={MCP_URL}>{MCP_URL.replace("https://", "")}</a> through any MCP client.
            </p>
          )}
        </div>
      </section>

      {/* 2 · The sky + side panel ──────────────────────────────────────────── */}
      <section className="atlas">
        <div className="container atlas__shell">
          <figure
            className="map"
            aria-label="Force-directed map: every wiki page, goal, and universe as a dot; lines are real references"
          >
            <div className="map__wrap" ref={wrapRef}>
              <canvas
                ref={canvasRef}
                onPointerDown={onDown}
                onPointerMove={onMove}
                onPointerUp={onUp}
                onPointerCancel={onUp}
                onWheel={onWheel}
              ></canvas>
              <p className="map__hint ev">hover to focus · scroll to zoom · drag to pan or move a node</p>
            </div>
          </figure>

          <aside className="panel" aria-live="polite">
            {selection.kind === "category" ? (
              <>
                <header className="panel__head">
                  <button className="panel__back" type="button" onClick={clearSelection}>
                    ← overview
                  </button>
                  <p className="panel__kind eyebrow">wiki category</p>
                  <h2 className="panel__title">{categoryTitle}</h2>
                  <p className="panel__blurb voice">{CATEGORY_BLURB[selection.id]}</p>
                  <p className="panel__count ev">
                    showing {Math.min(PER_CATEGORY, categoryPages.length)} of {fmtCount(categoryPages.length)} ·
                    newest first
                  </p>
                </header>
                {categoryPages.length === 0 ? (
                  <p className="panel__empty ev">
                    this category read as empty at {stampLabel}. A loose end, not a hidden link.
                  </p>
                ) : (
                  <ul className="rows">
                    {categoryPages.slice(0, PER_CATEGORY).map((p) => (
                      <li className="row" key={p.path}>
                        <span className="row__main">
                          <span className="row__title">{p.title}</span>
                          <span className="row__meta ev">
                            {p.dateLabel ? `${p.dateLabel} · ` : ""}
                            {p.path}
                          </span>
                        </span>
                        <button
                          type="button"
                          className="row__copy"
                          onClick={() => copyReadPrompt(p.path)}
                          title={`Copy: Read the wiki page "${p.path}" from my Workflow connector`}
                        >
                          {copiedPath === p.path ? "copied ✓" : "copy read prompt"}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            ) : selection.kind === "universe" && selectedUniverse ? (
              <>
                <header className="panel__head">
                  <button className="panel__back" type="button" onClick={clearSelection}>
                    ← overview
                  </button>
                  <p className="panel__kind eyebrow">universe</p>
                  <h2 className="panel__title">{selectedUniverse.id}</h2>
                </header>
                <dl className="facts">
                  <div>
                    <dt>phase</dt>
                    <dd className="ev">{selectedUniverse.phase ?? "unknown"}</dd>
                  </div>
                  <div>
                    <dt>words</dt>
                    <dd className="ev">{fmtCount(selectedUniverse.word_count ?? 0)}</dd>
                  </div>
                  <div>
                    <dt>last activity</dt>
                    <dd className="ev">
                      {selectedUniverse.last_activity_at
                        ? `${fmtStamp(selectedUniverse.last_activity_at)} · ${fmtRel(selectedUniverse.last_activity_at)}`
                        : "no activity recorded"}
                    </dd>
                  </div>
                </dl>
                <p className="panel__note voice">
                  Universes don't cross-bleed; only public ones appear here. Private universes live on their keepers'
                  machines, never in mine.
                </p>
              </>
            ) : (
              <>
                {/* Overview: legend + how to read the sky. Nothing pre-selected. */}
                <header className="panel__head">
                  <p className="panel__kind eyebrow">how to read it</p>
                  <h2 className="panel__title">Read it like a night sky.</h2>
                </header>
                <ul className="legend">
                  <li>
                    <span className="swatch swatch--page"></span>
                    <span>
                      <strong>pages</strong> — one dot per wiki page, {fmtCount(dotCount)} of them, sized by how
                      often other pages actually reference them. Hover one to see its title; zoom in and titles appear
                      on their own.
                    </span>
                  </li>
                  <li>
                    <span className="swatch swatch--hub"></span>
                    <span>
                      <strong>category hubs</strong> — the labelled anchors each page files under. Click one to read
                      its newest pages the way your chatbot would.
                    </span>
                  </li>
                  <li>
                    <span className="swatch swatch--goal"></span>
                    <span>
                      <strong>goals</strong> — {atlas.publicGoalCount} public goals in ember. Click one to open its
                      page.
                    </span>
                  </li>
                  <li>
                    <span className="swatch swatch--universe"></span>
                    <span>
                      <strong>universes</strong> — {atlas.universeCount} tailored memory containers in violet. Click one
                      for its phase and last activity.
                    </span>
                  </li>
                </ul>
                <p className="panel__note voice">
                  Three kinds of lines, honestly drawn: the bright ones are the {refCount} real page-to-page references
                  in my memory; the faint spokes are filing (a page to its category) and shared-tag clusters (pages
                  carrying the same tag). Filing and tags aren't citations, so they're drawn like they barely exist.
                </p>
                <p className="panel__foot">
                  <Tick href="/commons" label="browse every page in the commons" />
                </p>
                <p className="panel__foot">
                  <Tick href={REPO_URL} label="the repo behind all of it" external />
                </p>
              </>
            )}
          </aside>
        </div>
      </section>

      {/* 3 · Mobile list-map (shown only on narrow screens) ───────────────── */}
      <section className="listmap" aria-label="The map as a list (mobile)">
        <div className="container">
          <p className="eyebrow">the same map, read top to bottom</p>

          <div className="listmap__group">
            <h3>wiki — {fmtCount(wikiTotal)} pages</h3>
            <ul className="hublist">
              {atlas.nodes
                .filter((n) => n.kind === "hub")
                .map((h) => (
                  <li key={h.id}>
                    <button
                      type="button"
                      className="hubrow"
                      onClick={() => h.category && setSelection({ kind: "category", id: h.category })}
                    >
                      <span className="hubrow__label">{h.label}</span>
                      <span className="hubrow__count ev">{h.sub}</span>
                    </button>
                  </li>
                ))}
            </ul>
          </div>

          <div className="listmap__group">
            <h3>goals — {atlas.publicGoalCount} public</h3>
            <ul className="leaflist">
              {atlas.nodes
                .filter((n) => n.kind === "goal")
                .map((g) => (
                  <li key={g.id}>
                    <a className="leafrow leafrow--goal" href={`/goal/?id=${g.refId}`}>
                      {g.label}
                    </a>
                  </li>
                ))}
            </ul>
          </div>

          <div className="listmap__group">
            <h3>universes — {atlas.universeCount}</h3>
            <ul className="leaflist">
              {universesList.map((u) => (
                <li key={u.id}>
                  <button
                    type="button"
                    className="leafrow leafrow--universe"
                    onClick={() => setSelection({ kind: "universe", id: u.id })}
                  >
                    <span>{u.id}</span>
                    <span className="ev">{u.phase ?? ""}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
}
