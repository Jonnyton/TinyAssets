"use client";

import * as React from "react";
import { fetchPublicUniverses } from "../../../lib/live";
import { fmtRel } from "../../../lib/fmt";
import styles from "../page.module.css";

type PublicUniverse = {
  id?: string;
  name?: string;
  phase?: string;
  last_activity_at?: string | null;
};

type PublicGraphRead = {
  universes: PublicUniverse[];
  fetchedAt: string;
  error?: string;
};

function activityTime(universe: PublicUniverse): number {
  const parsed = Date.parse(universe.last_activity_at ?? "");
  return Number.isNaN(parsed) ? Number.NEGATIVE_INFINITY : parsed;
}

export default function LoopClient() {
  const [activity, setActivity] = React.useState<PublicGraphRead | null>(null);
  const [reading, setReading] = React.useState(false);

  const refresh = React.useCallback(async () => {
    setReading(true);
    try {
      const universes = (await fetchPublicUniverses()) as PublicUniverse[];
      setActivity({
        universes: [...universes]
          .sort((left, right) => activityTime(right) - activityTime(left))
          .slice(0, 16),
        fetchedAt: new Date().toISOString(),
      });
    } catch (error) {
      setActivity({
        universes: [],
        fetchedAt: new Date().toISOString(),
        error: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setReading(false);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className={styles.page}>
      <section className="cover" aria-labelledby="loop-title">
        <div className="container ch__inner">
          <p className="eyebrow">workflow activity · public graph read</p>
          <h1 id="loop-title">Ordinary workflows belong to their users.</h1>
          <p className="voice cover__lede">
            Every automation is a user-authored workflow. People compose, publish,
            copy, and remix them from the same public building blocks. This page
            shows activity timestamps from public workflow spaces and labels the
            source and read time explicitly.
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
              <p className="eyebrow">public graph activity · MCP provenance</p>
              <h2 id="activity-title">Public workflow spaces.</h2>
            </div>
            <button className="refresh" onClick={() => void refresh()} disabled={reading}>
              {reading ? "reading…" : "Refresh MCP"}
            </button>
          </div>

          {reading && !activity ? (
            <div className="state state--reading">
              <span className="dot" aria-hidden="true" />
              <p className="state__k">reading the public graph collection…</p>
            </div>
          ) : activity?.error ? (
            <div className="state state--error">
              <span className="dot error" aria-hidden="true" />
              <div>
                <p className="state__k">Public graph activity is unavailable.</p>
                <p className="state__sub ev">
                  source read_graph target=graphs · read {fmtRel(activity.fetchedAt)}
                </p>
                <p className="state__sub">{activity.error}</p>
              </div>
            </div>
          ) : activity?.universes.length ? (
            <>
              <div className="state state--awake">
                <span className="dot live" aria-hidden="true" />
                <div>
                  <p className="state__k">
                    {activity.universes.length} public workflow space
                    {activity.universes.length === 1 ? "" : "s"} visible.
                  </p>
                  <p className="state__sub ev">
                    source read_graph target=graphs · read {fmtRel(activity.fetchedAt)}
                  </p>
                  <p className="state__sub">
                    Activity timestamps describe public graph changes. They are not
                    run records or proof that a workflow is executing now.
                  </p>
                </div>
              </div>
              <div className="events" aria-label="Public workflow spaces">
                <ul className="events__list">
                  {activity.universes.map((universe, index) => {
                    const id = universe.id || universe.name || `public-graph-${index + 1}`;
                    return (
                      <li className="event" key={id}>
                        <span className="event__stage ev">public graph</span>
                        <div className="event__body">
                          <p className="event__title">{universe.name || universe.id || "Unnamed public workflow space"}</p>
                          <p className="event__detail">
                            {universe.phase ? `reported phase ${universe.phase}` : "phase unavailable"}
                          </p>
                        </div>
                        <span className="event__at ev">
                          {universe.last_activity_at
                            ? `activity ${fmtRel(universe.last_activity_at)}`
                            : "activity time unavailable"}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </>
          ) : activity ? (
            <div className="state state--asleep">
              <span className="dot idle" aria-hidden="true" />
              <div>
                <p className="state__k">No public workflow spaces are visible in this read.</p>
                <p className="state__sub ev">
                  source read_graph target=graphs · read {fmtRel(activity.fetchedAt)}
                </p>
                <p className="state__sub">
                  Public graph activity is unavailable until a user publishes a
                  graph visible through this collection.
                </p>
              </div>
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
