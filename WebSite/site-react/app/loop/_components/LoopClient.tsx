"use client";

import * as React from "react";
import { fetchWorkflowActivity, type WorkflowActivity } from "../../../lib/live";
import { fmtRel } from "../../../lib/fmt";
import styles from "../page.module.css";

const TERMINAL = new Set(["completed", "failed", "cancelled", "canceled", "interrupted"]);

function runStamp(run: WorkflowActivity["runs"][number]): string | null {
  return run.finishedAt ?? run.startedAt ?? null;
}

export default function LoopClient() {
  const [activity, setActivity] = React.useState<WorkflowActivity | null>(null);
  const [reading, setReading] = React.useState(false);

  const refresh = React.useCallback(async () => {
    setReading(true);
    setActivity(await fetchWorkflowActivity(16));
    setReading(false);
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const newestRun = activity?.runs[0] ?? null;

  return (
    <div className={styles.page}>
      <section className="cover" aria-labelledby="loop-title">
        <div className="container ch__inner">
          <p className="eyebrow">workflow activity · public read</p>
          <h1 id="loop-title">Ordinary workflows, moving when users run them.</h1>
          <p className="voice cover__lede">
            Every automation here is a user-authored workflow. People compose,
            publish, copy, and remix them from the same public building blocks. This
            page shows recent activity from the connector and labels the source and
            read time explicitly.
          </p>
        </div>
      </section>

      <section className="ch" aria-labelledby="shape-title">
        <div className="container ch__inner">
          <p className="eyebrow">the reusable shape</p>
          <h2 id="shape-title">Design it. Run it. Check the evidence. Remix it.</h2>
          <p className="voice">
            A workflow is a user-authored graph of steps, state, and checks. It can
            serve research, writing, commerce, software, or any other long-running
            goal. The platform supplies generic storage and execution primitives;
            the author supplies the purpose and decides when the workflow runs.
          </p>
          <nav className="close__row" aria-label="Workflow resources">
            <a className="close__cta" href="/patterns">
              <span className="close__k eyebrow">patterns</span>
              <strong>Start from a reusable workflow design.</strong>
              <span className="close__sub">Connect a chatbot, then adapt a pattern to your goal.</span>
            </a>
            <a className="close__cta close__cta--alt" href="/commons">
              <span className="close__k eyebrow">commons</span>
              <strong>Browse public goals, notes, and designs.</strong>
              <span className="close__sub">See what people have published and follow its provenance.</span>
            </a>
          </nav>
        </div>
      </section>

      <section className="ch ch--live" aria-labelledby="activity-title">
        <div className="container">
          <div className="live__head">
            <div>
              <p className="eyebrow">recent activity · MCP provenance</p>
              <h2 id="activity-title">What users have run recently.</h2>
            </div>
            <button className="refresh" onClick={() => void refresh()} disabled={reading}>
              {reading ? "reading…" : "Refresh MCP"}
            </button>
          </div>

          {reading && !activity ? (
            <div className="state state--reading">
              <span className="dot" aria-hidden="true" />
              <p className="state__k">reading recent workflow runs from the connector…</p>
            </div>
          ) : activity?.warnings.length && !activity.runs.length ? (
            <div className="state state--error">
              <span className="dot error" aria-hidden="true" />
              <div>
                <p className="state__k">Recent workflow activity is unavailable.</p>
                <p className="state__sub ev">
                  source {activity.source} · read {fmtRel(activity.fetchedAt)}
                </p>
                <p className="state__sub">{activity.warnings.join(" · ")}</p>
              </div>
            </div>
          ) : activity?.active ? (
            <div className="state state--awake">
              <span className="dot live" aria-hidden="true" />
              <div>
                <p className="state__k">A user workflow is active.</p>
                <p className="state__sub ev">
                  source {activity.source} · read {fmtRel(activity.fetchedAt)}
                </p>
              </div>
            </div>
          ) : activity ? (
            <div className="state state--asleep">
              <span className="dot idle" aria-hidden="true" />
              <div>
                <p className="state__k">No active workflow is visible in this read.</p>
                <p className="state__sub ev">
                  latest visible run {fmtRel(newestRun ? runStamp(newestRun) : null)} ·
                  source {activity.source} · read {fmtRel(activity.fetchedAt)}
                </p>
                <p className="state__sub">
                  Historical runs below are provenance-labelled activity, not platform
                  uptime evidence and not a promise that work is moving now.
                </p>
              </div>
            </div>
          ) : null}

          {activity?.runs.length ? (
            <div className="events" aria-label="Recent user workflow runs">
              <ul className="events__list">
                {activity.runs.map((run) => (
                  <li className="event" key={run.runId || `${run.workflowId}:${runStamp(run)}`}>
                    <span className="event__stage ev">
                      {TERMINAL.has(run.status) ? "history" : "active"}
                    </span>
                    <div className="event__body">
                      <p className="event__title">{run.name || "Unnamed workflow run"}</p>
                      <p className="event__detail">
                        {run.workflowId ? `workflow ${run.workflowId}` : "workflow id unavailable"}
                        {run.runId ? ` · run ${run.runId}` : ""}
                        {run.actor ? ` · actor ${run.actor}` : ""}
                      </p>
                    </div>
                    <span className="event__at ev">
                      {run.status} · {fmtRel(runStamp(run))}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : activity && !activity.warnings.length ? (
            <p className="events__empty ev">
              The connector answered, but returned no recent workflow runs.
            </p>
          ) : null}
        </div>
      </section>
    </div>
  );
}
