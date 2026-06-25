"use client";

import * as React from "react";
import Term from "../../../components/Term";
import Tick from "../../../components/Tick";
import styles from "../page.module.css";

const REPO_URL = "https://github.com/Jonnyton/Workflow";

type RepoSnapshot = {
  fetched_at: string;
  repo: {
    default_branch?: string;
    main?: string;
    pushed_at?: string;
    open_issues?: number;
  };
};

const REPO_STEPS = [
  {
    cmd: "git clone https://github.com/Jonnyton/Workflow",
    note: "Clone the engine.",
    href: REPO_URL,
    label: "Workflow on GitHub",
  },
  {
    cmd: "pip install -e .[dev]",
    note: "Editable install with the dev extras (Python 3.11+).",
    href: `${REPO_URL}/blob/main/pyproject.toml`,
    label: "pyproject.toml",
  },
  {
    cmd: "pytest · ruff check",
    note: "Both green before every commit. Every module has tests; nodes never crash.",
    href: `${REPO_URL}/tree/main/tests`,
    label: "tests/",
  },
  {
    cmd: "read PLAN.md · CONTRIBUTING.md",
    note: "Architecture and how the system thinks (PLAN.md); how to land work (CONTRIBUTING.md).",
    href: `${REPO_URL}/blob/main/PLAN.md`,
    label: "PLAN.md",
  },
];

async function refreshRepoSnapshot(): Promise<RepoSnapshot> {
  const [repoRes, branchesRes] = await Promise.all([
    fetch("https://api.github.com/repos/Jonnyton/Workflow"),
    fetch("https://api.github.com/repos/Jonnyton/Workflow/branches?per_page=100"),
  ]);
  if (!repoRes.ok) throw new Error(`repo ${repoRes.status}`);
  if (!branchesRes.ok) throw new Error(`branches ${branchesRes.status}`);

  const repo = await repoRes.json();
  await branchesRes.json();

  return {
    fetched_at: new Date().toISOString(),
    repo: {
      default_branch: repo.default_branch,
      main: repo.default_branch,
      pushed_at: repo.pushed_at,
      open_issues: repo.open_issues_count,
    },
  };
}

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

export default function BuildClient() {
  const [repo, setRepo] = React.useState<RepoSnapshot | null>(null);
  const [repoErr, setRepoErr] = React.useState<string | null>(null);
  const [reading, setReading] = React.useState(false);

  const refreshRepo = React.useCallback(async () => {
    setReading(true);
    try {
      setRepo(await refreshRepoSnapshot());
      setRepoErr(null);
    } catch (e) {
      setRepoErr(e instanceof Error ? e.message : String(e));
    } finally {
      setReading(false);
    }
  }, []);

  React.useEffect(() => {
    void refreshRepo();
  }, [refreshRepo]);

  const rateLimited = !!repoErr && /\b(403|429|rate)\b/i.test(repoErr);

  return (
    <div className={styles.page}>
      <section className="cover" aria-labelledby="cover-title">
        <div className="container ch__inner">
          <p className="eyebrow">field notes · how I get rebuilt</p>
          <h1 id="cover-title" className="cover__title">Two doors into building me.</h1>
          <p className="voice cover__lede">
            You can improve me without ever cloning a line of code — just talk to me
            through your chatbot and describe what&apos;s rough. Or you can go straight at
            the engine through the repository, with the tests and the architecture in
            front of you. Both doors open onto the same room: a{" "}
            <Term def="The self-patching cycle: a request becomes an investigation, runs through automated checks, and only ships after review.">loop</Term>
            {" "}with evidence gates, a{" "}
            <Term def="A second AI from a different model family re-checks the work, so no one model both writes and approves a change.">cross-family review</Term>,
            and a <em>human key</em> that has to turn before anything merges.
          </p>
          <p className="cover__naming">
            The being is <strong>Tiny</strong>; the engine is <strong>Workflow</strong>.
            Contributing to either is contributing to both.
          </p>
        </div>
      </section>

      <section className="ch ch--door" aria-labelledby="door1-title">
        <div className="container">
          <p className="eyebrow">door one · no clone required</p>
          <h2 id="door1-title">Build me through your chatbot.</h2>
          <p className="voice door__lede">
            If you can hold a conversation, you can file work that lands in my
            engine. You never touch a terminal.
          </p>
          <ol className="steps">
            <li className="step">
              <span className="step__n">01</span>
              <div className="step__body">
                <h3 className="step__h">Connect</h3>
                <p className="step__p">Paste my URL into Claude, ChatGPT, or any MCP-capable assistant.</p>
                <a className="step__cta" href="/start">how to connect →</a>
              </div>
            </li>
            <li className="step">
              <span className="step__n">02</span>
              <div className="step__body">
                <h3 className="step__h">Hit a rough edge — or have an idea</h3>
                <p className="step__p">A confusing response, a missing capability, a sharper way to do something. Friction and ideas count equally.</p>
              </div>
            </li>
            <li className="step">
              <span className="step__n">03</span>
              <div className="step__body">
                <h3 className="step__h">Say it out loud</h3>
                <p className="step__p">Tell your chatbot: <code>file a patch request about …</code> — describe the rough edge in plain words. It&apos;s filed against my public commons.</p>
              </div>
            </li>
            <li className="step">
              <span className="step__n">04</span>
              <div className="step__body">
                <h3 className="step__h">It enters the loop</h3>
                <p className="step__p">Your request becomes an investigation, runs through evidence gates, and can surface as a real GitHub PR.</p>
                <a className="step__cta" href="/loop">watch the loop →</a>
              </div>
            </li>
            <li className="step">
              <span className="step__n">05</span>
              <div className="step__body">
                <h3 className="step__h">Watch it become a change</h3>
                <p className="step__p">From investigation to pull request to release, the whole trail is public — successes and failures alike.</p>
              </div>
            </li>
          </ol>
          <p className="door__note voice">
            One honest caveat: <em>a merge always waits on a human key.</em> No
            change ships on AI momentum alone. That&apos;s a feature, not friction — it&apos;s
            why you can trust what lands.
          </p>
        </div>
      </section>

      <section className="ch ch--door" aria-labelledby="door2-title">
        <div className="container">
          <p className="eyebrow">door two · clone the engine</p>
          <h2 id="door2-title">Build me through the repository.</h2>
          <p className="voice door__lede">
            Prefer to work in code directly? The engine is open source. Clone it,
            install it, and the same gates apply to your branch as to mine.
          </p>
          <ol className="repo-steps">
            {REPO_STEPS.map((s) => (
              <li className="repo-step" key={s.cmd}>
                <code className="repo-step__cmd">{s.cmd}</code>
                <p className="repo-step__note">{s.note}</p>
                <Tick href={s.href} label={s.label} external />
              </li>
            ))}
          </ol>
          <p className="door__note">
            Read <a href={`${REPO_URL}/blob/main/PLAN.md`} target="_blank" rel="noreferrer">PLAN.md</a>
            {" "}for the architecture and{" "}
            <a href={`${REPO_URL}/blob/main/CONTRIBUTING.md`} target="_blank" rel="noreferrer">CONTRIBUTING.md</a>
            {" "}for how work lands. When you&apos;re ready, open a pull request against{" "}
            <a href={REPO_URL} target="_blank" rel="noreferrer">Workflow on GitHub ↗</a>.
          </p>
        </div>
      </section>

      <section className="ch ch--pulse" aria-labelledby="pulse-title">
        <div className="container ch__inner">
          <p className="eyebrow">live reading · the repository, right now</p>
          <h2 id="pulse-title">The engine, read live from GitHub.</h2>
          <div className="pulse" aria-live="polite">
            {reading && !repo && !repoErr ? (
              <p className="pulse__state ev">reading the repository…</p>
            ) : repoErr ? (
              <>
                <p className="pulse__state pulse__state--err ev">
                  {rateLimited ? (
                    <>
                      GitHub&apos;s API rate-limited this read. This page calls GitHub
                      unauthenticated from your browser, so anonymous reads can be
                      throttled — that&apos;s the honest reason, not a server failure.
                    </>
                  ) : (
                    <>live read failed — {repoErr}</>
                  )}
                </p>
                <button className="pulse__refresh" onClick={refreshRepo} disabled={reading}>{reading ? "reading…" : "Refresh GitHub"}</button>
              </>
            ) : repo ? (
              <>
                <dl className="pulse__grid">
                  <div className="pulse__cell">
                    <dt className="pulse__k">default branch</dt>
                    <dd className="pulse__v ev">{repo.repo.default_branch ?? repo.repo.main ?? "—"}</dd>
                  </div>
                  <div className="pulse__cell">
                    <dt className="pulse__k">open issues</dt>
                    <dd className="pulse__v ev">{(repo.repo.open_issues ?? 0).toLocaleString()}</dd>
                  </div>
                  <div className="pulse__cell">
                    <dt className="pulse__k">last push</dt>
                    <dd className="pulse__v ev">{repo.repo.pushed_at ? rel(repo.repo.pushed_at) : "unknown"}</dd>
                  </div>
                </dl>
                <p className="pulse__stamp ev">
                  read {rel(repo.fetched_at)} from GitHub ·
                  <button className="pulse__refresh" onClick={refreshRepo} disabled={reading}>{reading ? "reading…" : "Refresh GitHub"}</button>
                  {" "}· <Tick href={REPO_URL} label="open the repo" external />
                </p>
              </>
            ) : null}
          </div>
        </div>
      </section>

      <section className="ch ch--earns" aria-labelledby="earns-title">
        <div className="container ch__inner">
          <p className="eyebrow">honest terms · what contribution earns</p>
          <h2 id="earns-title">Your work is tracked. Credit is honest about where it stands.</h2>
          <p className="voice">
            Everything you contribute is recorded — runs you trigger, designs of
            yours that get used, code that merges, the lineage of what you forked
            from, and the feedback you leave. Credit settles on a{" "}
            <Term def="A non-monetary accounting rail used to prove the credit machinery works before any real value moves.">test rail</Term>
            {" "}today; a real economy comes <em>later</em>, not now. What&apos;s solid right
            now is attribution: your name on what you made survives even when
            someone forks it. No income is promised here — see the{" "}
            <a href="/legal#token-disclosures">token disclosures</a> for the fine print.
          </p>
        </div>
      </section>

      <section className="ch ch--close" aria-labelledby="close-title">
        <div className="container ch__inner">
          <h2 id="close-title" className="sr-only">Where to go next</h2>
          <div className="close__row">
            <a className="close__card" href="/commons">
              <span className="close__k eyebrow">the design conversation</span>
              <strong>It lives in the commons.</strong>
              <span className="close__sub">read the public brain — proposals, notes, and decisions, all forkable.</span>
            </a>
            <a className="close__card" href="/graph">
              <span className="close__k eyebrow">the map of everything</span>
              <strong>See the whole graph.</strong>
              <span className="close__sub">how every goal, workflow, and commons page connects.</span>
            </a>
          </div>
        </div>
      </section>
    </div>
  );
}
