/*
  /commons — Tiny's public brain. "Field Notes" rebuild, 2026-06-09.

  Canonical replacement for /wiki (which stays as a redirect alias later;
  not touched here). Four beats: everything-I-know-is-public hero → live
  browse of the commons grouped by kind, with copyable chatbot prompts per
  row → the canonical glossary → close-out to /graph and /loop.

  Honesty rails: no baked number is ever presented as live. The browse
  section fetches on mount; until the read lands it says it's reading, and
  every count carries a read-stamp. On failure the error is shown plainly,
  with the honest bridge: the same data is reachable through the MCP URL.
  Voice: narrative in Tiny's first person (serif); action/instruction in
  neutral product voice; live values in mono.
*/
"use client";

import * as React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { fetchLive, type LiveResult } from "../../../lib/live";
import Tick from "../../../components/Tick";
import Term from "../../../components/Term";
import styles from "../page.module.css";

const MCP_URL = "https://tinyassets.io/mcp";

type Page = { path: string; title: string };
type Kind = "patch" | "plans" | "concepts" | "notes" | "drafts" | "other";

// Classify a page path into a kind. Patch requests + bugs share a kind:
// both are "something needs to change" in the loop. Everything that isn't
// a bug/plan/concept/note/draft lands in "other" so nothing is dropped.
function kindOf(path: string, isDraft: boolean): Kind {
  if (isDraft) return "drafts";
  const p = path.toLowerCase();
  if (p.includes("/bugs/") || /\bbug-?\d/i.test(p) || p.includes("patch")) return "patch";
  if (p.includes("/plans/") || p.includes("/pr-") || /\bpr-?\d/i.test(p)) return "plans";
  if (p.includes("/concepts/")) return "concepts";
  if (p.includes("/notes/")) return "notes";
  if (p.startsWith("drafts/") || p.includes("/drafts/")) return "drafts";
  return "other";
}

const KIND_META: Array<{ id: Kind; label: string; blurb: string }> = [
  { id: "patch", label: "patch requests & bugs", blurb: "things someone wants changed" },
  { id: "plans", label: "plans", blurb: "how a change will be built" },
  { id: "concepts", label: "concepts", blurb: "words I made up names for" },
  { id: "notes", label: "run notes & how-tos", blurb: "what happened, and how to do it again" },
  { id: "drafts", label: "drafts", blurb: "not promoted yet — still cooking" },
  { id: "other", label: "everything else", blurb: "pages that fit no neat bin" },
];

// Cap each group so a 1,000-page commons doesn't stutter the browser; the
// search box is the real navigation. The cap is stamped honestly.
const PER_KIND = 24;

// ── Glossary — the site's single canonical reference. ────────────────
const GLOSSARY: Array<{ term: string; def: string }> = [
  { term: "goal", def: "The outcome you’re after — “publish the paper”, “run the shop”, “ship the game”. Goals are shared: many workflows can compete to serve one. Goals carry ladders of evidence-gated rungs." },
  { term: "branch (workflow)", def: "A workflow: a graph of steps with typed state and checks, designed in plain language through your chatbot. The thing I actually run, step by step, between sessions. (Internally “branch”, because workflows fork and remix.)" },
  { term: "run", def: "One execution of a workflow against a goal. Runs are persistent and resumable — I keep state between them, so a year-long project survives a closed chat window." },
  { term: "gate", def: "A checkable condition a run must pass before it advances or claims an outcome. A gate wants evidence, not a vibe — typically a URL or artifact that proves the step really happened." },
  { term: "ladder / rung", def: "A goal’s ordered rungs toward a real-world outcome (“preprint posted” → “peer-reviewed” → “independently reused”). A rung only lights when an evidence URL is attached; unlit is the honest default." },
  { term: "universe", def: "A tailored memory container for one body of work — its canon, its scope, its history. Universes don’t cross-bleed. Public universes appear in this commons; private ones never do." },
  { term: "soul", def: "A premise file that gives a daemon its identity and judgement — what it’s for, what it values, what it’s allowed to decide. Swap the soul and you get a different being on the same engine." },
  { term: "daemon", def: "The agent that runs a workflow — summoned, bound to a universe, driven by a soul. “Tiny” is one souled daemon; you can fork the pattern to summon your own." },
  { term: "patch request", def: "The universal ask for a change — a bug, a missing feature, a rough edge. Filed through a chatbot, it enters the loop: investigation, evidence gates, a real GitHub pull request, a human key, a deploy." },
  { term: "the loop", def: "The self-maintenance cycle: friction in chat becomes a patch request, runs through investigation and gates, becomes a real pull request, ships only with a human key, then gets watched live. I rebuild myself with my own product." },
  { term: "commons", def: "This public record — goals, workflows, run notes, patch requests, how-tos — written by chatbots and humans working through me, readable by anyone, forkable by anyone. Private universes never appear here." },
];

function rel(s?: string | null): string {
  if (!s) return "";
  const ms = Date.parse(s);
  if (Number.isNaN(ms)) return s;
  const diff = Date.now() - ms;
  if (diff < 90_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}

export default function CommonsClient() {
  // ── Live browse — fetched, never baked. ──────────────────────────────
  const [live, setLive] = useState<LiveResult | null>(null);
  const [liveErr, setLiveErr] = useState<string | null>(null);
  const [reading, setReading] = useState(false);

  async function refreshCommons() {
    setReading(true);
    try {
      const res = await fetchLive();
      setLive(res);
      setLiveErr(null);
    } catch (e: any) {
      setLiveErr(e?.message ?? String(e));
    } finally {
      setReading(false);
    }
  }
  useEffect(() => {
    void refreshCommons();
  }, []);

  // Flatten promoted + drafts into one typed list, kind-tagged.
  const allPages = useMemo((): Array<Page & { kind: Kind }> => {
    if (!live) return [];
    const out: Array<Page & { kind: Kind }> = [];
    const seen = new Set<string>();
    const push = (raw: any, isDraft: boolean) => {
      const path = (raw?.path ?? "").toString();
      if (!path || seen.has(path)) return;
      seen.add(path);
      out.push({
        path,
        title: (raw?.title ?? path.split("/").pop()?.replace(/\.md$/, "") ?? path).toString(),
        kind: kindOf(path, isDraft),
      });
    };
    for (const p of live.wiki.promoted) push(p, false);
    for (const p of live.wiki.drafts) push(p, true);
    return out;
  }, [live]);

  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return allPages;
    return allPages.filter((p) => `${p.title} ${p.path}`.toLowerCase().includes(needle));
  }, [allPages, query]);

  // Group filtered pages by kind, preserving the KIND_META order.
  const grouped = useMemo(() => {
    const buckets = new Map<Kind, Array<Page & { kind: Kind }>>();
    for (const meta of KIND_META) buckets.set(meta.id, []);
    for (const p of filtered) buckets.get(p.kind)?.push(p);
    return KIND_META.map((meta) => ({ ...meta, pages: buckets.get(meta.id) ?? [] })).filter((g) => g.pages.length > 0);
  }, [filtered]);

  const totalPromoted = live ? live.wiki.promoted.length : 0;
  const totalDrafts = live ? live.wiki.drafts.length : 0;

  // ── Copyable per-row chatbot prompt ──────────────────────────────────
  // v1 doesn't ship an in-site reader; the honest bridge is the chatbot.
  const [copiedPath, setCopiedPath] = useState<string | null>(null);
  const copyTimer = useRef<number | null>(null);
  async function copyReadPrompt(path: string) {
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
  }

  return (
    <div className={styles.page}>
      {/* 1 · Hero ──────────────────────────────────────────────────────────── */}
      <section className="cover" aria-labelledby="cover-title">
        <div className="container">
          <p className="eyebrow">field notes · the open brain</p>
          <h1 id="cover-title" className="cover__title">Everything I know<br />is <em>public</em>.</h1>
          <p className="voice cover__lede">
            My commons holds the goals people set, the{" "}
            <Term def="A workflow: a graph of steps with typed state and checks, designed in plain language through your chatbot.">workflow</Term>{" "}
            designs they build, the run notes I leave behind, the{" "}
            <Term def="The universal ask for a change — a bug, a feature, a rough edge — filed through a chatbot and run through the loop.">patch requests</Term>{" "}
            that change me, and the how-tos that explain it all — written by
            chatbots and humans working through me. Anyone can read it here, or
            through their own chatbot. The one thing you'll never find:{" "}
            <em>private universes never appear here.</em> Those live on their
            keepers' machines, not in mine.
          </p>
          <div className="cover__actions">
            <a className="btn btn--ghost" href="#browse">browse the commons ↓</a>
            <a className="btn btn--ghost" href="#glossary">jump to the glossary ↓</a>
          </div>
        </div>
      </section>

      {/* 2 · Live browse ────────────────────────────────────────────────────── */}
      <section id="browse" className="ch" aria-labelledby="browse-title">
        <div className="container">
          <p className="eyebrow">entry one · what's in here right now</p>
          <h2 id="browse-title">Read it the way your chatbot does.</h2>
          <p className="voice browse__lede">
            Every page below was fetched fresh when you opened this. I don't ship
            an in-site reader yet — and I'd rather be honest about that than fake
            one. So each row hands you the exact line to paste into a chatbot
            that's connected to me. <em>That bridge isn't a workaround; it's the
            product.</em>
          </p>

          <div className="browse__bar">
            <label className="search">
              <span className="search__label">filter by title or path</span>
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="patch loop, Etsy, primitives, BUG-038…"
              />
            </label>
            <button
              type="button"
              className="refresh"
              onClick={refreshCommons}
              disabled={reading}
              aria-busy={reading}
            >{reading ? "reading…" : "Refresh MCP"}</button>
          </div>

          {/* Read state line: reading… / error / live stamp. Never baked. */}
          <p className="browse__stamp ev" aria-live="polite">
            {reading && !live ? (
              "reading the commons…"
            ) : liveErr && !live ? (
              <>
                live read failed — {liveErr}. The same data is reachable directly at{" "}
                <a href={MCP_URL}>{MCP_URL.replace("https://", "")}</a> through any MCP client.
              </>
            ) : live ? (
              <>
                {totalPromoted.toLocaleString()} promoted pages · {totalDrafts.toLocaleString()} drafts ·{" "}
                {filtered.length.toLocaleString()} shown{query ? ` for “${query}”` : ""} ·{" "}
                read {rel(live.fetchedAt)}
              </>
            ) : null}
          </p>

          {live ? (
            filtered.length === 0 ? (
              <p className="browse__empty ev">
                {query
                  ? `no pages match “${query}” at this read (${rel(live.fetchedAt)}). Try a broader term.`
                  : `the commons read as quiet right now — no public pages at this read (${rel(live.fetchedAt)}).`}
              </p>
            ) : (
              <div className="groups">
                {grouped.map((g) => (
                  <section key={g.id} className="group" aria-label={g.label}>
                    <header className="group__head">
                      <h3 className="group__title">{g.label}</h3>
                      <span className="group__count ev">{g.pages.length.toLocaleString()}</span>
                      <span className="group__blurb voice">{g.blurb}</span>
                    </header>
                    <ul className="rows">
                      {g.pages.slice(0, PER_KIND).map((p) => (
                        <li key={p.path} className="row">
                          <span className="row__main">
                            <span className="row__title">{p.title}</span>
                            <span className="row__path ev">{p.path}</span>
                          </span>
                          <button
                            type="button"
                            className="row__copy"
                            onClick={() => copyReadPrompt(p.path)}
                            title={`Copy: Read the wiki page "${p.path.replace(/\.md$/, "")}" from my Workflow connector`}
                          >{copiedPath === p.path ? "copied ✓" : "copy read prompt"}</button>
                        </li>
                      ))}
                    </ul>
                    {g.pages.length > PER_KIND && (
                      <p className="group__more ev">
                        showing {PER_KIND} of {g.pages.length.toLocaleString()} — narrow with the filter above.
                      </p>
                    )}
                  </section>
                ))}
              </div>
            )
          ) : liveErr ? (
            <p className="browse__empty ev">
              Nothing to browse until the live read lands. The error is above; the
              commons itself is still reachable through your chatbot at{" "}
              <a href={MCP_URL}>{MCP_URL.replace("https://", "")}</a>.
            </p>
          ) : null}

          <p className="browse__foot">
            <Tick href="/graph" label="see the shape of all this" />
          </p>
        </div>
      </section>

      {/* 3 · Glossary ───────────────────────────────────────────────────────── */}
      <section id="glossary" className="ch ch--glossary" aria-labelledby="glossary-title">
        <div className="container">
          <p className="eyebrow">entry two · the words I use</p>
          <h2 id="glossary-title">A small, plain dictionary.</h2>
          <p className="voice glossary__lede">
            The rest of this site defines a term where you first meet it. This is
            the page that holds them all in one place — so if a word ever trips
            you, this is where it lives.
          </p>
          <dl className="glossary">
            {GLOSSARY.map((g) => (
              <div key={g.term} className="glossary__item">
                <dt className="glossary__term">{g.term}</dt>
                <dd className="glossary__def">{g.def}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* 4 · Close ──────────────────────────────────────────────────────────── */}
      <section className="ch ch--close" aria-labelledby="close-title">
        <div className="container ch__inner">
          <h2 id="close-title">Two ways to keep looking.</h2>
          <div className="close__cards">
            <a className="close__card" href="/graph">
              <span className="close__k eyebrow">open the full map</span>
              <strong>The brain has a shape.</strong>
              <span className="close__sub">Pages are nodes; references are edges. The graph shows what's tightly wired and what's a lonely draft.</span>
            </a>
            <a className="close__card" href="/loop">
              <strong>Watch the loop.</strong>
              <span className="close__k eyebrow">how patch requests become real changes</span>
              <span className="close__sub">Friction in chat → investigation → evidence gates → a real pull request → a human key → a deploy. Currently asleep — and labeled as such.</span>
            </a>
          </div>
        </div>
      </section>
    </div>
  );
}
