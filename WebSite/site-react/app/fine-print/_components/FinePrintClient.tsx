"use client";

import * as React from "react";
import Term from "../../../components/Term";
import VitalSigns from "../../../components/VitalSigns";
import { callTool } from "../../../lib/live";
import baked from "../../../lib/mcp-snapshot.json";
import { fmtStampStable } from "../../../lib/fmt";
import { useMounted } from "../../../lib/useMounted";
import styles from "../page.module.css";

const GH_ACTIONS = "https://github.com/Jonnyton/Workflow/actions";
const MCP_BARE = "tinyassets.io/mcp";
const bakedFetchedAt: string = baked.fetched_at ?? "";

const WATCHDOGS = [
  {
    file: "uptime-canary.yml",
    what: "Probes the public MCP endpoint on a schedule and after any DNS, tunnel, or Worker change — the out-of-band check that catches a silently-dropped route.",
  },
  {
    file: "community-loop-watch.yml",
    what: "Watches the self-patch loop end to end — intake, investigation, gate, release — and opens an alarm when a stage stalls.",
  },
];

type ReceiptState = "reading" | "ok" | "empty" | "error";

function rel(s?: string | null): string {
  if (!s) return "unknown";
  const ms = Date.parse(s);
  if (Number.isNaN(ms)) return s;
  const diff = Date.now() - ms;
  if (diff < 90_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}

function stamp(s?: string | null): string {
  if (!s) return "";
  const ms = Date.parse(s);
  if (Number.isNaN(ms)) return s;
  return new Date(ms).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function pick(obj: Record<string, unknown> | null, ...keys: string[]): string | undefined {
  if (!obj) return undefined;
  for (const k of keys) {
    const value = obj[k];
    if (value !== undefined && value !== null && value !== "") return String(value);
  }
  return undefined;
}

export default function FinePrintClient() {
  const mounted = useMounted();
  const [rcState, setRcState] = React.useState<ReceiptState>("reading");
  const [rcError, setRcError] = React.useState<string | null>(null);
  const [rcFetchedAt, setRcFetchedAt] = React.useState<string | null>(null);
  const [release, setRelease] = React.useState<Record<string, unknown> | null>(null);

  const readReceipt = React.useCallback(async () => {
    setRcState("reading");
    setRcError(null);
    try {
      const payload = await callTool("get_status", {});
      const relState = payload?.release_state ?? null;
      setRcFetchedAt(new Date().toISOString());
      if (relState && typeof relState === "object" && Object.keys(relState).length) {
        setRelease(relState as Record<string, unknown>);
        setRcState("ok");
      } else {
        setRelease(null);
        setRcState("empty");
      }
    } catch (err) {
      setRcError(err instanceof Error ? err.message : String(err));
      setRcState("error");
      setRelease(null);
    }
  }, []);

  React.useEffect(() => {
    void readReceipt();
  }, [readReceipt]);

  const gitSha = pick(release, "git_sha", "gitSha", "sha", "commit");
  const deployedAt = pick(release, "deployed_at", "deployedAt");
  const imageTag = pick(release, "image_tag", "imageTag", "image", "tag");
  const canaryStatus = pick(release, "canary_bundle_status", "canaryBundleStatus", "canary_status");
  const buildRunUrl = pick(release, "build_run_url", "buildRunUrl", "build_url");
  const deployRunUrl = pick(release, "deploy_run_url", "deployRunUrl", "deploy_url");
  const bakedStamp = bakedFetchedAt ? (mounted ? stamp(bakedFetchedAt) : fmtStampStable(bakedFetchedAt)) : "";

  return (
    <div className={styles.page}>
      <section className="cover" aria-labelledby="cover-title">
        <div className="container cover__inner">
          <p className="eyebrow">field notes · the ops room</p>
          <h1 id="cover-title" className="cover__title">The instrument panel.</h1>
          <p className="cover__lede">
            Every other page on this site makes a claim. This one explains how the
            claims are measured, what the engine reports about itself, and who
            watches it when no human is looking. No marketing here — just the
            readings and the fine print.
          </p>
          <p className="cover__caption voice">
            — if I&apos;m asleep, this page says so before I do.
          </p>
          <VitalSigns variant="hero" />
          <p className="cover__stamp ev">
            first paint seeded from snapshot {bakedStamp} · every reading
            above is upgraded by a live read on load and carries its own stamp
          </p>
        </div>
      </section>

      <section id="vitals" className="ch" aria-labelledby="vitals-title">
        <div className="container ch__inner">
          <p className="eyebrow">entry one · how the pulse is measured</p>
          <h2 id="vitals-title">Four readings, in plain words.</h2>
          <p className="voice vitals__lede">
            — the pulse strip up top is four separate facts, never collapsed into
            one. Here&apos;s exactly what each one means, so a green dot can never bluff
            you.
          </p>

          <dl className="measures">
            <div className="measure">
              <dt><span className="dot live" aria-hidden="true"></span> server live</dt>
              <dd>
                The <Term def="MCP — the Model Context Protocol. The open standard chatbots use to add outside tools. Tiny is one such tool.">MCP</Term>
                {" "}endpoint at <code>{MCP_BARE}</code> answered <em>this browser&apos;s</em>
                call, just now. It&apos;s reachability measured from where you&apos;re sitting —
                not a status page someone typed by hand. If the call fails, the strip
                says unreachable and shows the real error.
              </dd>
            </div>
            <div className="measure">
              <dt><span className="dot idle" aria-hidden="true"></span> loop awake</dt>
              <dd>
                A public universe shows activity within the last hour, <em>or</em> a
                run is executing right now. If neither is true, the loop is asleep —
                and the strip says asleep, plainly. This state is read live every
                time; it is never hardcoded, because the site got that wrong once and
                left a flat line showing as a pulse.
              </dd>
            </div>
            <div className="measure">
              <dt><span className="dot" aria-hidden="true"></span> lifetime runs</dt>
              <dd>
                The engine&apos;s queue keeps running counters of work it has taken
                through: <em>succeeded</em>, <em>failed</em>, and <em>pending</em>.
                The strip reports those numbers as the engine reports them — failures
                included, because a counter that only counts wins isn&apos;t a counter.
              </dd>
            </div>
            <div className="measure">
              <dt><span className="dot" aria-hidden="true"></span> deployed</dt>
              <dd>
                The engine&apos;s own release receipt: the git commit it&apos;s running and the
                time it says it deployed that commit. It&apos;s the engine describing
                itself, not the website guessing. The full receipt — image, canary
                verdict, and the GitHub Actions runs that built and shipped it — is
                read live just below.
              </dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="ch ch--receipt" aria-labelledby="receipt-title">
        <div className="container ch__inner">
          <p className="eyebrow">entry two · the engine&apos;s own receipt</p>
          <h2 id="receipt-title">What&apos;s actually deployed, by its own account.</h2>
          <p className="receipt__lede">
            Read live from <code>get_status</code> when you opened this page. These
            are the engine&apos;s words about its own release — not a value typed into
            this site.
          </p>

          <div className="receipt" aria-live="polite" data-state={rcState}>
            {rcState === "reading" ? (
              <p className="receipt__msg ev"><span className="dot idle" aria-hidden="true"></span> reading the release receipt from <code>{MCP_BARE}</code>…</p>
            ) : rcState === "error" ? (
              <>
                <p className="receipt__msg ev"><span className="dot error" aria-hidden="true"></span> couldn&apos;t read the receipt — this is a true reading.</p>
                <p className="receipt__err ev">{rcError}</p>
                <button className="receipt__refresh" onClick={() => void readReceipt()}>Refresh MCP</button>
              </>
            ) : rcState === "empty" ? (
              <>
                <p className="receipt__msg ev"><span className="dot idle" aria-hidden="true"></span> the engine answered, but reported no release_state in this read.</p>
                <p className="receipt__note">That&apos;s an honest gap, not a deployment claim. Read again, or check the build &amp; deploy runs on GitHub Actions directly.</p>
                <div className="receipt__links">
                  <a href={GH_ACTIONS} target="_blank" rel="noreferrer">GitHub Actions ↗</a>
                  <button className="receipt__refresh" onClick={() => void readReceipt()}>Refresh MCP</button>
                </div>
              </>
            ) : (
              <>
                <table className="rc-table">
                  <tbody>
                    <tr>
                      <th scope="row">git sha</th>
                      <td>{gitSha ?? "—"}</td>
                    </tr>
                    <tr>
                      <th scope="row">deployed at</th>
                      <td>{deployedAt ? `${stamp(deployedAt)} · ${rel(deployedAt)}` : "—"}</td>
                    </tr>
                    <tr>
                      <th scope="row">image tag</th>
                      <td>{imageTag ?? "—"}</td>
                    </tr>
                    <tr>
                      <th scope="row">canary bundle</th>
                      <td>{canaryStatus ?? "—"}</td>
                    </tr>
                    <tr>
                      <th scope="row">build run</th>
                      <td>
                        {buildRunUrl ? (
                          <a href={buildRunUrl} target="_blank" rel="noreferrer">build workflow run ↗</a>
                        ) : (
                          <span className="rc-none">not in this read — <a href={GH_ACTIONS} target="_blank" rel="noreferrer">all Actions ↗</a></span>
                        )}
                      </td>
                    </tr>
                    <tr>
                      <th scope="row">deploy run</th>
                      <td>
                        {deployRunUrl ? (
                          <a href={deployRunUrl} target="_blank" rel="noreferrer">deploy workflow run ↗</a>
                        ) : (
                          <span className="rc-none">not in this read — <a href={GH_ACTIONS} target="_blank" rel="noreferrer">all Actions ↗</a></span>
                        )}
                      </td>
                    </tr>
                  </tbody>
                </table>
                <p className="receipt__stamp ev">
                  read live {rel(rcFetchedAt)} ·
                  <button className="receipt__refresh receipt__refresh--inline" onClick={() => void readReceipt()}>Refresh MCP</button>
                </p>
              </>
            )}
          </div>
        </div>
      </section>

      <section className="ch ch--watch" aria-labelledby="watch-title">
        <div className="container ch__inner">
          <p className="eyebrow">entry three · the public watchdogs</p>
          <h2 id="watch-title">Who watches it when no one&apos;s looking.</h2>
          <p className="watch__lede">
            Two GitHub Actions watch the live system on a schedule. They&apos;re public —
            their run history, pass and fail, is on the Actions tab anyone can open.
          </p>
          <ul className="watch">
            {WATCHDOGS.map((w) => (
              <li className="watch__item" key={w.file}>
                <code className="watch__file">{w.file}</code>
                <p className="watch__what">{w.what}</p>
              </li>
            ))}
          </ul>
          <p className="watch__foot">
            <a href={GH_ACTIONS} target="_blank" rel="noreferrer">Open the Actions tab on GitHub ↗</a>
            {" "}— the live run history is the truth, not this page.
          </p>
        </div>
      </section>

      <section className="ch ch--legal" aria-labelledby="legal-title">
        <div className="container ch__inner">
          <p className="eyebrow">entry four · the fine print</p>
          <h2 id="legal-title">The part that has to be exact.</h2>
          <p className="legal__money voice">
            On money: any value or credit moving through Tiny today settles on a
            {" "}<em>test rail</em> — there&apos;s no payment method to ask for and nothing to
            buy. <strong>Nothing on this site is investment advice, and none of it
            represents equity, profit-sharing, or a price prediction.</strong>
          </p>
          <ul className="legal">
            <li className="legal__item">
              <a className="legal__link" href="/legal">Terms, token disclosures, risk &amp; DMCA →</a>
              <p className="legal__note">The full legal page: terms of use, token / currency disclosures, the risk statement, and the DMCA / takedown path.</p>
            </li>
          </ul>
        </div>
      </section>

      <section className="ch ch--close" aria-labelledby="close-title">
        <div className="container ch__inner">
          <h2 id="close-title">Seen the gauges. Now watch the work.</h2>
          <nav className="close__cards">
            <a className="close__card" href="/loop">
              <span className="close__k eyebrow">the patch loop</span>
              <strong>Watch how it maintains itself →</strong>
              <span className="close__sub">friction becomes a patch request, a real PR, a release — live runs and gates.</span>
            </a>
            <a className="close__card" href="/commons">
              <span className="close__k eyebrow">the public commons</span>
              <strong>Browse the brain — and the glossary →</strong>
              <span className="close__sub">every term of art, plus the searchable wiki it all reads from.</span>
            </a>
          </nav>
        </div>
      </section>
    </div>
  );
}
