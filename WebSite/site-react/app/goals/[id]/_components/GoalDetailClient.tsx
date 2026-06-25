/*
  /goals/[id] — a single goal's detail page. The persona crawl found every
  trail ending at an unlinked goal-id chip; this is where that chip leads.

  Client-side only. It paints instantly from the baked snapshot if the goal
  is in it, stamped with the snapshot's fetched_at, then upgrades live via
  `goals action=get`, which is the only place the full description + gate
  ladder live. Honest states: a goal absent from the snapshot shows
  "reading…" until the live read settles; a live read that fails with nothing
  baked says so plainly; a private / not-returned goal says exactly that. All
  stamps go through lib/fmt.
*/
"use client";

import * as React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { callTool } from "../../../../lib/live";
import bakedMcp from "../../../../lib/mcp-snapshot.json";
import { fmtStamp, fmtRel } from "../../../../lib/fmt";
import Ladder from "../../../../components/Ladder";
import Term from "../../../../components/Term";
import Tick from "../../../../components/Tick";

type Rung = { key?: string; name: string; description?: string; lit?: boolean; evidence_url?: string };
type Goal = {
  id: string;
  name: string;
  description: string;
  tags: string[];
  visibility: string;
  createdMs: number | null;
  updatedMs: number | null;
  rungs: Rung[];
};

function toTags(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.map((t) => String(t).trim()).filter(Boolean);
  if (typeof raw === "string") return raw.split(",").map((t) => t.trim()).filter(Boolean);
  return [];
}

// Live gate ladders carry {name, rung_key, description}. A rung lights ONLY
// with a real evidence URL behind it — absent one, it renders unlit. That's
// the honest default, and the section copy owns it.
function toRungs(raw: unknown): Rung[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((r: any) => ({
      key: r?.rung_key ?? r?.key ?? r?.name,
      name: String(r?.name ?? r?.rung_key ?? "").trim(),
      description: r?.description ? String(r.description) : undefined,
      lit: Boolean(r?.lit && r?.evidence_url),
      evidence_url: r?.evidence_url ?? undefined,
    }))
    .filter((r) => r.name);
}

// Live timestamps are Unix epoch seconds; fmt.ts handles either, but we
// keep a nullable ms so "unknown" stays honest when a goal carries none.
function toMs(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value > 1e12 ? value : value * 1000;
  if (typeof value === "string") {
    const n = Number(value);
    if (Number.isFinite(n) && n > 0) return n > 1e12 ? n : n * 1000;
    const p = Date.parse(value);
    if (!Number.isNaN(p)) return p;
  }
  return null;
}

function fromBaked(gid: string): Goal | null {
  const raw = ((bakedMcp as any).goals ?? []).find(
    (g: any) => String(g.id ?? g.goal_id ?? "") === gid
  );
  if (!raw) return null;
  return {
    id: gid,
    name: String(raw.name ?? ""),
    // The baked snapshot stores the body as "summary"; live returns the
    // fuller "description". Baked is the placeholder until live lands.
    description: String(raw.summary ?? raw.description ?? ""),
    tags: toTags(raw.tags),
    visibility: String(raw.visibility ?? "public"),
    createdMs: toMs(raw.created_at),
    updatedMs: toMs(raw.updated_at ?? raw.created_at),
    rungs: toRungs(raw.gate_ladder),
  };
}

function fromLive(raw: any, gid: string): Goal | null {
  if (!raw || typeof raw !== "object") return null;
  // `goals action=get` may return the goal directly or under a `goal` key.
  const g = raw.goal ?? raw;
  if (!g || typeof g !== "object") return null;
  const liveId = String(g.goal_id ?? g.id ?? gid);
  if (!g.name && !g.description) return null;
  return {
    id: liveId,
    name: String(g.name ?? ""),
    description: String(g.description ?? g.summary ?? ""),
    tags: toTags(g.tags),
    visibility: String(g.visibility ?? "public"),
    createdMs: toMs(g.created_at),
    updatedMs: toMs(g.updated_at ?? g.created_at),
    rungs: toRungs(g.gate_ladder),
  };
}

export default function GoalDetailClient() {
  const params = useParams();
  const id = String((params?.id as string) ?? "");

  // First paint: baked if present (instant, stamped with the snapshot date).
  const bakedStamp = fmtStamp((bakedMcp as any).fetched_at);
  const [goal, setGoal] = useState<Goal | null>(null);

  // 'baked' = showing snapshot; 'reading' = first live read in flight with
  // nothing baked; 'live' = upgraded; 'missing' = live says no such public
  // goal and nothing baked; 'private' = live returned it as private/withheld.
  const [phase, setPhase] = useState<"baked" | "reading" | "live" | "missing" | "private">("baked");
  const [readAt, setReadAt] = useState<string | null>(null);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  async function load() {
    const gid = id;
    const baked = gid ? fromBaked(gid) : null;
    if (baked) {
      setGoal(baked);
      setPhase("baked");
    } else {
      setGoal(null);
      setPhase("reading");
    }
    if (!gid) {
      setPhase("missing");
      return;
    }
    setErrMsg(null);
    try {
      const res = await callTool("goals", { action: "get", goal_id: gid });
      const live = fromLive(res, gid);
      if (live) {
        // A goal that comes back private (or with no public body) is named,
        // not silently swallowed.
        if (live.visibility.toLowerCase() === "private") {
          setGoal(live);
          setPhase("private");
        } else {
          setGoal(live);
          setReadAt(new Date().toISOString());
          setPhase("live");
        }
      } else if (baked) {
        // Live read returned nothing usable but we still have the snapshot.
        // Keep showing baked rather than blanking the page.
        setPhase("baked");
      } else {
        setPhase("missing");
      }
    } catch (e: any) {
      setErrMsg(e?.message ?? String(e));
      // Error + nothing baked = honestly can't show the goal.
      if (!baked) setPhase("missing");
      else setPhase("baked");
    }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    void load();
    // re-run when the id changes
  }, [id]);

  // The neutral prompt a visitor pastes into their own chatbot.
  const bridgePrompt = useMemo(
    () =>
      goal?.name
        ? `Show me the goal "${goal.name}" (${id}) on my Workflow connector and list its branches.`
        : `Show me the goal ${id} on my Workflow connector and list its branches.`,
    [goal?.name, id]
  );
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef<number | null>(null);
  async function copyBridge() {
    try {
      await navigator.clipboard.writeText(bridgePrompt);
      setCopied(true);
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard unavailable; the text is visible anyway */
    }
  }

  const litCount = (goal?.rungs ?? []).filter((r) => r.lit).length;

  return (
    <article className="detail">
      <div className="container">
        <p className="eyebrow"><a className="back" href="/goals">← the board</a> · goal</p>

        {phase === "reading" ? (
          /* Nothing baked for this id yet; the live read is settling. */
          <>
            <h1 className="detail__title detail__title--quiet">reading goal {id}…</h1>
            <p className="detail__state ev">
              <span className="dot" aria-hidden="true"></span>
              Pulling this goal live from the connector. If it's a public goal, it'll
              appear in a moment. <button className="retry" onClick={load}>Refresh MCP</button>
            </p>
          </>
        ) : phase === "missing" ? (
          <>
            <h1 className="detail__title">I can't find a public goal with this id.</h1>
            <p className="detail__state ev">
              {errMsg && <>The live read errored ({errMsg}). </>}
              Nothing public answers to <code>{id}</code> right now. It may have been
              retired, made private, or the id was mistyped.
            </p>
            <p className="detail__back-cta">
              <a className="cta" href="/goals">← back to the board</a>
              <button className="retry" onClick={load}>Refresh MCP</button>
            </p>
          </>
        ) : goal ? (
          <>
            <h1 className="detail__title">{goal.name || `Goal ${id}`}</h1>

            <p className="detail__meta ev" aria-live="polite">
              {phase === "live" ? (
                <span className="detail__stamp"><span className="dot live" aria-hidden="true"></span>read live {fmtRel(readAt)}</span>
              ) : phase === "private" ? (
                <span className="detail__stamp"><span className="dot" aria-hidden="true"></span>read live · this goal is private</span>
              ) : (
                <span className="detail__stamp"><span className="dot" aria-hidden="true"></span>snapshot {bakedStamp} · upgrading live…</span>
              )}
              <Tick label={`goal ${goal.id || id}`} />
              <button className="retry" onClick={load}>Refresh MCP</button>
            </p>

            {phase === "private" && (
              <p className="detail__private ev">
                This goal is marked <strong>private</strong>. Private goals live on a
                host's own machine and never publish their body to the public commons —
                so there's no description or ladder to show here. Only its existence
                and id are public.
              </p>
            )}

            {errMsg && phase === "baked" && (
              <p className="detail__err ev">
                The live read errored ({errMsg}). What's below is the {bakedStamp}
                snapshot, not a live reading. Try Refresh MCP.
              </p>
            )}

            {goal.description && phase !== "private" && (
              /* The lab-notebook detail belongs here, in a readable measure and
                 NOT clamped — this is the one place the full body is meant to be. */
              <div className="detail__body">
                {goal.description.split(/\n{2,}/).filter(Boolean).map((para, i) => (
                  <p key={i}>{para}</p>
                ))}
              </div>
            )}

            {goal.tags.length > 0 && (
              <ul className="detail__tags ev" aria-label="tags">
                {goal.tags.map((tag) => (
                  <li key={tag}>{tag}</li>
                ))}
              </ul>
            )}

            <dl className="detail__dates ev">
              {goal.createdMs && (
                <div><dt>created</dt><dd>{fmtStamp(goal.createdMs)}</dd></div>
              )}
              {goal.updatedMs && (
                <div><dt>updated</dt><dd>{fmtStamp(goal.updatedMs)}</dd></div>
              )}
              {!goal.createdMs && !goal.updatedMs && phase === "live" && (
                <div><dt>dates</dt><dd>none recorded on this goal</dd></div>
              )}
            </dl>

            {phase !== "private" && (
              <section className="detail__ladder" aria-labelledby="ladder-title">
                <h2 id="ladder-title" className="detail__h2">The outcome{" "}
                  <Term def="A ladder is a sequence of real-world rungs toward the outcome. A rung only lights with an evidence URL attached, so the outcome stays checkable instead of merely claimed.">ladder</Term>.</h2>
                {goal.rungs.length > 0 ? (
                  <>
                    <Ladder rungs={goal.rungs} start="now" />
                    <p className="detail__honest ev">
                      {goal.rungs.length} rung{goal.rungs.length === 1 ? "" : "s"} ·{" "}
                      {litCount} lit — the honest count. A rung only lights once a real
                      evidence URL is attached; unlit rungs are planned, not yet proven.
                    </p>
                  </>
                ) : phase === "live" ? (
                  <p className="detail__honest ev">
                    No ladder is bound to this goal yet — its outcome hasn't been
                    broken into evidence-gated rungs. That's a normal early state.
                  </p>
                ) : (
                  <p className="detail__honest ev">
                    The ladder upgrades once the live read lands.
                  </p>
                )}
              </section>
            )}

            {/* The chatbot bridge: a copyable prompt the visitor pastes into their
                own assistant to open this goal on their connector. */}
            <section className="bridge" aria-labelledby="bridge-title">
              <p className="eyebrow">take it to your chatbot</p>
              <h2 id="bridge-title" className="detail__h2">Open this goal on your connector.</h2>
              <p className="bridge__lede">
                With the <Term def="A connector is the one URL you paste into Claude, ChatGPT, or any MCP-capable assistant to give it the Workflow tools — no account, no install.">connector</Term>{" "}
                enabled, paste this into your own chatbot to inspect this goal and the
                branches competing to reach it:
              </p>
              <button type="button" className="bridge__prompt" onClick={copyBridge} aria-label={`Copy prompt: ${bridgePrompt}`}>
                <code>{bridgePrompt}</code>
                <span className="bridge__copy">{copied ? "copied ✓" : "copy"}</span>
              </button>
              <p className="bridge__note">
                New here? <a href="/start">How to connect →</a>
              </p>
            </section>
          </>
        ) : null}
      </div>
    </article>
  );
}
