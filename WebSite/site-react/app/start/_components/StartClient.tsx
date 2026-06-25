"use client";

import * as React from "react";
import { fetchVitals, type Vitals } from "../../../lib/live";
import { fmtRel } from "../../../lib/fmt";
import Tick from "../../../components/Tick";
import Term from "../../../components/Term";
import styles from "../page.module.css";

const MCP_URL = "https://tinyassets.io/mcp";
const MCP_BARE = MCP_URL.replace("https://", "");
const GH_REPO = "https://github.com/Jonnyton/Workflow";
const GH_ISSUES = "https://github.com/Jonnyton/Workflow/issues";
const GH_CONTRIBUTING = "https://github.com/Jonnyton/Workflow/blob/main/CONTRIBUTING.md";

// ── Six persona starter prompts — each copyable, each works today
// via the universe / goals / wiki tools. ──
type Prompt = { persona: string; flavor: string; text: string };
const PROMPTS: Prompt[] = [
  {
    persona: "The researcher",
    flavor: "orient first",
    text: "Inspect my Workflow universe and show me what goals exist.",
  },
  {
    persona: "The maker",
    flavor: "build something",
    text: "Help me design a workflow toward <my goal> and run a dry run.",
  },
  {
    persona: "The novelist",
    flavor: "long project",
    text: "Create a universe for my novel <title> with my premise, and propose a goal with a ladder toward a finished draft.",
  },
  {
    persona: "The shop owner",
    flavor: "commerce, carefully",
    text: "Draft me a product packet for <idea> and stop before anything publishes or spends money.",
  },
  {
    persona: "The curious",
    flavor: "see the whole thing",
    text: "Browse the public commons and tell me what this platform is working on right now.",
  },
  {
    persona: "The contributor",
    flavor: "file friction",
    text: "File a patch request about <a rough edge I hit>.",
  },
];

export default function StartClient() {
  // ── Copyable MCP URL chip (same idiom as home's urlchip). ──
  const [copied, setCopied] = React.useState(false);
  const copyTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  async function copyUrl() {
    try {
      await navigator.clipboard.writeText(MCP_URL);
      setCopied(true);
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard unavailable; URL is still visible */
    }
  }

  // ── Live reachability proof — read before you paste. Never baked. ──
  const [vitals, setVitals] = React.useState<Vitals | null>(null);
  const [reading, setReading] = React.useState(true);
  const refreshPulse = React.useCallback(async () => {
    setReading(true);
    const v = await fetchVitals();
    setVitals(v);
    setReading(false);
  }, []);
  React.useEffect(() => {
    void refreshPulse();
  }, [refreshPulse]);

  const [copiedPrompt, setCopiedPrompt] = React.useState<number | null>(null);
  const promptTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  async function copyPrompt(i: number, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedPrompt(i);
      if (promptTimer.current) clearTimeout(promptTimer.current);
      promptTimer.current = setTimeout(() => setCopiedPrompt(null), 1800);
    } catch {
      /* clipboard unavailable; the prompt is visible anyway */
    }
  }

  return (
    <div className={styles.page}>
      {/* 1 · Hero — prove the door is open, then paste */}
      <section className="cover" aria-labelledby="cover-title">
        <div className="container cover__grid">
          <div className="cover__main">
            <p className="eyebrow">how to connect · entry one</p>
            <h1 id="cover-title" className="cover__title">Connect your chatbot.</h1>
            <p className="cover__lede">
              One URL turns any
              {" "}<Term def="MCP — the Model Context Protocol. The open standard chatbots use to add outside tools. Tiny is one such tool.">MCP</Term>-capable
              {" "}chatbot into a control station for Tiny: it can browse the public
              commons, design workflows with you, and start real runs. No account,
              no install — just paste the address below into your assistant&apos;s
              connector settings.
            </p>
            <div className="cover__actions">
              <button type="button" className="urlchip" onClick={copyUrl} aria-label="Copy the MCP URL">
                <code>{MCP_BARE}</code>
                <span className="urlchip__copy">{copied ? "copied ✓" : "copy"}</span>
              </button>
              <a className="cover__skip" href="#paths">jump to the steps ↓</a>
            </div>
          </div>

          <div className="cover__pulse">
            <p className="eyebrow">is the door open? read it yourself</p>
            <div className="pulse" aria-live="polite">
              {reading && !vitals ? (
                <span className="pulse__row"><span className="dot" aria-hidden="true"></span><span className="pulse__k">reading the endpoint…</span></span>
              ) : vitals && !vitals.reachable ? (
                <>
                  <span className="pulse__row"><span className="dot error" aria-hidden="true"></span><span className="pulse__k">endpoint unreachable from your browser</span></span>
                  <span className="pulse__sub ev">this is a true reading — {vitals.error}</span>
                  <button className="pulse__refresh" onClick={refreshPulse} disabled={reading}>{reading ? "reading…" : "Refresh MCP"}</button>
                </>
              ) : vitals ? (
                <>
                  <span className="pulse__row">
                    <span className="dot live" aria-hidden="true"></span>
                    <span className="pulse__k">engine live</span>
                  </span>
                  {vitals.deployedAt && (
                    <span className="pulse__sub ev">deployed {fmtRel(vitals.deployedAt)}{vitals.gitSha ? <>&nbsp;· {vitals.gitSha}</> : null}</span>
                  )}
                  <span className="pulse__row pulse__row--quiet">
                    <span className={`dot ${vitals.loopAwake ? "live" : "idle"}`} aria-hidden="true"></span>
                    <span className="pulse__k">{vitals.loopAwake ? "loop awake" : "loop asleep"}</span>
                  </span>
                  <span className="pulse__stamp ev">
                    read {fmtRel(vitals.fetchedAt)}
                    {" "}· <button className="pulse__refresh" onClick={refreshPulse} disabled={reading}>{reading ? "reading…" : "Refresh MCP"}</button>
                  </span>
                  <span className="pulse__tick"><Tick href="/fine-print" label="how this is measured" /></span>
                </>
              ) : null}
            </div>
            <p className="cover__pulse-note voice">
              — you&apos;re reading my pulse through the same door you&apos;re about to
              walk through.
            </p>
          </div>
        </div>
      </section>

      {/* 1.5 · Before you paste — two honest things */}
      <section className="ch ch--honest" aria-labelledby="honest-title">
        <div className="container ch__inner ch__inner--wide">
          <p className="eyebrow">before you paste · two honest things</p>
          <h2 id="honest-title">Where your work lives.</h2>
          <div className="honest">
            <article className="honest__card">
              <h3 className="honest__h">Public by default</h3>
              <p className="honest__p">
                Work you do on the public engine lands in a public,
                forkable <Term def="The commons — the shared, public store of universes, workflows, and runs. Anyone can read it, and anyone can fork from it.">commons</Term>
                {" "}that anyone can read.
              </p>
              <p className="honest__p">
                Keeping work private currently means running the engine yourself —
                <a href="/host">see how to host it</a>.
              </p>
            </article>
            <article className="honest__card">
              <h3 className="honest__h">Yours to take</h3>
              <p className="honest__p">
                Universes and the commons are plain files in an open-source store, so
                you can export your work at any time.
              </p>
              <p className="honest__p">
                The engine&apos;s code is <strong>MIT-licensed</strong> on
                {" "}<a href={GH_REPO} target="_blank" rel="noreferrer">GitHub ↗</a>.
              </p>
            </article>
          </div>
          <p className="honest__cap voice">
            — no surprises after the paste. This is the deal up front.
          </p>
        </div>
      </section>

      {/* 2 · Two real connect paths */}
      <section id="paths" className="ch ch--paths" aria-labelledby="paths-title">
        <div className="container">
          <p className="eyebrow">entry two · the two simple steps</p>
          <h2 id="paths-title">Add the URL, then talk.</h2>
          <p className="paths__lede">
            Connecting is two steps in any client: register the connector, then
            start a chat with it enabled. The exact menu path differs per chatbot —
            here are the two that work today.
          </p>

          <div className="paths">
            <article className="connect">
              <header className="connect__head">
                <strong className="connect__name">Claude.ai</strong>
                <span className="connect__badge connect__badge--live">works today</span>
              </header>
              <p className="connect__who">
                Best path if Claude is where you already ask for help. Free, Pro,
                Max, Team, and Enterprise can add a custom remote connector, within
                plan limits.
              </p>
              <ol className="connect__steps">
                <li><span className="connect__n">1</span><span className="connect__t">Open <strong>Settings → Connectors</strong>.</span></li>
                <li><span className="connect__n">2</span><span className="connect__t">Choose <strong>Add custom connector</strong>.</span></li>
                <li><span className="connect__n">3</span><span className="connect__t">Paste <code>{MCP_BARE}</code> and approve it.</span></li>
                <li><span className="connect__n">4</span><span className="connect__t">Start a chat with the connector enabled and send a starter prompt below.</span></li>
              </ol>
              <p className="connect__note">
                The custom-URL path is the current one. A Claude directory listing
                is still pending, so this page doesn&apos;t claim directory acceptance.
              </p>
            </article>

            <article className="connect">
              <header className="connect__head">
                <strong className="connect__name">ChatGPT &amp; other MCP clients</strong>
                <span className="connect__badge connect__badge--partial">depends on the client</span>
              </header>
              <p className="connect__who">
                The same URL is a standard remote MCP server, so any MCP-capable
                client connects the same way — paste it into the connector / remote
                MCP field.
              </p>
              <ol className="connect__steps">
                <li><span className="connect__n">1</span><span className="connect__t">Open your client&apos;s <strong>connectors / MCP servers</strong> setting.</span></li>
                <li><span className="connect__n">2</span><span className="connect__t">Add <code>{MCP_BARE}</code> as a Streamable HTTP / remote MCP server.</span></li>
                <li><span className="connect__n">3</span><span className="connect__t">Enable it in a chat and send a starter prompt below.</span></li>
              </ol>
              <p className="connect__note">
                So which should you use today? The reliable path is
                {" "}<strong>Claude.ai</strong> — or any client that supports custom MCP
                connectors. On ChatGPT specifically, custom connectors require a paid
                plan with developer mode turned on, and availability still varies by
                workspace and region. We track where that actually stands here:
                {" "}<a href={GH_ISSUES} target="_blank" rel="noreferrer">current status on Workflow on GitHub ↗</a>.
              </p>
            </article>
          </div>
        </div>
      </section>

      {/* 3 · What to say first */}
      <section className="ch ch--prompts" aria-labelledby="prompts-title">
        <div className="container">
          <p className="eyebrow">entry three · what to say first</p>
          <h2 id="prompts-title">Bring a first sentence.</h2>
          <p className="prompts__lede voice">
            — connected and not sure what to ask? Here are six openers, one per
            kind of visitor. Each works today through my universe, goals, and
            commons tools. Swap the bracketed bits for your own.
          </p>

          <ul className="prompts">
            {PROMPTS.map((p, i) => (
              <li className="prompt" key={p.persona}>
                <div className="prompt__head">
                  <span className="prompt__persona">{p.persona}</span>
                  <span className="prompt__flavor ev">{p.flavor}</span>
                </div>
                <button
                  type="button"
                  className="prompt__block"
                  onClick={() => copyPrompt(i, p.text)}
                  aria-label={`Copy prompt: ${p.text}`}
                >
                  <code className="prompt__text">{p.text}</code>
                  <span className="prompt__copy">{copiedPrompt === i ? "copied ✓" : "copy"}</span>
                </button>
              </li>
            ))}
          </ul>
          <p className="prompts__foot">
            Wondering what a &ldquo;goal&rdquo; or the &ldquo;commons&rdquo; is? Open the live
            {" "}<a href="/goals">goals board</a> — it reads the real list straight from
            the engine.
          </p>
        </div>
      </section>

      {/* 4 · Other ways in */}
      <section className="ch ch--oss" aria-labelledby="oss-title">
        <div className="container ch__inner ch__inner--wide">
          <p className="eyebrow">entry four · other ways in</p>
          <h2 id="oss-title">Or run the engine yourself.</h2>
          <p className="oss__lede">
            Tiny is the public face of <strong>Workflow</strong>, an open-source
            engine. You don&apos;t need to host anything to use the connector above — but
            if you&apos;d rather run it locally or read the code, both paths are real.
          </p>
          <div className="oss">
            <article className="oss__card">
              <h3 className="oss__h">Clone the repo</h3>
              <p className="oss__p">
                Read the engine, the loop, and every workflow definition. It&apos;s all
                public.
              </p>
              <pre className="oss__pre"><code>git clone {GH_REPO}.git</code></pre>
              <a className="oss__cta" href={GH_REPO} target="_blank" rel="noreferrer">Workflow on GitHub ↗</a>
            </article>
            <article className="oss__card">
              <h3 className="oss__h">Run it locally</h3>
              <p className="oss__p">
                Python 3.11+. Install in editable mode and you have a local daemon
                to work against.
              </p>
              <pre className="oss__pre"><code>pip install -e .</code></pre>
              <a className="oss__cta" href={GH_CONTRIBUTING} target="_blank" rel="noreferrer">CONTRIBUTING.md ↗</a>
            </article>
          </div>
        </div>
      </section>

      {/* 5 · Close */}
      <section className="ch ch--close" aria-labelledby="close-title">
        <div className="container ch__inner">
          <h2 id="close-title">Connected. Now look around.</h2>
          <nav className="close__cards">
            <a className="close__card" href="/goals">
              <span className="close__k eyebrow">the goals board</span>
              <strong>See what&apos;s already running →</strong>
              <span className="close__sub">live public goals, each with its outcome ladder.</span>
            </a>
            <a className="close__card" href="/loop">
              <span className="close__k eyebrow">the patch loop</span>
              <strong>Watch how it maintains itself →</strong>
              <span className="close__sub">friction becomes a patch request, a real PR, a release.</span>
            </a>
          </nav>
        </div>
      </section>
    </div>
  );
}
