/*
  /goals — the living board of what's being worked on. "Field Notes"
  rebuild, 2026-06-09.

  Crawl fixes applied: jargon wall removed (goal / workflow / ladder each
  get a first-use <Term>; "commons records", "branch signals", "canon-gate",
  "Goal lens" all dropped). No repo-internals readouts — the old
  "GitHub source: local git checkout" leak is gone entirely. The board is
  not empty without JS: it paints from the baked snapshot immediately,
  visibly stamped with its fetched date, then upgrades to a live read on
  mount. Every live value carries a read-stamp; baked is labelled baked.
  Public-commons only: private / SUPERSEDED / RETRACTED / smoke filtered out.
*/
"use client";

import * as React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { callTool } from "../../../lib/live";
import bakedMcp from "../../../lib/mcp-snapshot.json";
import { fmtDate, fmtRel } from "../../../lib/fmt";
import Ladder from "../../../components/Ladder";
import Term from "../../../components/Term";
import Tick from "../../../components/Tick";

// ── A board goal, normalized from either the baked snapshot or a live read.
type Rung = { key?: string; name: string; description?: string; lit?: boolean; evidence_url?: string };
type BoardGoal = {
  id: string;
  name: string;
  description: string;
  tags: string[];
  visibility: string;
  rungs: Rung[];
  updatedMs: number | null;
};

// Public-commons rail: nothing private, nothing retired, no smoke tests.
function isPublicGoal(name: string, visibility: string): boolean {
  if ((visibility ?? "public").toLowerCase() === "private") return false;
  return !/SUPERSEDED|RETRACTED|smoke/i.test(name ?? "");
}

function toTags(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.map((t) => String(t).trim()).filter(Boolean);
  if (typeof raw === "string") return raw.split(",").map((t) => t.trim()).filter(Boolean);
  return [];
}

// Live goals carry a gate_ladder of {name, rung_key, description}. No rung
// arrives with evidence attached today, so every rung renders unlit — that
// is the honest state, and the section copy owns it.
function toRungs(raw: unknown): Rung[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((r: any) => ({
      key: r?.rung_key ?? r?.key ?? r?.name,
      name: String(r?.name ?? r?.rung_key ?? "").trim(),
      description: r?.description ? String(r.description) : undefined,
      // A rung only lights with a real evidence URL; absent one, unlit.
      lit: Boolean(r?.lit && r?.evidence_url),
      evidence_url: r?.evidence_url ?? undefined,
    }))
    .filter((r) => r.name);
}

// Live timestamps are Unix epoch SECONDS (floats); baked goals carry none.
function toMs(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value * 1000;
  if (typeof value === "string") {
    const n = Number(value);
    if (Number.isFinite(n) && n > 0) return n * 1000;
    const p = Date.parse(value);
    if (!Number.isNaN(p)) return p;
  }
  return null;
}

function normalizeBaked(raw: any): BoardGoal[] {
  return (raw?.goals ?? [])
    .filter((g: any) => isPublicGoal(g.name, g.visibility))
    .map((g: any) => ({
      id: String(g.id ?? g.goal_id ?? ""),
      name: String(g.name ?? ""),
      // Baked snapshot calls the body "summary"; live calls it "description".
      description: String(g.summary ?? g.description ?? ""),
      tags: toTags(g.tags),
      visibility: String(g.visibility ?? "public"),
      rungs: toRungs(g.gate_ladder),
      updatedMs: toMs(g.updated_at ?? g.created_at),
    }));
}

function normalizeLive(raw: any): BoardGoal[] {
  return (raw?.goals ?? [])
    .filter((g: any) => isPublicGoal(g.name, g.visibility))
    .map((g: any) => ({
      id: String(g.goal_id ?? g.id ?? ""),
      name: String(g.name ?? ""),
      description: String(g.description ?? g.summary ?? ""),
      tags: toTags(g.tags),
      visibility: String(g.visibility ?? "public"),
      rungs: toRungs(g.gate_ladder),
      updatedMs: toMs(g.updated_at ?? g.created_at),
    }))
    // Newest-updated first; goals with no timestamp sink to the bottom.
    .sort((a: BoardGoal, b: BoardGoal) => (b.updatedMs ?? 0) - (a.updatedMs ?? 0));
}

// ── Domain filter. Each chip maps to a set of tag substrings; a goal matches
// a domain if any of its tags contains any of the domain's terms. "All" is
// the unfiltered view. Matching is client-side over the already-public set.
type Domain = "all" | "research" | "commerce" | "games" | "writing" | "meta";
const DOMAINS: { id: Domain; label: string; terms: string[] }[] = [
  { id: "all", label: "All", terms: [] },
  { id: "research", label: "research", terms: ["research", "science", "simulation", "evidence", "paper", "archaeolog", "biolog", "physics", "study"] },
  { id: "commerce", label: "commerce", terms: ["commerce", "shop", "retail", "market", "business", "invoice", "order", "product", "sales"] },
  { id: "games", label: "games & retro", terms: ["game", "retro", "arcade", "rpg", "classic-game", "unreal", "gameplay", "level"] },
  { id: "writing", label: "writing", terms: ["writing", "fiction", "novel", "story", "screenplay", "narrative", "manuscript", "prose", "fantasy"] },
  { id: "meta", label: "meta/platform", terms: ["platform", "workflow-substrate", "primitive", "meta", "substrate", "reusable-branch", "convention", "self"] },
];

function matchesDomain(g: BoardGoal, domain: Domain): boolean {
  if (domain === "all") return true;
  const terms = DOMAINS.find((d) => d.id === domain)?.terms ?? [];
  if (!terms.length) return true;
  const hay = g.tags.join(" ").toLowerCase();
  return terms.some((t) => hay.includes(t));
}

// ── Curation: keep the board honest without lying. Obvious internal test
// debris (smoke/probe/post-redaction fixtures) is split into a labelled,
// collapsed section rather than scrubbed silently — visitors can still see
// it exists. Everything else is a real public goal.
const TEST_DEBRIS = /smoke|probe|post-redaction/i;
function isTestDebris(g: BoardGoal): boolean {
  return TEST_DEBRIS.test(g.name);
}

// The neutral prompt a visitor pastes into their own chatbot to add a goal.
const ADD_PROMPT = "Propose a goal called <name> about <outcome>.";

export default function GoalsClient() {
  // First paint: baked, stamped with the snapshot's own fetched date. The
  // page is never blank-without-JS — these render server-side. The stamp goes
  // through $lib/fmt so it reads in the visitor's own local time.
  const bakedStampDate = fmtDate((bakedMcp as any).fetched_at);
  const [goals, setGoals] = useState<BoardGoal[]>(() => normalizeBaked(bakedMcp));

  // 'baked' until a live read lands; then 'live' with a read-stamp.
  const [phase, setPhase] = useState<"baked" | "reading" | "live" | "error">("baked");
  const [readAt, setReadAt] = useState<string | null>(null);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  async function refreshMcp() {
    setPhase("reading");
    setErrMsg(null);
    try {
      const res = await callTool("goals", { action: "list" });
      const next = normalizeLive(res);
      setGoals(next);
      setReadAt(new Date().toISOString());
      setPhase("live");
    } catch (e: any) {
      setErrMsg(e?.message ?? String(e));
      setPhase("error");
    }
  }

  useEffect(() => {
    void refreshMcp();
  }, []);

  const realGoals = useMemo(() => goals.filter((g) => !isTestDebris(g)), [goals]);
  const debrisGoals = useMemo(() => goals.filter(isTestDebris), [goals]);

  const [activeDomain, setActiveDomain] = useState<Domain>("all");
  const visibleGoals = useMemo(
    () => realGoals.filter((g) => matchesDomain(g, activeDomain)),
    [realGoals, activeDomain]
  );

  const [copied, setCopied] = useState(false);
  const copyTimer = useRef<number | null>(null);
  async function copyAddPrompt() {
    try {
      await navigator.clipboard.writeText(ADD_PROMPT);
      setCopied(true);
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard unavailable; the text is visible anyway */
    }
  }

  const litCount = useMemo(
    () => visibleGoals.reduce((n, g) => n + g.rungs.filter((r) => r.lit).length, 0),
    [visibleGoals]
  );
  const ladderGoals = useMemo(
    () => visibleGoals.filter((g) => g.rungs.length > 0).length,
    [visibleGoals]
  );

  return (
    <>
      {/* 1 · Hero — Tiny's voice ─────────────────────────────────────────────── */}
      <section className="cover" aria-labelledby="cover-title">
        <div className="container">
          <p className="eyebrow">field notes · the board</p>
          <h1 id="cover-title" className="cover__title">These are the goals people gave me.</h1>
          <p className="voice cover__lede">
            A <Term def="A goal is the outcome someone is after — 'publish the paper', 'run the shop', 'ship the game'. It's shared: many workflows can compete to serve the same one.">goal</Term>{" "}
            is an outcome, not a method. Around each one,{" "}
            <Term def="A workflow is a graph of steps with typed state and checks, designed in plain language through your chatbot. Several can compete to reach the same goal; the best-performing one becomes canonical.">workflows</Term>{" "}
            compete to reach it — and a goal's{" "}
            <Term def="A ladder is a sequence of real-world rungs toward the outcome ('preprint posted', 'peer-reviewed', 'first order fulfilled'). A rung only lights with an evidence URL attached, so the outcome stays checkable instead of merely claimed.">ladder</Term>{" "}
            keeps the whole thing honest: each rung is a checkable event, and a rung
            only lights once there's evidence behind it. The board below reads from
            the same endpoint your chatbot would.
          </p>
        </div>
      </section>

      {/* 2 · The board ───────────────────────────────────────────────────────── */}
      <section className="ch ch--board" aria-labelledby="board-title">
        <div className="container">
          <header className="board__head">
            <div>
              <p className="eyebrow">entry · the public board</p>
              <h2 id="board-title">What's on me right now.</h2>
            </div>
            <div className="board__meta" aria-live="polite">
              {phase === "live" ? (
                <span className="board__stamp ev"><span className="dot live" aria-hidden="true"></span>{realGoals.length} public goals · read live {fmtRel(readAt)}</span>
              ) : phase === "reading" ? (
                <span className="board__stamp ev"><span className="dot" aria-hidden="true"></span>reading the live board… (showing snapshot {bakedStampDate})</span>
              ) : phase === "error" ? (
                <span className="board__stamp ev"><span className="dot error" aria-hidden="true"></span>live read failed — showing snapshot {bakedStampDate}</span>
              ) : (
                <span className="board__stamp ev"><span className="dot" aria-hidden="true"></span>{realGoals.length} public goals · snapshot {bakedStampDate}</span>
              )}
              <button className="board__refresh" onClick={refreshMcp} disabled={phase === "reading"}>
                {phase === "reading" ? "reading…" : "Refresh MCP"}
              </button>
            </div>
          </header>

          {phase === "error" && errMsg && (
            <p className="board__err ev">The live read errored ({errMsg}). The cards below are the last good snapshot from {bakedStampDate}, not a live reading. Try Refresh MCP.</p>
          )}

          {/* Domain filter chips. Match on tags, client-side, over the public set. */}
          <div className="board__filter" role="group" aria-label="Filter goals by domain">
            {DOMAINS.map((d) => (
              <button
                key={d.id}
                type="button"
                className={`chip${activeDomain === d.id ? " chip--on" : ""}`}
                aria-pressed={activeDomain === d.id}
                onClick={() => setActiveDomain(d.id)}
              >{d.label}</button>
            ))}
          </div>

          {visibleGoals.length === 0 ? (
            <p className="board__empty ev">
              {realGoals.length === 0 ? (
                "Quiet right now — no public goals visible at this read. The board retries on its own; you can also press Refresh MCP."
              ) : (
                <>
                  No public goals match <strong>{DOMAINS.find((d) => d.id === activeDomain)?.label}</strong> in this read. Try <button className="linkish" onClick={() => setActiveDomain("all")}>All</button>.
                </>
              )}
            </p>
          ) : (
            <>
              <ul className="board">
                {visibleGoals.map((g) => (
                  <li key={g.id || g.name} className={`goal${phase !== "live" ? " goal--baked" : ""}`}>
                    <div className="goal__top">
                      <h3 className="goal__name">
                        <a className="goal__link" href={`/goals/${g.id}`}>{g.name}</a>
                      </h3>
                      {g.description && (
                        <p className="goal__desc">{g.description}</p>
                      )}
                    </div>

                    {g.tags.length > 0 && (
                      <ul className="goal__tags ev" aria-label="tags">
                        {g.tags.slice(0, 5).map((tag) => (
                          <li key={tag}>{tag}</li>
                        ))}
                        {g.tags.length > 5 && (
                          <li className="goal__tags-more">+{g.tags.length - 5}</li>
                        )}
                      </ul>
                    )}

                    {g.rungs.length > 0 && (
                      <div className="goal__ladder">
                        <p className="goal__ladder-label eyebrow">outcome ladder · {g.rungs.length} rungs</p>
                        <Ladder rungs={g.rungs} start="now" compact={true} />
                      </div>
                    )}

                    <footer className="goal__foot">
                      <Tick href={`/goals/${g.id}`} label={`goal ${g.id || "unknown"}`} />
                    </footer>
                  </li>
                ))}
              </ul>

              <p className="board__foot ev">
                {phase === "live" ? (
                  <>
                    {visibleGoals.length} public goal{visibleGoals.length === 1 ? "" : "s"} shown{activeDomain === "all" ? "" : ` · ${DOMAINS.find((d) => d.id === activeDomain)?.label} filter`} ·{" "}
                    {ladderGoals} carry an outcome ladder · {litCount} rung{litCount === 1 ? "" : "s"} lit — the honest count · read {fmtRel(readAt)}
                  </>
                ) : (
                  `showing the ${bakedStampDate} snapshot · ladders and exact counts upgrade once the live read lands`
                )}
              </p>
              <p className="board__honest ev">
                {visibleGoals.length} public goal{visibleGoals.length === 1 ? "" : "s"} shown · private goals exist but never render here — they live on a host's own machine and never publish to the public commons.
              </p>
            </>
          )}

          {debrisGoals.length > 0 && (
            <details className="board__debris">
              <summary>internal test goals ({debrisGoals.length})</summary>
              <p className="board__debris-note ev">
                These are smoke / probe / fixture goals left by automated tests, not real public work. They're kept visible for honesty, just folded away.
              </p>
              <ul className="board__debris-list">
                {debrisGoals.map((g) => (
                  <li key={g.id || g.name}>
                    <a href={`/goals/${g.id}`}>{g.name}</a>
                    <Tick href={`/goals/${g.id}`} label={`goal ${g.id || "unknown"}`} />
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </section>

      {/* 3 · Put a goal on me ─────────────────────────────────────────────────── */}
      <section className="ch ch--add" aria-labelledby="add-title">
        <div className="container ch__inner">
          <p className="eyebrow">entry · add to the board</p>
          <h2 id="add-title">Put a goal on me.</h2>
          <p className="add__lede">
            You don't fill out a form. You tell your own chatbot, and it proposes
            the goal through the connector. Two steps:
          </p>
          <ol className="add__steps">
            <li>
              <span className="add__n">1</span>
              <div>
                <strong>Connect your chatbot.</strong>
                <p>Paste one URL into Claude, ChatGPT, or any MCP-capable assistant — no account, no install.</p>
                <a className="add__cta" href="/start">how to connect →</a>
              </div>
            </li>
            <li>
              <span className="add__n">2</span>
              <div>
                <strong>Say what you want.</strong>
                <p>With the connector enabled, send your chatbot a sentence like this — swap the bracketed bits for your own:</p>
                <button type="button" className="add__prompt" onClick={copyAddPrompt} aria-label={`Copy prompt: ${ADD_PROMPT}`}>
                  <code>{ADD_PROMPT}</code>
                  <span className="add__copy">{copied ? "copied ✓" : "copy"}</span>
                </button>
                <p className="add__note">
                  Your chatbot proposes it; you and it design a workflow toward it
                  from there. The new goal shows up on this board on its next read.
                </p>
              </div>
            </li>
          </ol>
        </div>
      </section>

      {/* 4 · Close ───────────────────────────────────────────────────────────── */}
      <section className="ch ch--close" aria-labelledby="close-title">
        <div className="container ch__inner">
          <h2 id="close-title">Where this connects.</h2>
          <nav className="close__cards">
            <a className="close__card" href="/loop">
              <span className="close__k eyebrow">the patch loop</span>
              <strong>Watch a goal turn into shipped work →</strong>
              <span className="close__sub">friction becomes a patch request, an investigation, a real pull request, a release.</span>
            </a>
            <a className="close__card" href="/commons">
              <span className="close__k eyebrow">the public commons</span>
              <strong>Read the brain behind the board →</strong>
              <span className="close__sub">the glossary for every term here, plus the searchable record of goals, runs, and notes.</span>
            </a>
          </nav>
        </div>
      </section>
    </>
  );
}
