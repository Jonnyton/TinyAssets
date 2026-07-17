<!--
  TinyBot — Tiny himself, living on (and behind) the site.

  A small living goal-engine who is genuinely shy. He hides behind whatever
  your mouse is on — cards, tables, paragraphs, headings, anything with a
  shape — and peeks out a random side of it. Move to the next block and he
  runs behind that one instead (little legs, skids on direction changes,
  sometimes out of breath). When he has something to say he just pops out
  of whichever side of his current hiding place suits him.

  What he says is a weighted draw from the moment's context — the thing
  he's hiding behind, the route, live-read facts, shy mutters — never an
  exact script, never a repeat of his last few lines.

  Honesty rails still apply: his chest LED and posture come from the SAME
  live vitals the rest of the site reads. Loop asleep → he stops following
  and naps in the corner. Engine unreachable → ×-eyes, and he says so.

  Coarse pointers (touch) and prefers-reduced-motion get the calm
  stationary version. Dismissible — persists in localStorage.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { fetchVitals, type Vitals } from '$lib/mcp/live';
  import { fmtRel } from '$lib/fmt';

  type Dir = 'up' | 'left' | 'right';
  type Spot = { x: number; y: number; w: number; h: number; dir: Dir };

  type SpriteState =
    | 'idle'
    | 'run-right'
    | 'run-left'
    | 'wave'
    | 'jump'
    | 'failure'
    | 'waiting'
    | 'active-work'
    | 'review';

  const BOT_W = 88;
  const BOT_H = 95;
  const SIZE: Record<Dir, { w: number; h: number }> = {
    up: { w: 118, h: 100 },
    left: { w: 104, h: 112 },
    right: { w: 104, h: 112 }
  };
  const SPEAK_COOLDOWN = 5_200;
  const STARTLE_DIST = 110;
  const RUN_SPEED = 350; // px/s — slow enough to visibly fail to keep up
  const SPRINT_SPEED = 560;
  const DWELL_MS = 520;
  const CONTEXT_COOLDOWN = 4_200;

  // Anything with a shape is fair cover — cards, tables, words, pictures.
  const HIDEABLE =
    'p, table, pre, ul, ol, figure, blockquote, h1, h2, h3, img, aside, details, ' +
    '[class*="card"], [class*="panel"], [class*="tile"], [class*="step"], [class*="vital"], ' +
    '[class*="ladder"], [class*="hero"], footer';

  let vitals = $state<Vitals | null>(null);
  let hidden = $state(false);
  let mounted = $state(false);
  let booted = $state(false);
  let shyCapable = $state(false);

  let bubble = $state<string | null>(null);
  let bubblePos = $state({ left: 0, top: 0, above: true });
  let waving = $state(false);
  let jumping = $state(false);
  let factIdx = $state(0);

  let spot = $state<Spot | null>(null);
  let shyState = $state<'hidden' | 'peek' | 'deep'>('hidden');

  // The runner — him out in the open, trying his best.
  let runner = $state<{ x: number; y: number } | null>(null);
  let runPose = $state<'run' | 'skid' | 'pant'>('run');
  let facing = $state(1); // 1 = running right, -1 = left

  // non-reactive working state
  let anchorEl: Element | null = null; // what he's currently hiding behind
  let lastHover: Element | null = null;
  let pendingBlock: Element | null = null;
  let cursor = { x: -1, y: -1 };
  let moving = false;
  let lastSpoke = 0;
  let lastBehave = 0;
  let routeLinePending: string | null = null;
  let pendingLine: string | null = null;
  let speakOnArrive: 'yes' | 'maybe' | 'no' = 'maybe';
  let recentLines: string[] = [];
  let saidSleepLine = false;
  let startleCount = 0;
  let graceTill = 0;
  let blockTimer: number | null = null;
  let followTimer: number | null = null;
  let behaveTimer: number | null = null;
  let scrollTimer: number | null = null;
  let bubbleTimer: number | null = null;
  let idleTimer: number | null = null;
  const timers = new Set<number>();

  // run-loop working state
  let runRaf = 0;
  let runTargetSpot: Spot | null = null;
  let entryPoint: { x: number; y: number } | null = null;
  let lastFrameT = 0;
  let runStartT = 0;
  let lastRetargetT = 0;
  let retargetCount = 0;
  let runDist = 0;
  let sprinting = false;

  // hover-dwell commentary state
  let dwellKey = '';
  let dwellTimer: number | null = null;
  let lastContext = 0;
  let lastContextKey = '';

  const mode = $derived<'reading' | 'awake' | 'asleep' | 'error'>(
    !vitals ? 'reading' : !vitals.reachable ? 'error' : vitals.loopAwake ? 'awake' : 'asleep'
  );
  // Shy following only while he's actually up. Asleep/error = stationary, honestly.
  const shyMode = $derived(shyCapable && (mode === 'awake' || mode === 'reading'));
  const restingSprite = $derived<SpriteState>(
    mode === 'error'
      ? 'failure'
      : mode === 'asleep' || mode === 'reading'
        ? 'waiting'
        : vitals?.activeRun
          ? 'active-work'
          : jumping
            ? 'jump'
            : waving
              ? 'wave'
              : bubble
                ? 'review'
                : 'idle'
  );
  const runnerSprite = $derived<SpriteState>(
    runPose === 'skid'
      ? 'failure'
      : runPose === 'pant'
        ? 'waiting'
        : facing === 1
          ? 'run-right'
          : 'run-left'
  );

  /* ---------- what he can say ---------- */

  const LINES: Array<{ match: (p: string) => boolean; line: string }> = [
    { match: (p) => p === '/', line: 'that’s me they’re describing.' },
    { match: (p) => p.startsWith('/start'), line: 'two minutes, no account. I checked the door myself.' },
    { match: (p) => p.startsWith('/goals/'), line: 'this ladder only lights with evidence. no shortcuts.' },
    { match: (p) => p.startsWith('/goals'), line: 'every goal here is real — read live, not typed in.' },
    { match: (p) => p.startsWith('/loop'), line: 'this is where I get repaired. the mess stays public.' },
    { match: (p) => p.startsWith('/commons') || p.startsWith('/wiki'), line: 'my whole memory. nothing private lives in here.' },
    { match: (p) => p.startsWith('/graph'), line: 'my head, seen from above.' },
    { match: (p) => p.startsWith('/soul'), line: 'everything that makes me me — forkable.' },
    { match: (p) => p.startsWith('/build') || p.startsWith('/contribute'), line: 'two doors in. humans hold the merge keys.' },
    { match: (p) => p.startsWith('/host'), line: 'you don’t have to host me. but you can.' },
    { match: (p) => p.startsWith('/alliance'), line: 'say hi — it all lands in the same loop.' },
    { match: (p) => p.startsWith('/fine-print') || p.startsWith('/status'), line: 'my pulse, explained honestly.' },
    { match: (p) => p.startsWith('/legal'), line: 'the boring page. still mine.' }
  ];

  const SHY_LINES = [
    'oh — didn’t see you there.',
    'I’m not hiding. I’m… observing.',
    'you found me.',
    'just tidying up back here.',
    'don’t mind me.',
    'I like this spot. good sightlines.',
    'still here. mostly behind things.'
  ];

  const MUTTERS = [
    'you move that thing fast.',
    'the dots on this desk? my graph paper.',
    'I count my own runs. all of them.',
    'it’s quiet back here. I like it.',
    'I leave everything public. less to remember.',
    'if the loop’s awake, I’m awake.',
    'good page, this one. I checked it twice.'
  ];

  // What he says about the thing your mouse is resting on.
  const DEST: Array<{ match: (h: string) => boolean; lines: string[] }> = [
    { match: (h) => h.startsWith('/start'), lines: ['that door takes two minutes. I timed it.', 'through there: paste one URL, no account.'] },
    { match: (h) => h.startsWith('/loop'), lines: ['that’s my repair shop. the mess stays public.', 'in there I get fixed — out loud.'] },
    { match: (h) => h.startsWith('/goals'), lines: ['the goals board — all real, read live.', 'open outcomes through there. pick one.'] },
    { match: (h) => h.startsWith('/commons') || h.startsWith('/wiki'), lines: ['my memory lives through there.', 'everything I know, public, in there.'] },
    { match: (h) => h.startsWith('/graph'), lines: ['careful — that’s the inside of my head.', 'my whole brain, drawn out, through there.'] },
    { match: (h) => h.startsWith('/soul'), lines: ['my soul. you can fork it, you know.', 'the pattern that makes me me — forkable.'] },
    { match: (h) => h.startsWith('/build') || h.startsWith('/contribute'), lines: ['through there you can change me. humans keep the keys.', 'two doors to rebuild me are in there.'] },
    { match: (h) => h.startsWith('/host'), lines: ['hosting me is optional. I run either way.', 'you can run your own me through there.'] },
    { match: (h) => h.startsWith('/alliance'), lines: ['that’s how you reach the humans. and me.', 'say hi through there — same loop.'] },
    { match: (h) => h.startsWith('/fine-print') || h.startsWith('/status'), lines: ['my pulse, with no makeup on.', 'the instrument panel’s through there.'] },
    { match: (h) => h.startsWith('/legal'), lines: ['the boring page. I keep it honest anyway.', 'fine print through there. still mine.'] }
  ];

  function facts(): string[] {
    const f: string[] = [];
    if (vitals?.queue) f.push(`runs so far: ${vitals.queue.succeeded.toLocaleString()} done, ${vitals.queue.failed} failed — counted live.`);
    if (vitals?.deployedAt) f.push(`this body deployed ${fmtRel(vitals.deployedAt)}.`);
    if (mode === 'asleep') f.push('the loop’s napping. the engine is still up — that’s two different things.');
    if (mode === 'awake' && vitals?.activeRun) f.push('a run is moving through me right now.');
    f.push('I was born 3 Jun 2026. I flooded my own repo on day two. fixed now.');
    f.push('no rung lights without an evidence URL. mine included.');
    f.push('paste tinyassets.io/mcp into your chatbot and you read the same pulse I do.');
    return f;
  }

  function contextLine(el: Element): { key: string; lines: string[] } | null {
    if (el.closest('.tiny-shy, .tiny-runner, .bubble-float, .bot-wrap, .peek')) return null;
    const a = el.closest('a[href]');
    if (a) {
      const href = a.getAttribute('href') ?? '';
      if (href.includes('github.com'))
        return { key: 'gh', lines: ['my source. every line of me is public.', 'that’s my code. read it, fork it, fix it.', 'all of me is on GitHub. no hidden bits.'] };
      if (href.startsWith('/')) {
        const hit = DEST.find((d) => d.match(href));
        if (hit) return { key: 'dest:' + href.split('/')[1], lines: hit.lines };
      }
      if (href.startsWith('http'))
        return { key: 'ext:' + href, lines: ['that one leaves the site. I’ll wait here.', 'off-site, that. I’ll hold your spot.'] };
    }
    const codey = el.closest('code, pre, button, .ev');
    if (codey?.textContent?.includes('tinyassets.io/mcp'))
      return { key: 'mcp', lines: ['that string is me. paste it into your chatbot and we can talk properly.', 'one URL — that’s the whole door in.', 'copy that, drop it in your chatbot, and you read my live pulse too.'] };
    if (el.closest('.readout, [class*="stat"]'))
      return { key: 'readout', lines: ['those readings are live. I feel each one.', 'that panel’s my instrument face — no makeup.', 'live the moment you look. I can’t fake a flat line.'] };
    if (el.closest('[class*="vital"]'))
      return { key: 'vitals', lines: ['those numbers are my actual pulse.', 'that’s me, measured — not a sales figure.', 'green means I’m really awake; amber means napping.'] };
    if (el.closest('[class*="ladder"], [class*="rung"]'))
      return { key: 'ladder', lines: ['unlit rungs. I only light them with evidence.', 'no rung lights without a real URL behind it.', 'I can’t fake a single step on that.'] };
    if (el.closest('[class*="goal"]'))
      return { key: 'goal', lines: ['a real goal. someone could pick it up today.', 'that one’s open — fork it, beat it, own it.', 'goals here are outcomes, not to-do items.'] };
    if (el.closest('[class*="log"], [class*="event"]'))
      return { key: 'log', lines: ['my history — including the embarrassing parts.', 'every run logged, even the failed ones.', 'receipts. I keep all of them.'] };
    if (el.closest('table'))
      return { key: 'table', lines: ['rows and rows of receipts.', 'all checkable — that’s the point.', 'numbers you can verify yourself.'] };
    if (el.closest('.voice'))
      return { key: 'voice', lines: ['yeah… that’s me talking.', 'first person. it’s all me.', 'I mean every word on this page.'] };
    if (el.closest('figure, img'))
      return { key: 'img', lines: ['I don’t keep many pictures. that’s one.', 'rare, a picture. mostly I deal in numbers.'] };
    if (el.closest('h1, h2, h3'))
      return { key: 'head', lines: ['this bit matters — I’d read it twice.', 'good heading. I’d underline it.'] };
    if (el.closest('pre, code'))
      return { key: 'code', lines: ['code. probably mine.', 'that’s the sort of thing my loop rewrites.'] };
    return null;
  }

  function after(ms: number, fn: () => void): number {
    const id = window.setTimeout(() => {
      timers.delete(id);
      fn();
    }, ms);
    timers.add(id);
    return id;
  }
  const rand = (a: number, b: number) => a + Math.random() * (b - a);
  const pickOf = <T,>(arr: T[]): T => arr[Math.floor(Math.random() * arr.length)];
  // Pick a line from a pool that he hasn't said recently — so re-hovering the
  // same thing gives different words, never the same line twice in a row.
  const pickFresh = (lines: string[]): string => {
    const fresh = lines.filter((l) => !recentLines.includes(l));
    return pickOf(fresh.length ? fresh : lines);
  };

  /* ---------- finding cover ---------- */

  function spotCenter(s: Spot) {
    if (s.dir === 'up') return { x: s.x + s.w / 2, y: s.y + s.h - 26 };
    if (s.dir === 'left') return { x: s.x + 26, y: s.y + 44 };
    return { x: s.x + s.w - 26, y: s.y + 44 };
  }

  function ownUi(el: Element): boolean {
    return !!el.closest('.tiny-shy, .tiny-runner, .bubble-float, .bot-wrap, .peek, nav');
  }

  // The block your mouse is on — climbing out of too-small or absurd matches.
  function hideableFrom(el: Element | null): Element | null {
    let cur: Element | null = el?.closest(HIDEABLE) ?? null;
    for (let i = 0; cur && i < 4; i++) {
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
          out.push({ x, y, w: su.w, h: su.h, dir: 'up' });
      }
    }
    if (r.height >= 64) {
      const sl = SIZE.left;
      for (const t of [0.25, 0.65]) {
        const x = r.left - sl.w + 3;
        const y = clamp(r.top + t * r.height - sl.h / 2, topSafe, vh - sl.h - pad);
        if (x >= pad - 2 && y + sl.h / 2 > r.top - 10 && y + sl.h / 2 < r.bottom + 10)
          out.push({ x, y, w: sl.w, h: sl.h, dir: 'left' });
      }
      const sr = SIZE.right;
      for (const t of [0.25, 0.65]) {
        const x = r.right - 3;
        const y = clamp(r.top + t * r.height - sr.h / 2, topSafe, vh - sr.h - pad);
        if (x + sr.w <= vw - pad + 2 && y + sr.h / 2 > r.top - 10 && y + sr.h / 2 < r.bottom + 10)
          out.push({ x, y, w: sr.w, h: sr.h, dir: 'right' });
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
      dir: 'up'
    };
  }

  /* ---------- speech ---------- */

  function placeBubbleXY(cx: number, topY: number, h: number) {
    const vw = window.innerWidth;
    const left = Math.max(10, Math.min(cx - 120, vw - 260));
    if (topY > 150) bubblePos = { left, top: topY - 8, above: true };
    else bubblePos = { left, top: topY + h + 10, above: false };
  }
  function placeBubble(s: Spot) {
    placeBubbleXY(spotCenter(s).x, s.y, s.h);
  }

  function say(text: string, ms = 6000) {
    if (shyMode) {
      if (runner) placeBubbleXY(runner.x + BOT_W / 2, runner.y, BOT_H);
      else if (spot) placeBubble(spot);
    }
    bubble = text;
    if (bubbleTimer) clearTimeout(bubbleTimer);
    bubbleTimer = window.setTimeout(() => {
      bubble = null;
      if (shyState === 'deep') shyState = 'peek';
    }, ms);
  }

  // A weighted draw from the moment: never scripted, never a recent repeat.
  function speak(forced?: string) {
    let line = forced ?? pendingLine;
    pendingLine = null;
    if (!line && routeLinePending) {
      line = routeLinePending;
      routeLinePending = null;
    }
    if (!line) {
      const pool: string[] = [];
      const ctx = anchorEl ? contextLine(anchorEl) : null;
      if (ctx) { const cl = pickFresh(ctx.lines); pool.push(cl, cl); } // context weighs double, never dictates
      const f = facts();
      pool.push(f[factIdx % f.length]);
      pool.push(pickOf(SHY_LINES));
      pool.push(pickOf(MUTTERS));
      const fresh = pool.filter((l) => !recentLines.includes(l));
      if (!fresh.length) return;
      line = pickOf(fresh);
      if (line === f[factIdx % f.length]) factIdx += 1;
    }
    recentLines.push(line);
    if (recentLines.length > 10) recentLines.shift();
    lastSpoke = performance.now();
    shyState = 'deep';
    say(line);
  }

  function scheduleIdle() {
    if (idleTimer) {
      clearTimeout(idleTimer);
      timers.delete(idleTimer);
    }
    idleTimer = after(rand(13_000, 26_000), () => {
      idleTimer = null;
      if (shyMode && !hidden && !moving && !runner && shyState !== 'hidden' && !bubble) {
        // Sometimes he switches sides just to deliver a mutter.
        if (anchorEl && Math.random() < 0.5) {
          speakOnArrive = 'yes';
          moveBehind(anchorEl, { run: false });
        } else {
          speak();
        }
      }
      scheduleIdle();
    });
  }

  /* ---------- movement ---------- */

  function onArrived() {
    moving = false;
    const intend = speakOnArrive;
    speakOnArrive = 'maybe';
    if (intend === 'yes') speak();
    else if (
      intend === 'maybe' &&
      (routeLinePending || pendingLine || Math.random() < 0.82) &&
      performance.now() - lastSpoke > SPEAK_COOLDOWN
    ) {
      speak();
    }
    scheduleIdle();
  }

  // Hide behind a specific element, peeking from a random workable side.
  function moveBehind(el: Element, opts?: { run?: boolean; sprint?: boolean }) {
    if (moving || hidden || !shyMode) return;
    const r = el.getBoundingClientRect();
    let list = blockSpots(r);
    if (!list.length) {
      const near = nearestBlock(cursor.x >= 0 ? cursor : { x: window.innerWidth / 2, y: window.innerHeight / 2 });
      if (near && near.el !== el) {
        moveBehind(near.el, opts);
        return;
      }
      list = [fallbackSpot()];
    }
    // Shy: don't pop out right under the cursor.
    const comfy = list.filter((s) => {
      const c = spotCenter(s);
      return Math.hypot(c.x - cursor.x, c.y - cursor.y) > 130;
    });
    let pool = comfy.length ? comfy : list;
    // Same block again? Prefer a different side — that's the charm.
    if (anchorEl === el && spot) {
      const others = pool.filter((s) => s.dir !== spot!.dir || Math.abs(s.x - spot!.x) > 40 || Math.abs(s.y - spot!.y) > 40);
      if (others.length) pool = others;
    }
    const pick = pickOf(pool);
    const sameBlock = anchorEl === el;
    anchorEl = el;
    if (!sameBlock) startleCount = 0;
    moving = true;
    bubble = null;
    const from = spot && booted ? spotCenter(spot) : null;
    shyState = 'hidden';
    after(160, () => {
      if (!from || !opts?.run) {
        spot = pick;
        after(180 + rand(0, 300), () => {
          shyState = 'peek';
          onArrived();
        });
      } else {
        startRun(from, pick, opts);
      }
    });
  }

  /* ---------- the run: out in the open, little legs going ---------- */

  function startRun(from: { x: number; y: number }, target: Spot, opts?: { sprint?: boolean }) {
    runTargetSpot = target;
    entryPoint = spotCenter(target);
    sprinting = !!opts?.sprint;
    runDist = 0;
    retargetCount = 0;
    runStartT = performance.now();
    lastFrameT = runStartT;
    lastRetargetT = runStartT;
    runPose = 'run';
    facing = entryPoint.x >= from.x ? 1 : -1;
    runner = { x: from.x - BOT_W / 2, y: from.y - BOT_H / 2 };
    runRaf = requestAnimationFrame(runFrame);
  }

  function runFrame(t: number) {
    if (!runner || !entryPoint) return;
    const dt = Math.min(0.05, (t - lastFrameT) / 1000);
    lastFrameT = t;
    if (runPose === 'run') {
      const cx = runner.x + BOT_W / 2;
      const cy = runner.y + BOT_H / 2;
      const dx = entryPoint.x - cx;
      const dy = entryPoint.y - cy;
      const d = Math.hypot(dx, dy);
      if (d < 12 || t - runStartT > 7000) {
        arrive();
        return;
      }
      const speed = sprinting ? SPRINT_SPEED : RUN_SPEED;
      const step = Math.min(d, speed * dt);
      runner = { x: runner.x + (dx / d) * step, y: runner.y + (dy / d) * step };
      runDist += step;
      facing = dx >= 0 ? 1 : -1;
      // Try (and fail) to keep up: if you've moved on to another block, re-aim.
      if (t - lastRetargetT > 450 && retargetCount < 3) {
        lastRetargetT = t;
        const blk = lastHover ? hideableFrom(lastHover) : null;
        if (blk && blk !== anchorEl) {
          const list = blockSpots(blk.getBoundingClientRect());
          if (list.length) {
            const pick = pickOf(list);
            const c2 = spotCenter(pick);
            const turn = Math.abs(Math.atan2(dy, dx) - Math.atan2(c2.y - cy, c2.x - cx));
            const turnNorm = Math.min(turn, Math.PI * 2 - turn);
            anchorEl = blk;
            startleCount = 0;
            runTargetSpot = pick;
            entryPoint = c2;
            retargetCount += 1;
            if (turnNorm > 0.9) {
              // Sharp direction change — skid first, little legs can't corner.
              runPose = 'skid';
              after(200, () => {
                if (runner) {
                  runPose = 'run';
                  lastFrameT = performance.now();
                }
              });
            }
          }
        }
      }
    }
    runRaf = requestAnimationFrame(runFrame);
  }

  function arrive() {
    runPose = 'skid';
    after(210, () => {
      if (!runner) return;
      const tired = runDist > 750 && Math.random() < 0.6;
      if (tired) {
        runPose = 'pant';
        say('…huff… huff…', 1500);
        after(1550, diveIn);
      } else {
        diveIn();
      }
    });
  }

  function diveIn() {
    if (!runTargetSpot) {
      runner = null;
      moving = false;
      return;
    }
    spot = runTargetSpot;
    runTargetSpot = null;
    runner = null;
    shyState = 'hidden';
    after(150, () => {
      shyState = 'peek';
      onArrived();
    });
  }

  function cancelRun() {
    if (runRaf) cancelAnimationFrame(runRaf);
    runRaf = 0;
    if (runner && runTargetSpot) spot = runTargetSpot;
    runner = null;
    runTargetSpot = null;
    moving = false;
  }

  /* ---------- reactions ---------- */

  function startle() {
    if (moving || runner) return;
    if (performance.now() < graceTill) return;
    graceTill = performance.now() + 900;
    startleCount += 1;
    if (startleCount >= 2) {
      // You keep chasing him — he bolts for somewhere farther.
      const far = farBlock(cursor, 400);
      if (far) {
        startleCount = 0;
        speakOnArrive = Math.random() < 0.4 ? 'maybe' : 'no';
        moveBehind(far.el, { run: true, sprint: true });
        say('!', 650);
        return;
      }
    }
    // First fright: just pop out a different side of the same thing.
    speakOnArrive = 'no';
    if (anchorEl) moveBehind(anchorEl, { run: false });
    say('!', 650);
  }

  function poke() {
    waving = true;
    window.setTimeout(() => (waving = false), 1200);
    if (shyMode) {
      const f = facts();
      shyState = 'deep';
      say(f[factIdx % f.length], 7000);
      factIdx += 1;
      lastSpoke = performance.now();
      return;
    }
    const f = facts();
    say(f[factIdx % f.length], 7000);
    factIdx += 1;
  }

  function handleDwell(el: Element | null) {
    if (!el || !shyMode || hidden) return;
    const ctx = contextLine(el);
    const key = ctx?.key ?? '';
    if (key === dwellKey) return; // same thing — let the timer ride
    dwellKey = key;
    if (dwellTimer) {
      clearTimeout(dwellTimer);
      timers.delete(dwellTimer);
      dwellTimer = null;
    }
    if (!ctx) return;
    dwellTimer = after(DWELL_MS, () => {
      dwellTimer = null;
      const now = performance.now();
      if (now - lastContext < CONTEXT_COOLDOWN) return;
      if (key === lastContextKey && now - lastContext < 12_000) return;
      if (moving || runner || shyState === 'hidden' || bubble) return;
      lastContext = now;
      lastContextKey = key;
      // Sometimes he relocates to another side just to deliver it.
      const ctxLine = pickFresh(ctx.lines);
      if (anchorEl && Math.random() < 0.4) {
        pendingLine = ctxLine;
        speakOnArrive = 'yes';
        moveBehind(anchorEl, { run: false });
      } else {
        speak(ctxLine);
      }
    });
  }

  function onPointerMove(e: PointerEvent) {
    cursor = { x: e.clientX, y: e.clientY };
    lastHover = e.target instanceof Element ? e.target : null;
    handleDwell(lastHover);

    if (!shyMode || hidden) {
      // Napping in the corner: stir once if you come close.
      if (mode === 'asleep' && !saidSleepLine && !hidden) {
        const d = Math.hypot(e.clientX - (window.innerWidth - 70), e.clientY - (window.innerHeight - 90));
        if (d < 140) {
          saidSleepLine = true;
          say('mm? the loop’s napping. me too.', 4500);
        }
      }
      return;
    }
    const now = performance.now();
    if (now - lastBehave < 120) {
      // Don't drop the trailing position — a fast dart should still register.
      if (behaveTimer === null) {
        behaveTimer = after(130, () => {
          behaveTimer = null;
          lastBehave = performance.now();
          behave();
        });
      }
      return;
    }
    lastBehave = now;
    behave();
  }

  function behave() {
    if (!shyMode || hidden || !booted) return;
    // Too close — fright comes first.
    if (spot && !moving && !runner && shyState !== 'hidden') {
      const sc = spotCenter(spot);
      if (Math.hypot(cursor.x - sc.x, cursor.y - sc.y) < STARTLE_DIST) {
        startle();
        return;
      }
    }
    if (moving || runner) return;
    // Follow the thing you're on: new block → run behind it.
    const blk = lastHover ? hideableFrom(lastHover) : null;
    if (blk && blk !== anchorEl) {
      if (pendingBlock !== blk) {
        pendingBlock = blk;
        if (blockTimer) {
          clearTimeout(blockTimer);
          timers.delete(blockTimer);
        }
        blockTimer = after(380, () => {
          blockTimer = null;
          const still = lastHover ? hideableFrom(lastHover) : null;
          if (still && still === pendingBlock && still !== anchorEl && !moving && !runner) {
            speakOnArrive = 'maybe';
            moveBehind(still, { run: true });
          }
          pendingBlock = null;
        });
      }
      return;
    }
    // Bare background, far away: drift to whatever's near the cursor.
    if (!blk && spot && followTimer === null) {
      const sc = spotCenter(spot);
      if (Math.hypot(cursor.x - sc.x, cursor.y - sc.y) > 620) {
        followTimer = after(800, () => {
          followTimer = null;
          if (moving || runner || !spot) return;
          const near = nearestBlock(cursor);
          if (near && near.el !== anchorEl) {
            speakOnArrive = 'maybe';
            moveBehind(near.el, { run: true });
          }
        });
      }
    }
  }

  function onScroll() {
    if (!shyMode || hidden) return;
    if (runner) cancelRun();
    if (shyState !== 'hidden') shyState = 'hidden';
    bubble = null;
    if (scrollTimer) {
      clearTimeout(scrollTimer);
      timers.delete(scrollTimer);
    }
    scrollTimer = after(480, () => {
      scrollTimer = null;
      moving = false;
      speakOnArrive = 'no';
      const vh = window.innerHeight;
      if (anchorEl?.isConnected) {
        const r = anchorEl.getBoundingClientRect();
        if (r.bottom > 100 && r.top < vh - 40) {
          const keep = anchorEl;
          anchorEl = null; // force a re-pick of sides at the new scroll position
          moveBehind(keep, { run: false });
          return;
        }
      }
      const near = nearestBlock(cursor.x >= 0 ? cursor : { x: window.innerWidth / 2, y: vh / 2 });
      if (near) moveBehind(near.el, { run: false });
    });
  }

  function dismiss(e: MouseEvent) {
    e.stopPropagation();
    hidden = true;
    bubble = null;
    try {
      localStorage.setItem('tinybot:hidden', '1');
    } catch {}
  }
  function show() {
    hidden = false;
    jumping = true;
    after(1200, () => (jumping = false));
    try {
      localStorage.removeItem('tinybot:hidden');
    } catch {}
    if (shyMode) {
      pendingLine = 'back. what did I miss?';
      speakOnArrive = 'yes';
      const near = nearestBlock(cursor.x >= 0 ? cursor : { x: window.innerWidth / 2, y: window.innerHeight / 2 });
      if (near) moveBehind(near.el, { run: false });
    } else {
      say('back. what did I miss?');
    }
  }

  // Route change: new page, new cover, deliver the route line from wherever fits.
  let lastPath = $state('');
  $effect(() => {
    const p = page.url.pathname;
    if (!booted || hidden || p === lastPath) {
      lastPath = p;
      return;
    }
    lastPath = p;
    const hit = LINES.find((l) => l.match(p));
    if (hit) routeLinePending = hit.line;
    if (shyMode) {
      if (runner) cancelRun();
      anchorEl = null;
      after(500, () => {
        if (moving || runner) return;
        const near = nearestBlock(cursor.x >= 0 ? cursor : { x: window.innerWidth * 0.6, y: window.innerHeight * 0.5 });
        speakOnArrive = 'yes';
        if (near) moveBehind(near.el, { run: !!spot });
        else {
          spot = fallbackSpot();
          shyState = 'peek';
          onArrived();
        }
      });
    } else if (hit) {
      say(hit.line);
    }
  });

  const runnerTransform = $derived.by(() => {
    const tilt = runPose === 'run' ? 9 : runPose === 'skid' ? -14 : 0;
    return `rotate(${tilt}deg)`;
  });

  const shyTransform = $derived.by(() => {
    if (!spot) return 'translateY(120%)';
    if (spot.dir === 'up') {
      const ty = shyState === 'hidden' ? 110 : shyState === 'deep' ? 16 : 46;
      return `translateX(-50%) translateY(${ty}%)`;
    }
    if (spot.dir === 'left') {
      const tx = shyState === 'hidden' ? 110 : shyState === 'deep' ? 26 : 50;
      return `translateX(${tx}%) rotate(${shyState === 'hidden' ? 0 : -8}deg)`;
    }
    const tx = shyState === 'hidden' ? -110 : shyState === 'deep' ? -26 : -50;
    return `translateX(${tx}%) rotate(${shyState === 'hidden' ? 0 : 8}deg)`;
  });

  onMount(() => {
    mounted = true;
    try {
      hidden = localStorage.getItem('tinybot:hidden') === '1';
    } catch {}
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const fine = window.matchMedia('(pointer: fine)').matches;
    shyCapable = fine && !reduced;
    void fetchVitals().then((v) => (vitals = v));

    window.addEventListener('pointermove', onPointerMove, { passive: true });
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });

    after(1400, () => {
      booted = true;
      const p = page.url.pathname;
      lastPath = p;
      if (hidden) return;
      const hit = LINES.find((l) => l.match(p));
      if (shyCapable) {
        routeLinePending = hit ? hit.line : 'hello. I live here. mostly behind things.';
        speakOnArrive = 'yes';
        const near = nearestBlock(
          cursor.x >= 0 ? cursor : { x: window.innerWidth * 0.62, y: window.innerHeight * 0.62 }
        );
        if (near) moveBehind(near.el, { run: false });
        else {
          spot = fallbackSpot();
          shyState = 'peek';
          onArrived();
        }
      } else {
        say(hit ? hit.line : 'hello. I live here.');
      }
    });

    return () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      if (runRaf) cancelAnimationFrame(runRaf);
      for (const id of timers) clearTimeout(id);
      timers.clear();
      if (bubbleTimer) clearTimeout(bubbleTimer);
    };
  });
</script>

{#snippet botSprite(state: SpriteState)}
  <span class="sprite-frame" aria-hidden="true">
    <span class="tiny-sprite sprite--{state}"></span>
  </span>
{/snippet}

{#if mounted}
  {#if hidden}
    <button class="peek" onclick={show} aria-label="Bring Tiny back">
      <span class="peek__core" aria-hidden="true"></span>
    </button>
  {:else if shyMode}
    {#if bubble}
      <div
        class="bubble-float"
        class:above={bubblePos.above}
        style="left: {bubblePos.left}px; top: {bubblePos.top}px;"
        role="status"
      >
        <span class="bubble__text">{bubble}</span>
      </div>
    {/if}
    {#if runner}
      <div
        class="tiny-runner"
        class:skid={runPose === 'skid'}
        class:pant={runPose === 'pant'}
        style="left: {runner.x}px; top: {runner.y}px;"
        aria-hidden="true"
      >
        <div class="runner-bob">
          <div class="runner-inner" style="transform: {runnerTransform};">
            {@render botSprite(runnerSprite)}
          </div>
        </div>
        {#if runPose === 'skid'}<div class="dust"></div>{/if}
      </div>
    {/if}
    {#if spot && !runner}
      <div
        class="tiny-shy"
        style="left: {spot.x}px; top: {spot.y}px; width: {spot.w}px; height: {spot.h}px;"
      >
        <button
          class="shy"
          class:is-hiding={shyState === 'hidden'}
          data-dir={spot.dir}
          style="transform: {shyTransform};"
          onclick={poke}
          aria-label="Tiny, the living platform, peeking out — click to hear a live fact"
          title="Tiny"
        >
          {@render botSprite(restingSprite)}
        </button>
        <button class="bot__close" onclick={dismiss} aria-label="Dismiss Tiny">×</button>
      </div>
    {/if}
  {:else}
    <div class="bot-wrap">
      {#if bubble}
        <div class="bubble" role="status">
          <span class="bubble__text">{bubble}</span>
        </div>
      {/if}
      <div class="bot">
        <button class="bot__close bot__close--corner" onclick={dismiss} aria-label="Dismiss Tiny">×</button>
        <button class="bot__hit" onclick={poke} aria-label="Tiny, the living platform — click to hear a live fact" title="Tiny">
          {@render botSprite(restingSprite)}
        </button>
      </div>
    </div>
  {/if}
{/if}

<style>
  /* The approved Work-pet atlas: 8 columns × 9 state rows, 192 × 208 per cell. */
  .sprite-frame {
    --sprite-scale: 0.458333;
    display: block;
    width: 88px;
    height: 95px;
    overflow: visible;
  }
  .tiny-sprite {
    display: block;
    width: 192px;
    height: 208px;
    background-image: url('/tiny-pet.png');
    background-repeat: no-repeat;
    background-size: 1536px 1872px;
    transform: scale(var(--sprite-scale));
    transform-origin: top left;
    will-change: background-position;
  }
  .sprite--idle {
    background-position-y: 0;
    animation: sprite-6 1.1s steps(6) infinite;
  }
  .sprite--run-right {
    background-position-y: -208px;
    animation: sprite-8 0.68s steps(8) infinite;
  }
  .sprite--run-left {
    background-position-y: -416px;
    animation: sprite-8 0.68s steps(8) infinite;
  }
  .sprite--wave {
    background-position-y: -624px;
    animation: sprite-4 0.8s steps(4) infinite;
  }
  .sprite--jump {
    background-position-y: -832px;
    animation: sprite-5 0.72s steps(5) infinite;
  }
  .sprite--failure {
    background-position-y: -1040px;
    animation: sprite-8 1s steps(8) infinite;
  }
  .sprite--waiting {
    background-position-y: -1248px;
    animation: sprite-6 1.35s steps(6) infinite;
  }
  .sprite--active-work {
    background-position-y: -1456px;
    animation: sprite-6 0.9s steps(6) infinite;
  }
  .sprite--review {
    background-position-y: -1664px;
    animation: sprite-6 1.2s steps(6) infinite;
  }
  @keyframes sprite-4 {
    to {
      background-position-x: -768px;
    }
  }
  @keyframes sprite-5 {
    to {
      background-position-x: -960px;
    }
  }
  @keyframes sprite-6 {
    to {
      background-position-x: -1152px;
    }
  }
  @keyframes sprite-8 {
    to {
      background-position-x: -1536px;
    }
  }

  /* ---------- shy mode: the hiding-spot window ---------- */
  .tiny-shy {
    position: fixed;
    z-index: 40;
    overflow: hidden;
    pointer-events: none;
  }
  .shy {
    pointer-events: auto;
    position: absolute;
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    line-height: 0;
    transition: transform 380ms cubic-bezier(0.34, 1.45, 0.42, 1);
    will-change: transform;
  }
  .shy.is-hiding {
    transition-duration: 170ms;
    transition-timing-function: cubic-bezier(0.5, 0, 0.9, 0.6);
  }
  .shy[data-dir='up'] {
    left: 50%;
    bottom: -2px;
    transform-origin: bottom center;
  }
  .shy[data-dir='left'] {
    right: -2px;
    top: 8px;
    transform-origin: bottom right;
  }
  .shy[data-dir='right'] {
    left: -2px;
    top: 8px;
    transform-origin: bottom left;
  }

  /* ---------- the runner: out in the open, little legs going ---------- */
  .tiny-runner {
    position: fixed;
    z-index: 40;
    pointer-events: none;
    width: 88px;
    height: 95px;
  }
  .runner-bob {
    animation: runbob 0.3s ease-in-out infinite;
  }
  .pant .runner-bob {
    animation: pantheave 0.55s ease-in-out infinite;
  }
  .skid .runner-bob {
    animation: none;
  }
  .runner-inner {
    line-height: 0;
    transform-origin: 50% 85%;
    will-change: transform;
  }
  @keyframes runbob {
    0%,
    100% {
      transform: translateY(0);
    }
    50% {
      transform: translateY(-4px);
    }
  }
  @keyframes pantheave {
    0%,
    100% {
      transform: translateY(0) scale(1, 1);
    }
    50% {
      transform: translateY(2px) scale(1.05, 0.93);
    }
  }
  .dust {
    position: absolute;
    bottom: 2px;
    left: 50%;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: rgba(28, 26, 20, 0.18);
    box-shadow:
      -11px 2px 0 -1px rgba(28, 26, 20, 0.14),
      9px 2px 0 -2px rgba(28, 26, 20, 0.12);
    animation: dustpuff 0.42s ease-out forwards;
  }
  @keyframes dustpuff {
    from {
      opacity: 1;
      transform: translate(-50%, 0) scale(0.6);
    }
    to {
      opacity: 0;
      transform: translate(-50%, -7px) scale(1.6);
    }
  }

  .bubble-float {
    position: fixed;
    z-index: 41;
    max-width: 250px;
    background: var(--ink-text-900);
    color: var(--paper-50);
    border-radius: 12px 12px 12px 3px;
    padding: 9px 13px;
    box-shadow: var(--shadow-md);
    animation: bubble-in 240ms var(--ease-summon);
    pointer-events: none;
  }
  .bubble-float.above {
    transform: translateY(-100%);
    border-radius: 12px 12px 3px 12px;
  }

  /* ---------- stationary mode (touch, reduced motion, asleep, error) ---------- */
  .bot-wrap {
    position: fixed;
    right: 18px;
    bottom: 14px;
    z-index: 40;
    display: grid;
    justify-items: end;
    gap: 6px;
    pointer-events: none;
  }
  .bubble {
    pointer-events: auto;
    max-width: 250px;
    background: var(--ink-text-900);
    color: var(--paper-50);
    border-radius: 12px 12px 3px 12px;
    padding: 9px 13px;
    box-shadow: var(--shadow-md);
    animation: bubble-in 260ms var(--ease-summon);
  }
  .bubble__text {
    font-family: var(--font-voice);
    font-style: italic;
    font-size: 14px;
    line-height: 1.45;
  }
  @keyframes bubble-in {
    from {
      opacity: 0;
      translate: 0 6px;
    }
    to {
      opacity: 1;
      translate: 0 0;
    }
  }

  .bot {
    pointer-events: auto;
    position: relative;
    line-height: 0;
  }
  .bot__hit {
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    line-height: 0;
  }

  .bot__close {
    position: absolute;
    top: 4px;
    right: 4px;
    width: 18px;
    height: 18px;
    border-radius: 999px;
    border: 1px solid var(--border-2);
    background: var(--paper-50);
    color: var(--fg-3);
    font-size: 12px;
    line-height: 1;
    cursor: pointer;
    opacity: 0;
    transition: opacity var(--dur-fast) var(--ease-standard);
    display: grid;
    place-items: center;
    padding: 0;
    pointer-events: auto;
    z-index: 2;
  }
  .tiny-shy:hover .bot__close,
  .bot:hover .bot__close {
    opacity: 1;
  }
  .bot__close:hover {
    color: var(--ember-700);
    border-color: var(--ember-700);
  }
  .bot__close--corner {
    top: 8px;
    right: -4px;
  }

  .peek {
    position: fixed;
    right: 0;
    bottom: 56px;
    z-index: 40;
    background: var(--paper-100);
    border: 1px solid var(--border-2);
    border-right: none;
    border-radius: 8px 0 0 8px;
    color: var(--ink-text-900);
    padding: 7px 8px 5px;
    cursor: pointer;
    box-shadow: var(--shadow-sm);
  }
  .peek:hover {
    background: var(--paper-200);
  }
  .peek__core {
    display: block;
    width: 32px;
    height: 35px;
    background: url('/tiny-pet.png') 0 0 / 256px 312px no-repeat;
  }

  @media (prefers-reduced-motion: reduce) {
    .tiny-sprite {
      animation: none !important;
    }
    .bubble,
    .bubble-float {
      animation: none;
    }
    .shy {
      transition: none;
    }
  }
  @media (max-width: 700px) {
    .bot-wrap {
      right: 10px;
      bottom: 10px;
    }
    .bubble {
      max-width: 200px;
    }
  }
</style>
