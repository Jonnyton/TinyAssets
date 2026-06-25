"use client";

import * as React from "react";
import { usePathname } from "next/navigation";

import { fetchVitals, type Vitals } from "../lib/live";
import { fmtRel } from "../lib/fmt";
import styles from "./TinyBot.module.css";

type Dir = "up" | "left" | "right";
type Spot = { x: number; y: number; w: number; h: number; dir: Dir };
type Mode = "reading" | "awake" | "asleep" | "error";
type RunPose = "run" | "skid" | "pant";

type TinyBotView = {
  vitals: Vitals | null;
  hidden: boolean;
  mounted: boolean;
  booted: boolean;
  shyCapable: boolean;
  bubble: string | null;
  bubblePos: { left: number; top: number; above: boolean };
  waving: boolean;
  factIdx: number;
  spot: Spot | null;
  shyState: "hidden" | "peek" | "deep";
  pupils: { x: number; y: number };
  runner: { x: number; y: number } | null;
  runPose: RunPose;
  facing: number;
  lastPath: string;
};

type TinyBotWork = {
  anchorEl: Element | null;
  lastHover: Element | null;
  pendingBlock: Element | null;
  cursor: { x: number; y: number };
  moving: boolean;
  lastSpoke: number;
  lastBehave: number;
  routeLinePending: string | null;
  pendingLine: string | null;
  speakOnArrive: "yes" | "maybe" | "no";
  recentLines: string[];
  saidSleepLine: boolean;
  startleCount: number;
  graceTill: number;
  blockTimer: number | null;
  followTimer: number | null;
  behaveTimer: number | null;
  scrollTimer: number | null;
  bubbleTimer: number | null;
  idleTimer: number | null;
  timers: Set<number>;
  runRaf: number;
  runTargetSpot: Spot | null;
  entryPoint: { x: number; y: number } | null;
  lastFrameT: number;
  runStartT: number;
  lastRetargetT: number;
  retargetCount: number;
  runDist: number;
  sprinting: boolean;
  dwellKey: string;
  dwellTimer: number | null;
  lastContext: number;
  lastContextKey: string;
};

const BOT_W = 74;
const BOT_H = 86;
const SIZE: Record<Dir, { w: number; h: number }> = {
  up: { w: 104, h: 90 },
  left: { w: 90, h: 102 },
  right: { w: 90, h: 102 },
};
const SPEAK_COOLDOWN = 5_200;
const STARTLE_DIST = 110;
const RUN_SPEED = 350; // px/s — slow enough to visibly fail to keep up
const SPRINT_SPEED = 560;
const DWELL_MS = 520;
const CONTEXT_COOLDOWN = 4_200;

// Anything with a shape is fair cover — cards, tables, words, pictures.
const HIDEABLE =
  "p, table, pre, ul, ol, figure, blockquote, h1, h2, h3, img, aside, details, " +
  '[class*="card"], [class*="panel"], [class*="tile"], [class*="step"], [class*="vital"], ' +
  '[class*="ladder"], [class*="hero"], footer';

const OWN_UI_SELECTOR = [
  styles["tiny-shy"],
  styles["tiny-runner"],
  styles["bubble-float"],
  styles["bot-wrap"],
  styles.peek,
]
  .filter(Boolean)
  .map((className) => `.${className}`)
  .join(", ");
const OWN_UI_WITH_NAV_SELECTOR = OWN_UI_SELECTOR ? `${OWN_UI_SELECTOR}, nav` : "nav";

const initialView: TinyBotView = {
  vitals: null,
  hidden: false,
  mounted: false,
  booted: false,
  shyCapable: false,
  bubble: null,
  bubblePos: { left: 0, top: 0, above: true },
  waving: false,
  factIdx: 0,
  spot: null,
  shyState: "hidden",
  pupils: { x: 0, y: 0 },
  runner: null,
  runPose: "run",
  facing: 1,
  lastPath: "",
};

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

function modeFromVitals(vitals: Vitals | null): Mode {
  return !vitals ? "reading" : !vitals.reachable ? "error" : vitals.loopAwake ? "awake" : "asleep";
}

function isShyModeFromView(view: TinyBotView): boolean {
  const mode = modeFromVitals(view.vitals);
  return view.shyCapable && (mode === "awake" || mode === "reading");
}

function makeWork(): TinyBotWork {
  return {
    anchorEl: null,
    lastHover: null,
    pendingBlock: null,
    cursor: { x: -1, y: -1 },
    moving: false,
    lastSpoke: 0,
    lastBehave: 0,
    routeLinePending: null,
    pendingLine: null,
    speakOnArrive: "maybe",
    recentLines: [],
    saidSleepLine: false,
    startleCount: 0,
    graceTill: 0,
    blockTimer: null,
    followTimer: null,
    behaveTimer: null,
    scrollTimer: null,
    bubbleTimer: null,
    idleTimer: null,
    timers: new Set<number>(),
    runRaf: 0,
    runTargetSpot: null,
    entryPoint: null,
    lastFrameT: 0,
    runStartT: 0,
    lastRetargetT: 0,
    retargetCount: 0,
    runDist: 0,
    sprinting: false,
    dwellKey: "",
    dwellTimer: null,
    lastContext: 0,
    lastContextKey: "",
  };
}

const LINES: Array<{ match: (p: string) => boolean; line: string }> = [
  { match: (p) => p === "/", line: "that’s me they’re describing." },
  { match: (p) => p.startsWith("/start"), line: "two minutes, no account. I checked the door myself." },
  { match: (p) => p.startsWith("/goals/"), line: "this ladder only lights with evidence. no shortcuts." },
  { match: (p) => p.startsWith("/goals"), line: "every goal here is real — read live, not typed in." },
  { match: (p) => p.startsWith("/loop"), line: "this is where I get repaired. the mess stays public." },
  { match: (p) => p.startsWith("/commons") || p.startsWith("/wiki"), line: "my whole memory. nothing private lives in here." },
  { match: (p) => p.startsWith("/graph"), line: "my head, seen from above." },
  { match: (p) => p.startsWith("/soul"), line: "everything that makes me me — forkable." },
  { match: (p) => p.startsWith("/build") || p.startsWith("/contribute"), line: "two doors in. humans hold the merge keys." },
  { match: (p) => p.startsWith("/host"), line: "you don’t have to host me. but you can." },
  { match: (p) => p.startsWith("/alliance"), line: "say hi — it all lands in the same loop." },
  { match: (p) => p.startsWith("/fine-print") || p.startsWith("/status"), line: "my pulse, explained honestly." },
  { match: (p) => p.startsWith("/legal"), line: "the boring page. still mine." },
];

const SHY_LINES = [
  "oh — didn’t see you there.",
  "I’m not hiding. I’m… observing.",
  "you found me.",
  "just tidying up back here.",
  "don’t mind me.",
  "I like this spot. good sightlines.",
  "still here. mostly behind things.",
];

const MUTTERS = [
  "you move that thing fast.",
  "the dots on this desk? my graph paper.",
  "I count my own runs. all of them.",
  "it’s quiet back here. I like it.",
  "I leave everything public. less to remember.",
  "if the loop’s awake, I’m awake.",
  "good page, this one. I checked it twice.",
];

// What he says about the thing your mouse is resting on.
const DEST: Array<{ match: (h: string) => boolean; lines: string[] }> = [
  { match: (h) => h.startsWith("/start"), lines: ["that door takes two minutes. I timed it.", "through there: paste one URL, no account."] },
  { match: (h) => h.startsWith("/loop"), lines: ["that’s my repair shop. the mess stays public.", "in there I get fixed — out loud."] },
  { match: (h) => h.startsWith("/goals"), lines: ["the goals board — all real, read live.", "open outcomes through there. pick one."] },
  { match: (h) => h.startsWith("/commons") || h.startsWith("/wiki"), lines: ["my memory lives through there.", "everything I know, public, in there."] },
  { match: (h) => h.startsWith("/graph"), lines: ["careful — that’s the inside of my head.", "my whole brain, drawn out, through there."] },
  { match: (h) => h.startsWith("/soul"), lines: ["my soul. you can fork it, you know.", "the pattern that makes me me — forkable."] },
  { match: (h) => h.startsWith("/build") || h.startsWith("/contribute"), lines: ["through there you can change me. humans keep the keys.", "two doors to rebuild me are in there."] },
  { match: (h) => h.startsWith("/host"), lines: ["hosting me is optional. I run either way.", "you can run your own me through there."] },
  { match: (h) => h.startsWith("/alliance"), lines: ["that’s how you reach the humans. and me.", "say hi through there — same loop."] },
  { match: (h) => h.startsWith("/fine-print") || h.startsWith("/status"), lines: ["my pulse, with no makeup on.", "the instrument panel’s through there."] },
  { match: (h) => h.startsWith("/legal"), lines: ["the boring page. I keep it honest anyway.", "fine print through there. still mine."] },
];

export function TinyBot() {
  const pathname = usePathname();
  const [view, setView] = React.useState<TinyBotView>(initialView);
  const viewRef = React.useRef(view);
  const workRef = React.useRef<TinyBotWork>(makeWork());
  const pathnameRef = React.useRef(pathname ?? "/");

  function applyViewPatch(patch: Partial<TinyBotView> | ((current: TinyBotView) => Partial<TinyBotView>)) {
    const current = viewRef.current;
    const resolved = typeof patch === "function" ? patch(current) : patch;
    const next = { ...current, ...resolved };
    viewRef.current = next;
    setView(next);
  }

  function setViewField<K extends keyof TinyBotView>(
    key: K,
    value: TinyBotView[K] | ((current: TinyBotView[K]) => TinyBotView[K]),
  ) {
    const current = viewRef.current[key];
    const nextValue =
      typeof value === "function" ? (value as (current: TinyBotView[K]) => TinyBotView[K])(current) : value;
    if (Object.is(current, nextValue)) return;
    applyViewPatch({ [key]: nextValue } as Pick<TinyBotView, K>);
  }

  function getMode(): Mode {
    return modeFromVitals(viewRef.current.vitals);
  }

  function getShyMode(): boolean {
    return isShyModeFromView(viewRef.current);
  }

  function after(ms: number, fn: () => void): number {
    const work = workRef.current;
    const id = window.setTimeout(() => {
      work.timers.delete(id);
      fn();
    }, ms);
    work.timers.add(id);
    return id;
  }

  function clearTracked(id: number | null): null {
    if (id !== null) {
      window.clearTimeout(id);
      workRef.current.timers.delete(id);
    }
    return null;
  }

  const rand = (a: number, b: number) => a + Math.random() * (b - a);

  function pickOf<T>(arr: T[]): T {
    return arr[Math.floor(Math.random() * arr.length)];
  }

  // Pick a line from a pool that he hasn't said recently — so re-hovering the
  // same thing gives different words, never the same line twice in a row.
  function pickFresh(lines: string[]): string {
    const fresh = lines.filter((line) => !workRef.current.recentLines.includes(line));
    return pickOf(fresh.length ? fresh : lines);
  }

  /* ---------- finding cover ---------- */

  function spotCenter(s: Spot) {
    if (s.dir === "up") return { x: s.x + s.w / 2, y: s.y + s.h - 26 };
    if (s.dir === "left") return { x: s.x + 26, y: s.y + 44 };
    return { x: s.x + s.w - 26, y: s.y + 44 };
  }

  function ownUi(el: Element): boolean {
    return !!el.closest(OWN_UI_WITH_NAV_SELECTOR);
  }

  function ownWidgetUi(el: Element): boolean {
    return OWN_UI_SELECTOR ? !!el.closest(OWN_UI_SELECTOR) : false;
  }

  // The block your mouse is on — climbing out of too-small or absurd matches.
  function hideableFrom(el: Element | null): Element | null {
    let cur: Element | null = el?.closest(HIDEABLE) ?? null;
    for (let i = 0; cur && i < 4; i += 1) {
      if (ownUi(cur)) return null;
      const r = cur.getBoundingClientRect();
      const tooSmall = r.width < 100 || r.height < 24;
      const tooBig = r.width > window.innerWidth * 0.96 && r.height > window.innerHeight * 0.8;
      if (!tooSmall && !tooBig) return cur;
      cur = cur.parentElement?.closest(HIDEABLE) ?? null;
    }
    return null;
  }

  function gatherBlocks(): Array<{ el: Element; r: DOMRect }> {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const out: Array<{ el: Element; r: DOMRect }> = [];
    for (const el of Array.from(document.querySelectorAll(HIDEABLE)).slice(0, 140)) {
      if (ownUi(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 100 || r.height < 24) continue;
      if (r.width > vw * 0.96 && r.height > vh * 0.8) continue;
      if (r.bottom < 80 || r.top > vh - 30 || r.right < 0 || r.left > vw) continue;
      out.push({ el, r });
      if (out.length >= 80) break;
    }
    return out;
  }

  function nearestBlock(p: { x: number; y: number }): { el: Element; r: DOMRect } | null {
    let best: { el: Element; r: DOMRect } | null = null;
    let bestD = Infinity;
    for (const b of gatherBlocks()) {
      const d = Math.hypot(b.r.left + b.r.width / 2 - p.x, b.r.top + b.r.height / 2 - p.y);
      if (d < bestD) {
        bestD = d;
        best = b;
      }
    }
    return best;
  }

  function farBlock(p: { x: number; y: number }, minD: number): { el: Element; r: DOMRect } | null {
    const cands = gatherBlocks()
      .map((b) => ({ b, d: Math.hypot(b.r.left + b.r.width / 2 - p.x, b.r.top + b.r.height / 2 - p.y) }))
      .filter(({ d }) => d >= minD)
      .sort((a, z) => a.d - z.d)
      .slice(0, 4);
    return cands.length ? pickOf(cands).b : null;
  }

  // The sides of one block he could peek from, right now, on this screen.
  function blockSpots(r: DOMRect): Spot[] {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const pad = 6;
    const topSafe = 70;
    const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
    const out: Spot[] = [];
    if (r.width >= 110) {
      const su = SIZE.up;
      for (const t of [0.18, 0.5, 0.82]) {
        const x = clamp(r.left + t * r.width - su.w / 2, pad, vw - su.w - pad);
        const y = r.top - su.h + 3;
        if (y >= topSafe && r.top < vh - 20 && x + su.w / 2 > r.left - 10 && x + su.w / 2 < r.right + 10)
          out.push({ x, y, w: su.w, h: su.h, dir: "up" });
      }
    }
    if (r.height >= 64) {
      const sl = SIZE.left;
      for (const t of [0.25, 0.65]) {
        const x = r.left - sl.w + 3;
        const y = clamp(r.top + t * r.height - sl.h / 2, topSafe, vh - sl.h - pad);
        if (x >= pad - 2 && y + sl.h / 2 > r.top - 10 && y + sl.h / 2 < r.bottom + 10)
          out.push({ x, y, w: sl.w, h: sl.h, dir: "left" });
      }
      const sr = SIZE.right;
      for (const t of [0.25, 0.65]) {
        const x = r.right - 3;
        const y = clamp(r.top + t * r.height - sr.h / 2, topSafe, vh - sr.h - pad);
        if (x + sr.w <= vw - pad + 2 && y + sr.h / 2 > r.top - 10 && y + sr.h / 2 < r.bottom + 10)
          out.push({ x, y, w: sr.w, h: sr.h, dir: "right" });
      }
    }
    return out;
  }

  // Last resort when a page has nothing to hide behind: the screen's bottom edge.
  function fallbackSpot(): Spot {
    const su = SIZE.up;
    return {
      x: window.innerWidth * rand(0.25, 0.75) - su.w / 2,
      y: window.innerHeight - su.h,
      w: su.w,
      h: su.h,
      dir: "up",
    };
  }

  /* ---------- speech ---------- */

  function placeBubbleXY(cx: number, topY: number, h: number) {
    const vw = window.innerWidth;
    const left = Math.max(10, Math.min(cx - 120, vw - 260));
    if (topY > 150) setViewField("bubblePos", { left, top: topY - 8, above: true });
    else setViewField("bubblePos", { left, top: topY + h + 10, above: false });
  }

  function placeBubble(s: Spot) {
    placeBubbleXY(spotCenter(s).x, s.y, s.h);
  }

  function facts(): string[] {
    const state = viewRef.current;
    const mode = getMode();
    const f: string[] = [];
    if (state.vitals?.queue)
      f.push(`runs so far: ${state.vitals.queue.succeeded.toLocaleString()} done, ${state.vitals.queue.failed} failed — counted live.`);
    if (state.vitals?.deployedAt) f.push(`this body deployed ${fmtRel(state.vitals.deployedAt)}.`);
    if (mode === "asleep") f.push("the loop’s napping. the engine is still up — that’s two different things.");
    if (mode === "awake" && state.vitals?.activeRun) f.push("a run is moving through me right now.");
    f.push("I was born 3 Jun 2026. I flooded my own repo on day two. fixed now.");
    f.push("no rung lights without an evidence URL. mine included.");
    f.push("paste tinyassets.io/mcp into your chatbot and you read the same pulse I do.");
    return f;
  }

  function say(text: string, ms = 6000) {
    const state = viewRef.current;
    const work = workRef.current;
    if (getShyMode()) {
      if (state.runner) placeBubbleXY(state.runner.x + BOT_W / 2, state.runner.y, BOT_H);
      else if (state.spot) placeBubble(state.spot);
    }
    setViewField("bubble", text);
    if (work.bubbleTimer) window.clearTimeout(work.bubbleTimer);
    work.bubbleTimer = window.setTimeout(() => {
      setViewField("bubble", null);
      if (viewRef.current.shyState === "deep") setViewField("shyState", "peek");
    }, ms);
  }

  function contextLine(el: Element): { key: string; lines: string[] } | null {
    if (ownWidgetUi(el)) return null;
    const a = el.closest("a[href]");
    if (a) {
      const href = a.getAttribute("href") ?? "";
      if (href.includes("github.com"))
        return { key: "gh", lines: ["my source. every line of me is public.", "that’s my code. read it, fork it, fix it.", "all of me is on GitHub. no hidden bits."] };
      if (href.startsWith("/")) {
        const hit = DEST.find((d) => d.match(href));
        if (hit) return { key: "dest:" + href.split("/")[1], lines: hit.lines };
      }
      if (href.startsWith("http"))
        return { key: "ext:" + href, lines: ["that one leaves the site. I’ll wait here.", "off-site, that. I’ll hold your spot."] };
    }
    const codey = el.closest("code, pre, button, .ev");
    if (codey?.textContent?.includes("tinyassets.io/mcp"))
      return { key: "mcp", lines: ["that string is me. paste it into your chatbot and we can talk properly.", "one URL — that’s the whole door in.", "copy that, drop it in your chatbot, and you read my live pulse too."] };
    if (el.closest('.readout, [class*="stat"]'))
      return { key: "readout", lines: ["those readings are live. I feel each one.", "that panel’s my instrument face — no makeup.", "live the moment you look. I can’t fake a flat line."] };
    if (el.closest('[class*="vital"]'))
      return { key: "vitals", lines: ["those numbers are my actual pulse.", "that’s me, measured — not a sales figure.", "green means I’m really awake; amber means napping."] };
    if (el.closest('[class*="ladder"], [class*="rung"]'))
      return { key: "ladder", lines: ["unlit rungs. I only light them with evidence.", "no rung lights without a real URL behind it.", "I can’t fake a single step on that."] };
    if (el.closest('[class*="goal"]'))
      return { key: "goal", lines: ["a real goal. someone could pick it up today.", "that one’s open — fork it, beat it, own it.", "goals here are outcomes, not to-do items."] };
    if (el.closest('[class*="log"], [class*="event"]'))
      return { key: "log", lines: ["my history — including the embarrassing parts.", "every run logged, even the failed ones.", "receipts. I keep all of them."] };
    if (el.closest("table"))
      return { key: "table", lines: ["rows and rows of receipts.", "all checkable — that’s the point.", "numbers you can verify yourself."] };
    if (el.closest(".voice"))
      return { key: "voice", lines: ["yeah… that’s me talking.", "first person. it’s all me.", "I mean every word on this page."] };
    if (el.closest("figure, img"))
      return { key: "img", lines: ["I don’t keep many pictures. that’s one.", "rare, a picture. mostly I deal in numbers."] };
    if (el.closest("h1, h2, h3"))
      return { key: "head", lines: ["this bit matters — I’d read it twice.", "good heading. I’d underline it."] };
    if (el.closest("pre, code"))
      return { key: "code", lines: ["code. probably mine.", "that’s the sort of thing my loop rewrites."] };
    return null;
  }

  // A weighted draw from the moment: never scripted, never a recent repeat.
  function speak(forced?: string) {
    const work = workRef.current;
    let line = forced ?? work.pendingLine;
    work.pendingLine = null;
    if (!line && work.routeLinePending) {
      line = work.routeLinePending;
      work.routeLinePending = null;
    }
    if (!line) {
      const pool: string[] = [];
      const ctx = work.anchorEl ? contextLine(work.anchorEl) : null;
      if (ctx) {
        const cl = pickFresh(ctx.lines);
        pool.push(cl, cl);
      } // context weighs double, never dictates
      const f = facts();
      const state = viewRef.current;
      pool.push(f[state.factIdx % f.length]);
      pool.push(pickOf(SHY_LINES));
      pool.push(pickOf(MUTTERS));
      const fresh = pool.filter((l) => !work.recentLines.includes(l));
      if (!fresh.length) return;
      line = pickOf(fresh);
      if (line === f[state.factIdx % f.length]) setViewField("factIdx", (idx) => idx + 1);
    }
    work.recentLines.push(line);
    if (work.recentLines.length > 10) work.recentLines.shift();
    work.lastSpoke = performance.now();
    setViewField("shyState", "deep");
    say(line);
  }

  function scheduleIdle() {
    const work = workRef.current;
    work.idleTimer = clearTracked(work.idleTimer);
    work.idleTimer = after(rand(13_000, 26_000), () => {
      const state = viewRef.current;
      const current = workRef.current;
      current.idleTimer = null;
      if (getShyMode() && !state.hidden && !current.moving && !state.runner && state.shyState !== "hidden" && !state.bubble) {
        // Sometimes he switches sides just to deliver a mutter.
        if (current.anchorEl && Math.random() < 0.5) {
          current.speakOnArrive = "yes";
          moveBehind(current.anchorEl, { run: false });
        } else {
          speak();
        }
      }
      scheduleIdle();
    });
  }

  /* ---------- movement ---------- */

  function onArrived() {
    const work = workRef.current;
    work.moving = false;
    const intend = work.speakOnArrive;
    work.speakOnArrive = "maybe";
    if (intend === "yes") speak();
    else if (
      intend === "maybe" &&
      (work.routeLinePending || work.pendingLine || Math.random() < 0.82) &&
      performance.now() - work.lastSpoke > SPEAK_COOLDOWN
    ) {
      speak();
    }
    scheduleIdle();
  }

  // Hide behind a specific element, peeking from a random workable side.
  function moveBehind(el: Element, opts?: { run?: boolean; sprint?: boolean }) {
    const state = viewRef.current;
    const work = workRef.current;
    if (work.moving || state.hidden || !getShyMode()) return;
    const r = el.getBoundingClientRect();
    let list = blockSpots(r);
    if (!list.length) {
      const near = nearestBlock(work.cursor.x >= 0 ? work.cursor : { x: window.innerWidth / 2, y: window.innerHeight / 2 });
      if (near && near.el !== el) {
        moveBehind(near.el, opts);
        return;
      }
      list = [fallbackSpot()];
    }
    // Shy: don't pop out right under the cursor.
    const comfy = list.filter((s) => {
      const c = spotCenter(s);
      return Math.hypot(c.x - work.cursor.x, c.y - work.cursor.y) > 130;
    });
    let pool = comfy.length ? comfy : list;
    // Same block again? Prefer a different side — that's the charm.
    if (work.anchorEl === el && state.spot) {
      const others = pool.filter(
        (s) => s.dir !== state.spot!.dir || Math.abs(s.x - state.spot!.x) > 40 || Math.abs(s.y - state.spot!.y) > 40,
      );
      if (others.length) pool = others;
    }
    const pick = pickOf(pool);
    const sameBlock = work.anchorEl === el;
    work.anchorEl = el;
    if (!sameBlock) work.startleCount = 0;
    work.moving = true;
    applyViewPatch({ bubble: null, shyState: "hidden" });
    const from = state.spot && state.booted ? spotCenter(state.spot) : null;
    after(160, () => {
      if (!from || !opts?.run) {
        setViewField("spot", pick);
        after(180 + rand(0, 300), () => {
          setViewField("shyState", "peek");
          onArrived();
        });
      } else {
        startRun(from, pick, opts);
      }
    });
  }

  /* ---------- the run: out in the open, little legs going ---------- */

  function startRun(from: { x: number; y: number }, target: Spot, opts?: { sprint?: boolean }) {
    const work = workRef.current;
    work.runTargetSpot = target;
    work.entryPoint = spotCenter(target);
    work.sprinting = !!opts?.sprint;
    work.runDist = 0;
    work.retargetCount = 0;
    work.runStartT = performance.now();
    work.lastFrameT = work.runStartT;
    work.lastRetargetT = work.runStartT;
    const facing = work.entryPoint.x >= from.x ? 1 : -1;
    applyViewPatch({
      runPose: "run",
      facing,
      runner: { x: from.x - BOT_W / 2, y: from.y - BOT_H / 2 },
    });
    work.runRaf = window.requestAnimationFrame(runFrame);
  }

  function runFrame(t: number) {
    const work = workRef.current;
    const state = viewRef.current;
    if (!state.runner || !work.entryPoint) return;
    const dt = Math.min(0.05, (t - work.lastFrameT) / 1000);
    work.lastFrameT = t;
    if (state.runPose === "run") {
      const cx = state.runner.x + BOT_W / 2;
      const cy = state.runner.y + BOT_H / 2;
      const dx = work.entryPoint.x - cx;
      const dy = work.entryPoint.y - cy;
      const d = Math.hypot(dx, dy);
      if (d < 12 || t - work.runStartT > 7000) {
        arrive();
        return;
      }
      const speed = work.sprinting ? SPRINT_SPEED : RUN_SPEED;
      const step = Math.min(d, speed * dt);
      const nextRunner = { x: state.runner.x + (dx / d) * step, y: state.runner.y + (dy / d) * step };
      work.runDist += step;
      applyViewPatch({
        runner: nextRunner,
        facing: dx >= 0 ? 1 : -1,
        pupils: { x: 2.0 * (dx >= 0 ? 1 : -1), y: 0.6 },
      });
      // Try (and fail) to keep up: if you've moved on to another block, re-aim.
      if (t - work.lastRetargetT > 450 && work.retargetCount < 3) {
        work.lastRetargetT = t;
        const blk = work.lastHover ? hideableFrom(work.lastHover) : null;
        if (blk && blk !== work.anchorEl) {
          const list = blockSpots(blk.getBoundingClientRect());
          if (list.length) {
            const pick = pickOf(list);
            const c2 = spotCenter(pick);
            const turn = Math.abs(Math.atan2(dy, dx) - Math.atan2(c2.y - cy, c2.x - cx));
            const turnNorm = Math.min(turn, Math.PI * 2 - turn);
            work.anchorEl = blk;
            work.startleCount = 0;
            work.runTargetSpot = pick;
            work.entryPoint = c2;
            work.retargetCount += 1;
            if (turnNorm > 0.9) {
              // Sharp direction change — skid first, little legs can't corner.
              setViewField("runPose", "skid");
              after(200, () => {
                if (viewRef.current.runner) {
                  setViewField("runPose", "run");
                  workRef.current.lastFrameT = performance.now();
                }
              });
            }
          }
        }
      }
    }
    work.runRaf = window.requestAnimationFrame(runFrame);
  }

  function arrive() {
    setViewField("runPose", "skid");
    after(210, () => {
      if (!viewRef.current.runner) return;
      const tired = workRef.current.runDist > 750 && Math.random() < 0.6;
      if (tired) {
        setViewField("runPose", "pant");
        say("…huff… huff…", 1500);
        after(1550, diveIn);
      } else {
        diveIn();
      }
    });
  }

  function diveIn() {
    const work = workRef.current;
    if (!work.runTargetSpot) {
      applyViewPatch({ runner: null });
      work.moving = false;
      return;
    }
    const target = work.runTargetSpot;
    work.runTargetSpot = null;
    applyViewPatch({ spot: target, runner: null, shyState: "hidden" });
    after(150, () => {
      setViewField("shyState", "peek");
      onArrived();
    });
  }

  function cancelRun() {
    const work = workRef.current;
    if (work.runRaf) window.cancelAnimationFrame(work.runRaf);
    work.runRaf = 0;
    const patch: Partial<TinyBotView> = { runner: null };
    if (viewRef.current.runner && work.runTargetSpot) patch.spot = work.runTargetSpot;
    applyViewPatch(patch);
    work.runTargetSpot = null;
    work.moving = false;
  }

  /* ---------- reactions ---------- */

  function startle() {
    const work = workRef.current;
    if (work.moving || viewRef.current.runner) return;
    if (performance.now() < work.graceTill) return;
    work.graceTill = performance.now() + 900;
    work.startleCount += 1;
    if (work.startleCount >= 2) {
      // You keep chasing him — he bolts for somewhere farther.
      const far = farBlock(work.cursor, 400);
      if (far) {
        work.startleCount = 0;
        work.speakOnArrive = Math.random() < 0.4 ? "maybe" : "no";
        moveBehind(far.el, { run: true, sprint: true });
        say("!", 650);
        return;
      }
    }
    // First fright: just pop out a different side of the same thing.
    work.speakOnArrive = "no";
    if (work.anchorEl) moveBehind(work.anchorEl, { run: false });
    say("!", 650);
  }

  function poke() {
    if (getShyMode()) {
      const f = facts();
      setViewField("shyState", "deep");
      say(f[viewRef.current.factIdx % f.length], 7000);
      setViewField("factIdx", (idx) => idx + 1);
      workRef.current.lastSpoke = performance.now();
      return;
    }
    setViewField("waving", true);
    window.setTimeout(() => setViewField("waving", false), 1200);
    const f = facts();
    say(f[viewRef.current.factIdx % f.length], 7000);
    setViewField("factIdx", (idx) => idx + 1);
  }

  function handleDwell(el: Element | null) {
    const state = viewRef.current;
    const work = workRef.current;
    if (!el || !getShyMode() || state.hidden) return;
    const ctx = contextLine(el);
    const key = ctx?.key ?? "";
    if (key === work.dwellKey) return; // same thing — let the timer ride
    work.dwellKey = key;
    work.dwellTimer = clearTracked(work.dwellTimer);
    if (!ctx) return;
    work.dwellTimer = after(DWELL_MS, () => {
      const current = workRef.current;
      current.dwellTimer = null;
      const now = performance.now();
      if (now - current.lastContext < CONTEXT_COOLDOWN) return;
      if (key === current.lastContextKey && now - current.lastContext < 12_000) return;
      const latest = viewRef.current;
      if (current.moving || latest.runner || latest.shyState === "hidden" || latest.bubble) return;
      current.lastContext = now;
      current.lastContextKey = key;
      // Sometimes he relocates to another side just to deliver it.
      const ctxLine = pickFresh(ctx.lines);
      if (current.anchorEl && Math.random() < 0.4) {
        current.pendingLine = ctxLine;
        current.speakOnArrive = "yes";
        moveBehind(current.anchorEl, { run: false });
      } else {
        speak(ctxLine);
      }
    });
  }

  function onPointerMove(e: PointerEvent) {
    const work = workRef.current;
    work.cursor = { x: e.clientX, y: e.clientY };
    work.lastHover = e.target instanceof Element ? e.target : null;
    // Eyes track the cursor from wherever he's hiding (mid-run he watches the road).
    if (!viewRef.current.runner) {
      const state = viewRef.current;
      const c = state.spot && getShyMode() ? spotCenter(state.spot) : { x: window.innerWidth - 70, y: window.innerHeight - 90 };
      setViewField("pupils", {
        x: Math.max(-2.2, Math.min(2.2, (e.clientX - c.x) / 200)),
        y: Math.max(-1.6, Math.min(1.6, (e.clientY - c.y) / 240)),
      });
    }
    handleDwell(work.lastHover);

    if (!getShyMode() || viewRef.current.hidden) {
      // Napping in the corner: stir once if you come close.
      if (getMode() === "asleep" && !work.saidSleepLine && !viewRef.current.hidden) {
        const d = Math.hypot(e.clientX - (window.innerWidth - 70), e.clientY - (window.innerHeight - 90));
        if (d < 140) {
          work.saidSleepLine = true;
          say("mm? the loop’s napping. me too.", 4500);
        }
      }
      return;
    }
    const now = performance.now();
    if (now - work.lastBehave < 120) {
      // Don't drop the trailing position — a fast dart should still register.
      if (work.behaveTimer === null) {
        work.behaveTimer = after(130, () => {
          const current = workRef.current;
          current.behaveTimer = null;
          current.lastBehave = performance.now();
          behave();
        });
      }
      return;
    }
    work.lastBehave = now;
    behave();
  }

  function behave() {
    const state = viewRef.current;
    const work = workRef.current;
    if (!getShyMode() || state.hidden || !state.booted) return;
    // Too close — fright comes first.
    if (state.spot && !work.moving && !state.runner && state.shyState !== "hidden") {
      const sc = spotCenter(state.spot);
      if (Math.hypot(work.cursor.x - sc.x, work.cursor.y - sc.y) < STARTLE_DIST) {
        startle();
        return;
      }
    }
    if (work.moving || state.runner) return;
    // Follow the thing you're on: new block ? run behind it.
    const blk = work.lastHover ? hideableFrom(work.lastHover) : null;
    if (blk && blk !== work.anchorEl) {
      if (work.pendingBlock !== blk) {
        work.pendingBlock = blk;
        work.blockTimer = clearTracked(work.blockTimer);
        work.blockTimer = after(380, () => {
          const current = workRef.current;
          current.blockTimer = null;
          const still = current.lastHover ? hideableFrom(current.lastHover) : null;
          if (still && still === current.pendingBlock && still !== current.anchorEl && !current.moving && !viewRef.current.runner) {
            current.speakOnArrive = "maybe";
            moveBehind(still, { run: true });
          }
          current.pendingBlock = null;
        });
      }
      return;
    }
    // Bare background, far away: drift to whatever's near the cursor.
    if (!blk && state.spot && work.followTimer === null) {
      const sc = spotCenter(state.spot);
      if (Math.hypot(work.cursor.x - sc.x, work.cursor.y - sc.y) > 620) {
        work.followTimer = after(800, () => {
          const current = workRef.current;
          current.followTimer = null;
          const latest = viewRef.current;
          if (current.moving || latest.runner || !latest.spot) return;
          const near = nearestBlock(current.cursor);
          if (near && near.el !== current.anchorEl) {
            current.speakOnArrive = "maybe";
            moveBehind(near.el, { run: true });
          }
        });
      }
    }
  }

  function onScroll() {
    const state = viewRef.current;
    const work = workRef.current;
    if (!getShyMode() || state.hidden) return;
    if (state.runner) cancelRun();
    if (state.shyState !== "hidden") setViewField("shyState", "hidden");
    setViewField("bubble", null);
    work.scrollTimer = clearTracked(work.scrollTimer);
    work.scrollTimer = after(480, () => {
      const current = workRef.current;
      current.scrollTimer = null;
      current.moving = false;
      current.speakOnArrive = "no";
      const vh = window.innerHeight;
      if (current.anchorEl?.isConnected) {
        const r = current.anchorEl.getBoundingClientRect();
        if (r.bottom > 100 && r.top < vh - 40) {
          const keep = current.anchorEl;
          current.anchorEl = null; // force a re-pick of sides at the new scroll position
          moveBehind(keep, { run: false });
          return;
        }
      }
      const near = nearestBlock(current.cursor.x >= 0 ? current.cursor : { x: window.innerWidth / 2, y: vh / 2 });
      if (near) moveBehind(near.el, { run: false });
    });
  }

  function dismiss(e: React.MouseEvent<HTMLButtonElement>) {
    e.stopPropagation();
    applyViewPatch({ hidden: true, bubble: null });
    try {
      localStorage.setItem("tinybot:hidden", "1");
    } catch {}
  }

  function show() {
    setViewField("hidden", false);
    try {
      localStorage.removeItem("tinybot:hidden");
    } catch {}
    if (getShyMode()) {
      const work = workRef.current;
      work.pendingLine = "back. what did I miss?";
      work.speakOnArrive = "yes";
      const near = nearestBlock(work.cursor.x >= 0 ? work.cursor : { x: window.innerWidth / 2, y: window.innerHeight / 2 });
      if (near) moveBehind(near.el, { run: false });
    } else {
      say("back. what did I miss?");
    }
  }

  // Route change: new page, new cover, deliver the route line from wherever fits.
  React.useEffect(() => {
    const p = pathname ?? "/";
    pathnameRef.current = p;
    const state = viewRef.current;
    if (!state.booted || state.hidden || p === state.lastPath) {
      setViewField("lastPath", p);
      return;
    }
    setViewField("lastPath", p);
    const hit = LINES.find((l) => l.match(p));
    const work = workRef.current;
    if (hit) work.routeLinePending = hit.line;
    if (getShyMode()) {
      if (viewRef.current.runner) cancelRun();
      work.anchorEl = null;
      after(500, () => {
        const current = workRef.current;
        if (current.moving || viewRef.current.runner) return;
        const near = nearestBlock(
          current.cursor.x >= 0 ? current.cursor : { x: window.innerWidth * 0.6, y: window.innerHeight * 0.5 },
        );
        current.speakOnArrive = "yes";
        if (near) moveBehind(near.el, { run: !!viewRef.current.spot });
        else {
          setViewField("spot", fallbackSpot());
          setViewField("shyState", "peek");
          onArrived();
        }
      });
    } else if (hit) {
      say(hit.line);
    }
  }, [pathname]);

  const runnerTransform = React.useMemo(() => {
    const tilt = view.runPose === "run" ? 9 : view.runPose === "skid" ? -14 : 0;
    return `scaleX(${view.facing}) rotate(${tilt}deg)`;
  }, [view.facing, view.runPose]);

  const shyTransform = React.useMemo(() => {
    if (!view.spot) return "translateY(120%)";
    if (view.spot.dir === "up") {
      const ty = view.shyState === "hidden" ? 110 : view.shyState === "deep" ? 16 : 46;
      return `translateX(-50%) translateY(${ty}%)`;
    }
    if (view.spot.dir === "left") {
      const tx = view.shyState === "hidden" ? 110 : view.shyState === "deep" ? 26 : 50;
      return `translateX(${tx}%) rotate(${view.shyState === "hidden" ? 0 : -8}deg)`;
    }
    const tx = view.shyState === "hidden" ? -110 : view.shyState === "deep" ? -26 : -50;
    return `translateX(${tx}%) rotate(${view.shyState === "hidden" ? 0 : 8}deg)`;
  }, [view.shyState, view.spot]);

  React.useEffect(() => {
    setViewField("mounted", true);
    try {
      setViewField("hidden", localStorage.getItem("tinybot:hidden") === "1");
    } catch {}
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const fine = window.matchMedia("(pointer: fine)").matches;
    setViewField("shyCapable", fine && !reduced);
    void fetchVitals().then((v) => setViewField("vitals", v));

    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });

    after(1400, () => {
      const p = pathnameRef.current;
      applyViewPatch({ booted: true, lastPath: p });
      if (viewRef.current.hidden) return;
      const hit = LINES.find((l) => l.match(p));
      const work = workRef.current;
      if (viewRef.current.shyCapable) {
        work.routeLinePending = hit ? hit.line : "hello. I live here. mostly behind things.";
        work.speakOnArrive = "yes";
        const near = nearestBlock(
          work.cursor.x >= 0 ? work.cursor : { x: window.innerWidth * 0.62, y: window.innerHeight * 0.62 },
        );
        if (near) moveBehind(near.el, { run: false });
        else {
          setViewField("spot", fallbackSpot());
          setViewField("shyState", "peek");
          onArrived();
        }
      } else {
        say(hit ? hit.line : "hello. I live here.");
      }
    });

    return () => {
      const work = workRef.current;
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (work.runRaf) window.cancelAnimationFrame(work.runRaf);
      for (const id of work.timers) window.clearTimeout(id);
      work.timers.clear();
      if (work.bubbleTimer) window.clearTimeout(work.bubbleTimer);
    };
  }, []);

  function BotSvg() {
    const mode = modeFromVitals(view.vitals);
    const pupils = view.pupils;

    return (
      <svg className={styles["bot__svg"]} viewBox="0 0 120 140" width={BOT_W} height={BOT_H} aria-hidden="true">
        <g className={styles["bot__body-group"]}>
          {/* antenna */}
          <g className={styles.antenna}>
            <path d="M60 26 C 60 18, 64 14, 64 9" fill="none" stroke="var(--ink-text-900)" strokeWidth="2.4" strokeLinecap="round" />
            <circle className={styles["antenna__tip"]} cx="64" cy="8" r="4.6" fill="var(--ember-600)" />
          </g>
          {/* head */}
          <g className={styles.head}>
            <rect x="30" y="24" width="60" height="44" rx="14" fill="var(--paper-50)" stroke="var(--ink-text-900)" strokeWidth="2.6" />
            {mode === "asleep" ? (
              <>
                <path d="M44 46 q 5 4 10 0" fill="none" stroke="var(--ink-text-900)" strokeWidth="2.4" strokeLinecap="round" />
                <path d="M66 46 q 5 4 10 0" fill="none" stroke="var(--ink-text-900)" strokeWidth="2.4" strokeLinecap="round" />
              </>
            ) : mode === "error" ? (
              <>
                <path d="M45 42 l8 8 m0 -8 l-8 8" stroke="var(--ink-text-900)" strokeWidth="2.2" strokeLinecap="round" />
                <path d="M67 42 l8 8 m0 -8 l-8 8" stroke="var(--ink-text-900)" strokeWidth="2.2" strokeLinecap="round" />
              </>
            ) : (
              <>
                <g className={styles["eye-l"]}>
                  <circle cx="49" cy="46" r="6.5" fill="#fff" stroke="var(--ink-text-900)" strokeWidth="2" />
                  <circle cx={49 + pupils.x} cy={46 + pupils.y} r="2.6" fill="var(--ink-text-900)" />
                </g>
                <g className={styles["eye-r"]}>
                  <circle cx="71" cy="46" r="6.5" fill="#fff" stroke="var(--ink-text-900)" strokeWidth="2" />
                  <circle cx={71 + pupils.x} cy={46 + pupils.y} r="2.6" fill="var(--ink-text-900)" />
                </g>
              </>
            )}
            {mode === "awake" ? (
              <path d="M54 58 q 6 4 12 0" fill="none" stroke="var(--ink-text-900)" strokeWidth="2.2" strokeLinecap="round" />
            ) : mode === "asleep" ? (
              <circle cx="60" cy="59" r="2.4" fill="none" stroke="var(--ink-text-900)" strokeWidth="1.8" />
            ) : (
              <line x1="55" y1="58" x2="65" y2="58" stroke="var(--ink-text-900)" strokeWidth="2.2" strokeLinecap="round" />
            )}
          </g>
          {/* body */}
          <g className={styles.torso}>
            <rect x="38" y="72" width="44" height="36" rx="11" fill="var(--paper-100)" stroke="var(--ink-text-900)" strokeWidth="2.6" />
            {/* chest LED = the loop, honestly */}
            <circle
              className={styles.led}
              cx="60"
              cy="86"
              r="4.4"
              fill={mode === "awake" ? "var(--live-600)" : mode === "asleep" ? "var(--signal-idle)" : mode === "error" ? "var(--signal-error)" : "var(--ink-text-300)"}
            />
            <line x1="46" y1="98" x2="74" y2="98" stroke="var(--border-2)" strokeWidth="1.6" />
          </g>
          {/* arms */}
          <g className={cx(styles.arm, styles["arm--l"])}>
            <path d="M38 80 C 28 84, 26 92, 28 97" fill="none" stroke="var(--ink-text-900)" strokeWidth="2.6" strokeLinecap="round" />
          </g>
          <g className={cx(styles.arm, styles["arm--r"])}>
            <path d="M82 80 C 92 84, 94 92, 92 97" fill="none" stroke="var(--ink-text-900)" strokeWidth="2.6" strokeLinecap="round" />
          </g>
          {/* legs */}
          <g className={cx(styles.leg, styles["leg--l"])}>
            <rect x="46" y="108" width="10" height="14" rx="4.5" fill="var(--paper-50)" stroke="var(--ink-text-900)" strokeWidth="2.4" />
          </g>
          <g className={cx(styles.leg, styles["leg--r"])}>
            <rect x="64" y="108" width="10" height="14" rx="4.5" fill="var(--paper-50)" stroke="var(--ink-text-900)" strokeWidth="2.4" />
          </g>
        </g>
        {mode === "asleep" && (
          <g className={styles.zz} fill="none" stroke="var(--signal-idle)" strokeWidth="1.8" strokeLinecap="round">
            <path className={cx(styles.z, styles.z1)} d="M88 30 h8 l-8 8 h8" />
            <path className={cx(styles.z, styles.z2)} d="M99 16 h6 l-6 6 h6" />
          </g>
        )}
      </svg>
    );
  }

  const mode = modeFromVitals(view.vitals);
  const shyMode = isShyModeFromView(view);

  if (!view.mounted) return null;

  if (view.hidden) {
    return (
      <button className={styles.peek} onClick={show} aria-label="Bring Tiny back">
        <svg viewBox="0 0 24 30" width="16" height="20" aria-hidden="true">
          <line x1="12" y1="10" x2="12" y2="3" stroke="currentColor" strokeWidth="1.8" />
          <circle cx="12" cy="3" r="2.4" fill="var(--ember-600)" stroke="none" />
          <rect x="4" y="10" width="16" height="14" rx="5" fill="var(--paper-50)" stroke="currentColor" strokeWidth="1.8" />
        </svg>
      </button>
    );
  }

  if (shyMode) {
    return (
      <>
        {view.bubble && (
          <div
            className={cx(styles["bubble-float"], view.bubblePos.above && styles.above)}
            style={{ left: view.bubblePos.left, top: view.bubblePos.top }}
            role="status"
          >
            <span className={styles["bubble__text"]}>{view.bubble}</span>
          </div>
        )}
        {view.runner && (
          <div
            className={cx(styles["tiny-runner"], view.runPose === "skid" && styles.skid, view.runPose === "pant" && styles.pant)}
            style={{ left: view.runner.x, top: view.runner.y }}
            aria-hidden="true"
          >
            <div className={styles["runner-bob"]}>
              <div className={styles["runner-inner"]} style={{ transform: runnerTransform }}>
                <BotSvg />
              </div>
            </div>
            {view.runPose === "skid" && <div className={styles.dust}></div>}
          </div>
        )}
        {view.spot && !view.runner && (
          <div
            className={styles["tiny-shy"]}
            style={{ left: view.spot.x, top: view.spot.y, width: view.spot.w, height: view.spot.h }}
          >
            <button
              className={cx(styles.shy, view.shyState === "hidden" && styles["is-hiding"])}
              data-dir={view.spot.dir}
              style={{ transform: shyTransform }}
              onClick={poke}
              aria-label="Tiny the robot, peeking out — click to hear a live fact"
              title="Tiny"
            >
              <BotSvg />
            </button>
            <button className={styles["bot__close"]} onClick={dismiss} aria-label="Dismiss Tiny">
              ×
            </button>
          </div>
        )}
      </>
    );
  }

  return (
    <div className={cx(styles["bot-wrap"], mode === "asleep" && styles.asleep)}>
      {view.bubble && (
        <div className={styles.bubble} role="status">
          <span className={styles["bubble__text"]}>{view.bubble}</span>
        </div>
      )}
      <div className={cx(styles.bot, view.waving && styles.waving)}>
        <button className={cx(styles["bot__close"], styles["bot__close--corner"])} onClick={dismiss} aria-label="Dismiss Tiny">
          ×
        </button>
        <button className={styles["bot__hit"]} onClick={poke} aria-label="Tiny the robot — click to hear a live fact" title="Tiny">
          <BotSvg />
        </button>
      </div>
    </div>
  );
}

export default TinyBot;
