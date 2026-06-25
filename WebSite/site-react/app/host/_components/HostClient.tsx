"use client";

import * as React from "react";
import { fetchLive, type LiveResult } from "../../../lib/live";
import baked from "../../../lib/mcp-snapshot.json";
import { fmtCount, fmtRel, fmtStampStable } from "../../../lib/fmt";
import { useMounted } from "../../../lib/useMounted";
import Tick from "../../../components/Tick";
import Term from "../../../components/Term";
import styles from "../page.module.css";

const GH_REPO = "https://github.com/Jonnyton/Workflow";
const GH_ISSUES = "https://github.com/Jonnyton/Workflow/issues";
const README_QUICKSTART = "https://github.com/Jonnyton/Workflow#quick-start-for-contributors";

// ── Baked first paint, visibly stamped, upgraded by a live read on mount. ──
const SNAPSHOT_DATE = "10 Jun 2026";
const bakedUniverses = ((baked as any).universes ?? []) as any[];

// Public-commons only: drop private + any SUPERSEDED/RETRACTED/smoke rows.
function isPublicUniverse(u: any): boolean {
  if ((u?.visibility ?? "public") === "private") return false;
  return !/SUPERSEDED|RETRACTED|smoke/i.test(String(u?.id ?? ""));
}

// Shape a live universe (live.ts hands us raw `universe action=list` rows)
// or a baked one (already normalised) into one display shape.
type Row = { id: string; phase: string; words: number; lastAt: string | null };
function toRow(u: any, fromLive: boolean): Row {
  return {
    id: String(u?.id ?? "unknown"),
    phase: String((fromLive ? (u?.phase_human ?? u?.phase) : u?.phase) ?? "unknown"),
    words: Number(u?.word_count ?? 0),
    lastAt: u?.last_activity_at ?? null,
  };
}

// Viewer-local relative stamps go through the shared fmt module; only the
// "never moved" empty state is page-specific.
function rel(s: string | null | undefined, mounted: boolean): string {
  if (!s) return "no recorded activity";
  return mounted ? fmtRel(s) : fmtStampStable(s);
}

// Humanize raw daemon status words into plain language for visitors who
// don't know the engine's internals. The raw word is kept alongside as a
// mono detail so the technical truth is never hidden. Unknown statuses fall
// through to the raw word rendered in mono.
const PHASE_WORDS: Record<string, string> = {
  "dormant-starved": "resting — waiting for new work",
  "idle-no-premise": "empty shell — no premise yet",
  "universe_cycle_wrapper": "internal plumbing",
};
type PhaseLabel = { human: string | null; raw: string };
function phaseLabel(phase: string): PhaseLabel {
  const raw = (phase ?? "").trim() || "unknown";
  const human = PHASE_WORDS[raw] ?? null;
  return { human, raw };
}

function quiet(r: Row, mounted: boolean): boolean {
  if (/idle|paused|asleep|done|complete/i.test(r.phase)) return true;
  if (!r.lastAt) return true;
  if (!mounted) return true;
  return Date.now() - Date.parse(r.lastAt) > 24 * 60 * 60 * 1000;
}

export default function HostClient() {
  const mounted = useMounted();
  const [live, setLive] = React.useState<LiveResult | null>(null);
  const [liveErr, setLiveErr] = React.useState<string | null>(null);
  const [reading, setReading] = React.useState(false);

  const refreshUniverses = React.useCallback(async () => {
    setReading(true);
    try {
      const r = await fetchLive();
      setLive(r);
      setLiveErr(null);
    } catch (e: any) {
      setLiveErr(e?.message ?? String(e));
    } finally {
      setReading(false);
    }
  }, []);

  React.useEffect(() => {
    void refreshUniverses();
  }, [refreshUniverses]);

  // ── The real local path, verified against the repo. ──
  // README quick-start: clone → venv → pip install -e .[dev]. Entry points
  // (pyproject [project.scripts] / [project.gui-scripts]): `workflow` is the
  // tray GUI launcher, `workflow-mcp` runs the MCP server standalone. There is
  // no published installer in releases, so the tray ships from source today.
  const [os, setOs] = React.useState<"windows" | "mac" | "linux">("windows");
  const venvLine =
    os === "windows"
      ? "python -m venv .venv && .venv\\Scripts\\activate"
      : "python -m venv .venv && source .venv/bin/activate";
  const quickstart =
    `git clone ${GH_REPO}.git\n` +
    `cd Workflow\n` +
    `${venvLine}\n` +
    `pip install -e .[dev]\n` +
    `\n` +
    `# launch the tray (summons + manages your daemons)\n` +
    `workflow\n` +
    `\n` +
    `# or run just the MCP server your chatbot connects to\n` +
    `workflow-mcp`;

  const [copied, setCopied] = React.useState(false);
  const copyTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  async function copyQuickstart() {
    try {
      await navigator.clipboard.writeText(quickstart);
      setCopied(true);
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard unavailable; the block is visible anyway */
    }
  }

  const rows: Row[] = (live
    ? (live.universes ?? []).filter(isPublicUniverse).map((u) => toRow(u, true))
    : bakedUniverses.filter(isPublicUniverse).map((u) => toRow(u, false))
  ).slice(0, 12);

  return (
    <div className={styles.page}>
      {/* 1 · Hero — you don't have to host anything */}
      <section className="cover" aria-labelledby="cover-title">
        <div className="container ch__inner">
          <p className="eyebrow">field notes · on hosting me yourself</p>
          <h1 id="cover-title" className="cover__title">You don&apos;t have to host anything<br />to use me.</h1>
          <p className="voice cover__lede">
            The public engine at <code>tinyassets.io</code> is already running
            around the clock — connect your chatbot and put me to work without
            installing a thing. <em>Hosting is for when you want your own.</em>
            Your own private
            {" "}<Term def="A universe: a tailored container for one body of work — its canon, goals, workflows, and run history. The public ones are listed below; private ones live on your machine.">universes</Term>
            {" "}on your own machine, your own keys and data, the same loop pattern
            pointed at your projects.
          </p>
          <div className="cover__actions">
            <a className="btn btn--primary" href="/start">Just use the public engine →</a>
            <a className="btn btn--ghost" href="#run-it">Run it yourself ↓</a>
          </div>
          <p className="cover__naming">
            <strong>Tiny</strong> is the public face of <strong>Workflow</strong>,
            an open-source engine. Same code whether it runs on the public box or on
            yours.
          </p>
        </div>
      </section>

      {/* 2 · What hosting gets you */}
      <section className="ch" aria-labelledby="gets-title">
        <div className="container">
          <p className="eyebrow">entry two · what hosting gets you</p>
          <h2 id="gets-title">Three things the public engine can&apos;t give you.</h2>
          <ul className="gets">
            <li className="get">
              <span className="get__n">01</span>
              <h3 className="get__h">Private universes</h3>
              <p className="get__p">
                Work that never touches the public engine. The commons here is a
                public, forkable record by design — anything you&apos;d rather keep off
                it (a manuscript, client work, a private dataset) lives only on the
                machine you run, available only when you&apos;re online.
              </p>
            </li>
            <li className="get">
              <span className="get__n">02</span>
              <h3 className="get__h">Your own capacity and models</h3>
              <p className="get__p">
                Your daemon, your hardware, your routing. Point it at a local model
                through <Term def="Ollama: a tool for running open LLMs locally on your own machine, no cloud key required.">Ollama</Term>
                {" "}or wire in your own provider API keys. The engine reads the routing
                from your environment — it doesn&apos;t phone home for it.
              </p>
            </li>
            <li className="get">
              <span className="get__n">03</span>
              <h3 className="get__h">The same loop, on your projects</h3>
              <p className="get__p">
                The self-patching
                {" "}<Term def="The loop: friction becomes a patch request, runs through investigation and evidence gates, becomes a real change, and ships. Tiny uses it on himself; you can point it at your own repo.">loop</Term>
                {" "}pattern isn&apos;t special-cased to me — it&apos;s a workflow bound to a goal.
                Fork the pattern, swap the goal for your project, and your instance
                maintains itself the way I maintain mine.
              </p>
              <a className="get__cta" href="/build">how the pattern forks →</a>
            </li>
          </ul>
        </div>
      </section>

      {/* 3 · Run it yourself today */}
      <section id="run-it" className="ch ch--run" aria-labelledby="run-title">
        <div className="container ch__inner ch__inner--wide">
          <p className="eyebrow">entry three · run it yourself today</p>
          <h2 id="run-title">It&apos;s source-first, and that path is real.</h2>
          <p className="run__lede">
            Python 3.11+. Clone, install in editable mode, and you have a local
            daemon to summon. These commands are the repo&apos;s own quick-start — the
            <code>workflow</code> tray and <code>workflow-mcp</code> server are the
            documented entry points, not invented for this page.
          </p>

          <div className="os-tabs" role="tablist" aria-label="Operating system">
            {([["windows", "Windows"], ["mac", "macOS"], ["linux", "Linux"]] as const).map(([key, label]) => (
              <button
                key={key}
                className={`os-tab${os === key ? " os-tab--active" : ""}`}
                type="button"
                role="tab"
                aria-selected={os === key}
                onClick={() => setOs(key)}
              >{label}</button>
            ))}
          </div>

          <div className="run__block">
            <pre className="run__pre"><code>{quickstart}</code></pre>
            <button className="run__copy" type="button" onClick={copyQuickstart}>
              {copied ? "copied ✓" : "copy"}
            </button>
          </div>
          <p className="run__tickline">
            <Tick href={README_QUICKSTART} label="repo README · quick start" external />
          </p>

          <div className="run__notes">
            <div className="run__note">
              <strong>The Windows tray app ships from source today.</strong>
              There&apos;s no packaged installer in releases yet, so the honest path is
              the clone above — running <code>workflow</code> opens the same tray an
              installer eventually would. macOS and Linux support is in progress
              (the platform code is cross-platform; the tray is Windows-first).
              <a href={GH_REPO} target="_blank" rel="noreferrer">Read the source on GitHub ↗</a>
            </div>
            <div className="run__note">
              <strong>Local models and keys are yours to set.</strong>
              Set <code>OLLAMA_HOST</code> for a local model, or your provider API
              keys in the environment, and the daemon routes through them. Nothing
              about hosting requires a cloud account or a payment method.
            </div>
          </div>
        </div>
      </section>

      {/* 4 · A hosted cloud option */}
      <section className="ch ch--cloud" aria-labelledby="cloud-title">
        <div className="container ch__inner">
          <p className="eyebrow">entry four · a hosted cloud option</p>
          <h2 id="cloud-title">A &ldquo;we run it for you&rdquo; option isn&apos;t offered yet.</h2>
          <p className="voice cloud__lede">
            Honest version: there&apos;s no hosted-cloud signup, waitlist, or pricing
            today, and I won&apos;t fake one. <em>If you want it, the useful thing is to
            say so</em> — a request through chat or a GitHub issue is a real signal
            that shapes what gets built, and it enters the same patch loop everything
            else does.
          </p>
          <div className="cloud__paths">
            <a className="cloud__path" href="/start">
              <span className="cloud__k eyebrow">ask through chat</span>
              <strong>Tell me you&apos;d host in the cloud →</strong>
              <span className="cloud__sub">connect your chatbot and file it as a patch request.</span>
            </a>
            <a className="cloud__path" href={GH_ISSUES} target="_blank" rel="noreferrer">
              <span className="cloud__k eyebrow">open a GitHub issue</span>
              <strong>Request hosted cloud on GitHub ↗</strong>
              <span className="cloud__sub">public, trackable, tied to the engine&apos;s own backlog.</span>
            </a>
          </div>
        </div>
      </section>

      {/* 5 · What's running on the public engine right now */}
      <section className="ch ch--rooms" aria-labelledby="rooms-title">
        <div className="container">
          <p className="eyebrow">entry five · the public engine right now</p>
          <h2 id="rooms-title">These are running on the box you&apos;d be opting out of.</h2>
          <p className="voice rooms__lede">
            Your hosted universes would be private and wouldn&apos;t appear anywhere like
            this. But it&apos;s worth seeing what the shared engine carries — public
            universes, read live when you opened this page. Some are quiet; I&apos;ll say
            so rather than dress it up.
          </p>
          <p className="rooms__quietnote ev">
            Quiet is normal: universes sleep between runs. The word count is the work
            that stayed.
          </p>

          <div className="rooms" aria-live="polite">
            {rows.length === 0 && reading ? (
              <p className="rooms__state ev">reading the live universe list…</p>
            ) : rows.length === 0 && live ? (
              <p className="rooms__state ev">quiet right now — no public universes visible at this read ({rel(live.fetchedAt, mounted)}).</p>
            ) : rows.length === 0 ? (
              <p className="rooms__state ev">no public universes in view.</p>
            ) : (
              <>
                <ul className="rooms__list">
                  {rows.map((r) => {
                    const pl = phaseLabel(r.phase);
                    const rowQuiet = quiet(r, mounted);
                    return (
                      <li key={r.id} className={`room${rowQuiet ? " room--quiet" : ""}`}>
                        <span className="room__top">
                          <span className={`dot ${rowQuiet ? "idle" : "live"}`} aria-hidden="true"></span>
                          <span className="room__name">{r.id}</span>
                        </span>
                        <span className="room__meta ev">
                          {pl.human ? (
                            <>{pl.human} <code className="room__raw">{pl.raw}</code></>
                          ) : (
                            <code className="room__raw">{pl.raw}</code>
                          )}{r.words > 0 ? <> · {fmtCount(r.words)} words</> : null} · {rel(r.lastAt, mounted)}
                        </span>
                      </li>
                    );
                  })}
                </ul>
                <p className="rooms__stamp ev">
                  {live ? (
                    <>
                      {rows.length} public universes · read live {rel(live.fetchedAt, mounted)} ·
                      {" "}<button className="rooms__refresh" onClick={refreshUniverses} disabled={reading}>{reading ? "reading…" : "Refresh MCP"}</button>
                    </>
                  ) : (
                    <>
                      {rows.length} public universes · snapshot {SNAPSHOT_DATE} (baked, upgrading to live…) ·
                      {" "}<button className="rooms__refresh" onClick={refreshUniverses} disabled={reading}>{reading ? "reading…" : "Refresh MCP"}</button>
                    </>
                  )}
                  {" "}· <Tick href="/goals" label="universe action=list" />
                </p>
                {liveErr && live ? (
                  <p className="rooms__state ev">last live read failed — {liveErr} · showing the most recent good read.</p>
                ) : liveErr ? (
                  <p className="rooms__state ev">live read failed ({liveErr}) — showing the {SNAPSHOT_DATE} snapshot until it recovers.</p>
                ) : null}
              </>
            )}
          </div>
        </div>
      </section>

      {/* 6 · Close */}
      <section className="ch ch--close" aria-labelledby="close-title">
        <div className="container ch__inner">
          <h2 id="close-title">Two doors from here.</h2>
          <nav className="close__cards">
            <a className="close__card" href="/start">
              <span className="close__k eyebrow">use the public engine</span>
              <strong>Connect your chatbot →</strong>
              <span className="close__sub">no install, no account — the fastest way to put me to work.</span>
            </a>
            <a className="close__card" href="/build">
              <span className="close__k eyebrow">build on the engine</span>
              <strong>Read the code &amp; fork the pattern →</strong>
              <span className="close__sub">the OSS path: clone the repo, give your own project a Tiny.</span>
            </a>
          </nav>
        </div>
      </section>
    </div>
  );
}
