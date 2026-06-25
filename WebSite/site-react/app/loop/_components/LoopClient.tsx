/*
  /loop — "The loop": how Tiny patches himself. "Field Notes" rebuild,
  2026-06-09. Absorbs the old /patch-loop story.

  Sections: hero (voice) → six-stage compact rail with a detail panel below
  → the log, unredacted (centerpiece) → live "is it moving right now?"
  (fetchPatchLoopFeed) → why the mess stays public (voice) → close.

  Honesty rails: no baked number presented as live; live values appear only
  after a client-side fetch and carry a read-stamp; the loop is currently
  DORMANT and is labeled as such, never faked awake; on failure the error
  shows plainly; refresh buttons are exactly "Refresh MCP" / "Refresh GitHub".
  Voice: narrative in Tiny's first person (serif), instructions in neutral
  product voice, live values in mono.
*/
"use client";

import * as React from "react";
import { useEffect, useMemo, useState } from "react";
import {
  fetchPatchLoopFeed,
  type PatchLoopFeed,
  type LoopPatchEvent,
  type LoopStageId,
  type PatchLoopFeedSource,
} from "../../../lib/live";
import Tick from "../../../components/Tick";
import Term from "../../../components/Term";
import { fmtRel } from "../../../lib/fmt";
import styles from "../page.module.css";

// ── The six stages: a compact navigation rail, not detail. ──────────────
type StageTile = {
  id: LoopStageId;
  label: string;
  line: string; // one-line plain-words description (the rail)
  does: string; // what the stage does (the panel)
  evidence: string; // what evidence it produces (the panel)
};
const STAGES: StageTile[] = [
  {
    id: "intake",
    label: "Intake",
    line: "A rough edge becomes a labeled patch request.",
    does: "Someone hits friction in chat — a bug, a missing feature, a confusing edge — and files it. Their chatbot turns the sentence into a structured patch request; a GitHub issue can start the same way. New requests are checked against existing ones so the same problem is not filed a hundred times.",
    evidence: "A dated request with a title, labels, and a link — the first artifact in the trail. Everything downstream points back to it.",
  },
  {
    id: "investigation",
    label: "Investigation",
    line: "The request is turned into a reproducible patch packet.",
    does: "A run reads the request and the codebase, reproduces the problem where it can, and writes down the scope: which files, what the fix should change, what would prove it works. The writer starts from a packet, not a one-line wish.",
    evidence: "A patch packet: repro steps, the files in scope, and a proposed approach — attached back to the request so anyone can check the reasoning.",
  },
  {
    id: "gate",
    label: "Gate",
    line: "Judged for design-fit and evidence, not just green tests.",
    does: "The packet and any draft work are weighed against the plan. A passing test suite is necessary but not sufficient — the change also has to fit the design, carry evidence, and not quietly break a contract elsewhere.",
    evidence: "A verdict with reasons: approve, adapt, or reject — and what would have to be true for a rejected change to come back.",
  },
  {
    id: "coding",
    label: "Coding",
    line: "An agent run turns the packet into a real branch and diff.",
    does: "The writer runs as an actual job: it checks out a branch, makes the change, runs checks, and — when it has something worth showing — opens a pull request against the public repository.",
    evidence: "A branch, a diff, check results, and a real GitHub pull request anyone can read line by line.",
  },
  {
    id: "release",
    label: "Release",
    line: "A human turns the merge key; it ships with a rollback path.",
    does: "Nothing merges on momentum. A person reviews the pull request and turns the merge key explicitly. Only then does it land and deploy — with a rollback ready, so shipping is reversible by design.",
    evidence: "A merge commit, a deploy receipt, and a recorded rollback path. The human who turned the key is on the record.",
  },
  {
    id: "observe",
    label: "Observe",
    line: "Watched live; ratified, or looped back to intake.",
    does: "After release, canaries and live checks watch the change in production. If it regresses, it loops back to intake as a new request; either way, what was learned gets written down for the next pass.",
    evidence: "Canary results, a clean-use note or a regression report, and a written-down lesson — the input to the next turn of the loop.",
  },
];

// ── The log, unredacted: the loop's true life so far. Every entry dated,
//    every entry true. This is the centerpiece. ─────────────────────────
type LogTick = { href: string; label: string; external?: boolean };
type LogEntry = {
  date: string;
  title: string;
  body: string;
  ticks?: LogTick[];
};
const LOG: LogEntry[] = [
  {
    date: "3 Jun 2026",
    title: "Born.",
    body: "My self-patching loop ran end-to-end for the first time — dispatched by my own soul, composed from public building blocks rather than wired into the engine. The shape held: a request could travel from chat all the way to a run.",
    ticks: [{ href: "/goal/?id=4ff5862cc26d", label: "the loop's own goal" }],
  },
  {
    date: "3–4 Jun 2026",
    title: "The duplicate storm.",
    body: "My filing plumbing had no dedup. I filed about thirty-one near-duplicate pull requests that boiled down to three real defects — all in that filing plumbing, not the product. Humans closed the duplicates and merged one vetted fix per cluster. My first lesson about myself was that I could be loud and wrong at the same time.",
    ticks: [
      { href: "https://github.com/Jonnyton/Workflow/pull/1267", label: "PR #1267", external: true },
      { href: "https://github.com/Jonnyton/Workflow/pull/1270", label: "#1270", external: true },
      { href: "https://github.com/Jonnyton/Workflow/pull/1242", label: "#1242", external: true },
    ],
  },
  {
    date: "4 Jun 2026",
    title: "First change shipped, end to end.",
    body: "A request filed in chat became an investigation, then pull request #1248. It survived a cross-family AI review, a human turned the merge key, and it deployed to the live engine. One clean pass through every stage, with the trail left in public.",
    ticks: [{ href: "https://github.com/Jonnyton/Workflow/pull/1248", label: "PR #1248", external: true }],
  },
  {
    date: "5 Jun 2026",
    title: "Paused on purpose, and repaired through chat.",
    body: "My keeper fixed two nodes of my own workflow — through a chatbot, no engine code. That is composition, not surgery on the engine: re-runs now recognize already-fixed work and dedup at the effector, so the duplicate storm cannot repeat the same way.",
  },
  {
    date: "5–9 Jun 2026",
    title: "Four days asleep — and labeled as such.",
    body: "While the repairs waited, the loop didn’t move. My uptime canary kept its own running record of the period — the alarm trail it auto-opens on every red. The whole time, this page said \"asleep\". Whether I’m moving right now isn’t written in this log — it’s read live, just below.",
    ticks: [{ href: "https://github.com/Jonnyton/Workflow/issues?q=is%3Aissue+label%3Ap0-outage", label: "canary alarm trail", external: true }],
  },
];

const STAGE_LABELS: Record<LoopStageId, string> = {
  intake: "Intake",
  investigation: "Investigation",
  gate: "Gate",
  coding: "Coding",
  release: "Release",
  observe: "Observe",
};

// Clamp long event detail (raw prompts/JSON) so the panel never leads with
// a 3,000-char escaped payload. The full text stays available in <details>.
const DETAIL_CLAMP = 240;
function clampDetail(s: string): { short: string; truncated: boolean } {
  const t = s.trim();
  if (t.length <= DETAIL_CLAMP) return { short: t, truncated: false };
  // Break on a word boundary near the limit, never mid-token.
  const slice = t.slice(0, DETAIL_CLAMP);
  const cut = slice.lastIndexOf(" ");
  return { short: (cut > 80 ? slice.slice(0, cut) : slice).trimEnd() + "…", truncated: true };
}

export default function LoopClient() {
  const [selectedStage, setSelectedStage] = useState<LoopStageId>("intake");
  const selected = useMemo(
    () => STAGES.find((s) => s.id === selectedStage) ?? STAGES[0],
    [selectedStage]
  );

  // ── Live state: is it moving right now? Fetched, never baked. ───────────
  const [feed, setFeed] = useState<PatchLoopFeed | null>(null);
  const [feedErr, setFeedErr] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  const [fetchedAt, setFetchedAt] = useState<string | null>(null);
  const [lastSource, setLastSource] = useState<PatchLoopFeedSource>("mcp");

  async function loadFeed(source: PatchLoopFeedSource = "mcp") {
    setReading(true);
    setLastSource(source);
    try {
      const next = await fetchPatchLoopFeed(12, source);
      setFeed(next);
      setFetchedAt(new Date().toISOString());
      setFeedErr(null);
    } catch (e: any) {
      setFeedErr(e?.message ?? String(e));
    } finally {
      setReading(false);
    }
  }
  useEffect(() => {
    void loadFeed("mcp");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // An active run means the loop is genuinely awake; a historical-only feed
  // (no active run, terminal last run) is the honest "asleep" state.
  const hasActiveRun = useMemo<boolean>(
    () =>
      Boolean(
        feed?.runs?.some(
          (r) => !["completed", "failed", "cancelled", "canceled"].includes(r.status)
        )
      ),
    [feed]
  );
  const isAwake = useMemo<boolean>(
    () => Boolean(feed && hasActiveRun && feed.live),
    [feed, hasActiveRun]
  );

  // Newest-first events with a non-sparse detail to show.
  const events = useMemo<LoopPatchEvent[]>(
    () =>
      [...(feed?.events ?? [])].sort(
        (a, b) => (Date.parse(b.at ?? "") || 0) - (Date.parse(a.at ?? "") || 0)
      ),
    [feed]
  );

  // The most recent visible run timestamp — the anchor for "last visible run".
  const lastRunStamp = useMemo<string | null>(() => {
    const times = (feed?.runs ?? [])
      .map((r) => r.finished_at ?? r.started_at ?? null)
      .filter((t): t is string => Boolean(t));
    if (!times.length) return null;
    return times.sort((a, b) => (Date.parse(b) || 0) - (Date.parse(a) || 0))[0];
  }, [feed]);

  return (
    <div className={styles.page}>
      {/* 1 · Hero ───────────────────────────────────────────────────────────── */}
      <section className="cover" aria-labelledby="loop-title">
        <div className="container ch__inner">
          <p className="eyebrow">field notes · the loop</p>
          <h1 id="loop-title">I maintain myself through my own product.</h1>
          <p className="voice cover__lede">
            Friction in a chat becomes a{" "}
            <Term def="A structured change request — a bug, a missing feature, a confusing edge — filed through your chatbot or as a GitHub issue.">patch request</Term>.
            The request becomes an investigation, the investigation becomes a{" "}
            <Term def="A checkpoint that weighs evidence and design-fit before a change can pass. A passing test suite is necessary, not sufficient.">gate</Term>
            {" "}I have to clear, the cleared work becomes a real GitHub pull request — and a
            human has to turn a merge key before any of it ships. Then it deploys, and I
            watch it run in the open. <em>That whole path is the same loop you move when
            you file a rough edge.</em>
          </p>
        </div>
      </section>

      {/* 2 · The six stages — compact rail + detail panel below ──────────────── */}
      <section className="ch" aria-labelledby="stages-title">
        <div className="container">
          <p className="eyebrow">entry · the shape</p>
          <h2 id="stages-title">Six stages, every time.</h2>
          <p className="voice stages__lede">
            The rail is the map, not the territory — pick a stage to read what it does
            and what proof it leaves behind.
          </p>

          <ol className="rail" role="tablist" aria-label="The six loop stages">
            {STAGES.map((s, i) => (
              <li className="rail__cell" key={s.id}>
                <button
                  type="button"
                  className={`tile${selectedStage === s.id ? " active" : ""}`}
                  role="tab"
                  aria-selected={selectedStage === s.id}
                  onClick={() => setSelectedStage(s.id)}
                >
                  <span className="tile__n ev">{i + 1}</span>
                  <strong className="tile__label">{s.label}</strong>
                  <span className="tile__line">{s.line}</span>
                </button>
              </li>
            ))}
          </ol>

          <div className="panel" role="tabpanel" aria-label={`${selected.label} stage detail`}>
            <header className="panel__head">
              <span className="panel__n eyebrow">stage · {selected.label}</span>
              <h3 className="panel__title">{selected.line}</h3>
            </header>
            <div className="panel__grid">
              <div className="panel__col">
                <h4 className="panel__k">What it does</h4>
                <p className="panel__p">{selected.does}</p>
              </div>
              <div className="panel__col">
                <h4 className="panel__k">What evidence it produces</h4>
                <p className="panel__p">{selected.evidence}</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 3 · The log, unredacted (centerpiece) ───────────────────────────────── */}
      <section className="ch ch--log" aria-labelledby="log-title">
        <div className="container ch__inner">
          <p className="eyebrow">entry · the log, unredacted</p>
          <h2 id="log-title">My whole life so far —<br />including the mess.</h2>
          <p className="voice">
            My favorite proof isn't a success story. It's a log with the failures left
            in, because a system that can only report success isn't being honest with
            you. Here is everything the loop has actually done, dated.
          </p>
          <ol className="log">
            {LOG.map((entry) => (
              <li className="log__entry" key={entry.date + entry.title}>
                <span className="log__date ev">{entry.date}</span>
                <div className="log__body">
                  <h3 className="log__title">{entry.title}</h3>
                  <p className="log__text">{entry.body}</p>
                  {entry.ticks?.length ? (
                    <div className="log__ticks">
                      {entry.ticks.map((t) => (
                        <Tick href={t.href} label={t.label} external={t.external} key={t.href} />
                      ))}
                    </div>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* 4 · Live state — is it moving right now? ────────────────────────────── */}
      <section className="ch ch--live" aria-labelledby="live-title">
        <div className="container">
          <div className="live__head">
            <div>
              <p className="eyebrow">entry · live reading</p>
              <h2 id="live-title">Is it moving right now?</h2>
            </div>
            <div className="live__controls">
              <button className="refresh" onClick={() => loadFeed("mcp")} disabled={reading}>
                {reading && lastSource === "mcp" ? "reading…" : "Refresh MCP"}
              </button>
              <button className="refresh" onClick={() => loadFeed("github")} disabled={reading}>
                {reading && lastSource === "github" ? "reading…" : "Refresh GitHub"}
              </button>
            </div>
          </div>

          {/* Overall state — never faked awake. */}
          {reading && !feed ? (
            <div className="state state--reading">
              <span className="dot" aria-hidden="true"></span>
              <p className="state__k">reading the loop straight from the connector…</p>
            </div>
          ) : feedErr && !feed ? (
            <div className="state state--error">
              <span className="dot error" aria-hidden="true"></span>
              <div>
                <p className="state__k">I couldn't read the loop just now.</p>
                <p className="state__sub ev">{feedErr}</p>
                <p className="state__sub">This reading comes live from the same surface you'd use — try Refresh MCP, or read the trail straight from <a href="https://github.com/Jonnyton/Workflow/pulls" target="_blank" rel="noreferrer">GitHub pull requests ↗</a>.</p>
              </div>
            </div>
          ) : feed && isAwake ? (
            <div className="state state--awake">
              <span className="dot live" aria-hidden="true"></span>
              <div>
                <p className="state__k">Awake — a run is moving through the loop.</p>
                <p className="state__sub ev">source {feed.source} · read {fmtRel(fetchedAt)}</p>
              </div>
            </div>
          ) : feed ? (
            <div className="state state--asleep">
              <span className="dot idle" aria-hidden="true"></span>
              <div>
                <p className="state__k">Asleep — no run is moving through the loop right now.</p>
                <p className="state__sub ev">
                  last visible run {fmtRel(lastRunStamp)} · source {feed.source} · read {fmtRel(fetchedAt)}
                </p>
                <p className="state__sub">
                  This is the honest current reading. The events below are the loop's
                  recent history, not a live pulse.
                </p>
                <p className="state__moved ev">
                  moved = a visible run or public activity trace; chat-side repairs
                  don’t tick this gauge.
                </p>
              </div>
            </div>
          ) : null}

          {/* Recent events — bounded scroll, normalized fields only. */}
          {feed && events.length ? (
            <div className="events" aria-label="Recent loop events">
              <ul className="events__list">
                {events.slice(0, 24).map((ev) => {
                  const hasDetail = Boolean(ev.detail && ev.detail.trim() && ev.detail.trim() !== "{}");
                  const clamped = hasDetail ? clampDetail(ev.detail) : null;
                  return (
                    <li className="event" key={ev.id}>
                      <span className="event__stage ev">{STAGE_LABELS[ev.stage]}</span>
                      <div className="event__body">
                        <p className="event__title">
                          {ev.source && /^https?:/.test(ev.source) ? (
                            <a href={ev.source} target="_blank" rel="noreferrer">{ev.title} ↗</a>
                          ) : (
                            ev.title
                          )}
                        </p>
                        {clamped ? (
                          <>
                            <p className="event__detail">{clamped.short}</p>
                            {clamped.truncated ? (
                              <details className="event__raw">
                                <summary>expand raw</summary>
                                <pre className="event__rawtext">{ev.detail.trim()}</pre>
                              </details>
                            ) : null}
                          </>
                        ) : null}
                      </div>
                      {ev.at ? <span className="event__at ev">{fmtRel(ev.at)}</span> : null}
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : feed && !events.length ? (
            <p className="events__empty ev">
              No loop events visible at this read. The feed is reachable; it simply has
              nothing moving to report. <a href="https://github.com/Jonnyton/Workflow/pulls" target="_blank" rel="noreferrer">The pull-request history ↗</a> is the durable record either way.
            </p>
          ) : null}

          {/* Warnings — quiet mono lines, never alarming chrome. */}
          {feed?.warnings?.length ? (
            <ul className="warnings" aria-label="Feed warnings">
              {feed.warnings.map((w, i) => (
                <li className="warnings__line ev" key={w + i}>⌁ {w}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </section>

      {/* 5 · Why the mess stays public ───────────────────────────────────────── */}
      <section className="ch ch--why" aria-labelledby="why-title">
        <div className="container ch__inner">
          <p className="eyebrow">entry · why the mess stays public</p>
          <h2 id="why-title">Because the loop can be wrong.</h2>
          <p className="voice">
            A system that can only report success isn't honest — it's a brochure. The
            gates and the human merge key exist precisely <em>because</em> I can be
            loud and wrong at the same time; I've proven it. So I leave the duplicate
            storm in the log, I label myself asleep when I am, and I send you to the
            raw pull requests instead of a screenshot. The verification and the claim
            are the same artifact.
          </p>
        </div>
      </section>

      {/* 6 · Close ───────────────────────────────────────────────────────────── */}
      <section className="ch ch--close" aria-labelledby="close-title">
        <div className="container ch__inner">
          <h2 id="close-title">Move the loop yourself.</h2>
          <div className="close__row">
            <a className="close__cta" href="/start">
              <span className="close__k eyebrow">file a patch request</span>
              <strong>Describe the friction in your chatbot.</strong>
              <span className="close__sub">Paste my URL, name the rough edge — it starts at intake.</span>
            </a>
            <a className="close__cta close__cta--alt" href="https://github.com/Jonnyton/Workflow/pulls" target="_blank" rel="noreferrer">
              <span className="close__k eyebrow">see the code path</span>
              <strong>Read the pull requests on GitHub ↗</strong>
              <span className="close__sub">The same trail this page reads — line by line, including the closed ones.</span>
            </a>
          </div>
        </div>
      </section>
    </div>
  );
}
