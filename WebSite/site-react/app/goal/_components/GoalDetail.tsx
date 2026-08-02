/*
  /goals/[id] — a single goal's detail page. The persona crawl found every
  trail ending at an unlinked goal-id chip; this is where that chip leads.

  Client-side only. It renders a public Goal only when that Goal is present
  and explicitly public in the checked-in snapshot. The browser does not
  request private-capable Goal records from MCP. Visitors can use the published
  outcome as inspiration for a new user-authored workflow.
*/
"use client";

import * as React from "react";
import { useMemo, useRef, useState } from "react";
import bakedMcp from "../../../lib/mcp-snapshot.json";
import { fmtStamp } from "../../../lib/fmt";
import Ladder from "../../../components/Ladder";
import Term from "../../../components/Term";
import Tick from "../../../components/Tick";

type Rung = { key?: string; name: string; description?: string; lit?: boolean; evidence_url?: string };
type Goal = {
  id: string;
  name: string;
  description: string;
  tags: string[];
  createdMs: number | null;
  updatedMs: number | null;
  rungs: Rung[];
};

function toTags(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.map((t) => String(t).trim()).filter(Boolean);
  if (typeof raw === "string") return raw.split(",").map((t) => t.trim()).filter(Boolean);
  return [];
}

// Snapshot ladders carry {name, rung_key, description}. A rung lights only
// with a real evidence URL behind it; absent one, it renders unlit.
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

// Snapshot timestamps may be Unix epoch seconds or ISO strings.
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
    (g: any) =>
      String(g.id ?? g.goal_id ?? "") === gid &&
      String(g.visibility ?? "").toLowerCase() === "public"
  );
  if (!raw) return null;
  return {
    id: gid,
    name: String(raw.name ?? ""),
    // The checked-in snapshot normally stores the body as "summary".
    description: String(raw.summary ?? raw.description ?? ""),
    tags: toTags(raw.tags),
    createdMs: toMs(raw.created_at),
    updatedMs: toMs(raw.updated_at ?? raw.created_at),
    rungs: toRungs(raw.gate_ladder),
  };
}

export default function GoalDetail({ id }: { id: string }) {
  const bakedStamp = fmtStamp((bakedMcp as any).fetched_at);
  const goal = id ? fromBaked(id) : null;

  // A neutral remix prompt based only on the checked-in public snapshot.
  const bridgePrompt = useMemo(
    () =>
      goal?.name
        ? `Help me design a new user-authored workflow for the outcome "${goal.name}". Use ordinary, remixable workflow primitives and do not request the source Goal record.`
        : "Help me design a new user-authored workflow from a public outcome. Use ordinary, remixable workflow primitives.",
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

        {!goal ? (
          <>
            <h1 className="detail__title">This goal is not in the public snapshot.</h1>
            <p className="detail__state ev">
              The checked-in snapshot from {bakedStamp} has no explicitly
              public Goal with id <code>{id || "unknown"}</code>. It may be
              newer than the snapshot, unavailable to the public site, retired,
              or mistyped. No connector Goal-record read is attempted.
            </p>
            <p className="detail__back-cta">
              <a className="cta" href="/goals">← back to the board</a>
            </p>
          </>
        ) : (
          <>
            <h1 className="detail__title">{goal.name || `Goal ${id}`}</h1>

            <p className="detail__meta ev">
              <span className="detail__stamp">
                <span className="dot" aria-hidden="true"></span>
                checked-in public snapshot {bakedStamp}
              </span>
              <Tick label={`goal ${goal.id || id}`} />
            </p>

            {goal.description && (
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
              {!goal.createdMs && !goal.updatedMs && (
                <div><dt>dates</dt><dd>none included in this snapshot</dd></div>
              )}
            </dl>

            <section className="detail__ladder" aria-labelledby="ladder-title">
              <h2 id="ladder-title" className="detail__h2">The outcome{" "}
                <Term def="A ladder is a sequence of real-world rungs toward the outcome. A rung only lights with an evidence URL attached, so the outcome stays checkable instead of merely claimed.">ladder</Term>.</h2>
              {goal.rungs.length > 0 ? (
                <>
                  <Ladder rungs={goal.rungs} start="now" />
                  <p className="detail__honest ev">
                    {goal.rungs.length} rung{goal.rungs.length === 1 ? "" : "s"} ·{" "}
                    {litCount} lit in this snapshot. A rung only lights once a real
                    evidence URL is attached; unlit rungs are not yet proven.
                  </p>
                </>
              ) : (
                <p className="detail__honest ev">
                  No outcome ladder is included for this Goal in the checked-in
                  snapshot.
                </p>
              )}
            </section>

            {/* A copyable prompt that remixes the published outcome without
                requesting its source Goal record. */}
            <section className="bridge" aria-labelledby="bridge-title">
              <p className="eyebrow">remix the published outcome</p>
              <h2 id="bridge-title" className="detail__h2">Design your own workflow.</h2>
              <p className="bridge__lede">
                With the <Term def="A connector is the one URL you paste into Claude, ChatGPT, or any MCP-capable assistant to give it the TinyAssets tools — no account, no install.">connector</Term>{" "}
                enabled, paste this into your own chatbot to compose an authenticated,
                user-authored workflow from the published outcome. The prompt does
                not inspect the source Goal record:
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
        )}
      </div>
    </article>
  );
}
