import type { Metadata } from "next";
import Link from "next/link";
import { RitualLabel } from "@tiny/design-system";
import { Reachability } from "../../components/Reachability";
import { SITE } from "../../lib/site";

export const metadata: Metadata = {
  title: "Fine print",
  description:
    "What is true right now: whether the public endpoint is reachable, what free includes, what premium changes, what does not exist yet, and where the boundaries are.",
  alternates: { canonical: `${SITE.origin}/fine-print/` },
};

export default function FinePrintPage() {
  return (
    <>
      <section className="container hero">
        <RitualLabel>Fine print</RitualLabel>
        <h1>What is true right now.</h1>
        <p className="lead">
          The operational facts, the limits and the boundaries, in one place. Live readings are
          stamped with when they were read; everything else says when it was last checked.
        </p>
      </section>

      <section className="section" id="reachability">
        <div className="container">
          <div className="head">
            <RitualLabel>Reachability</RitualLabel>
            <h2>Can your browser reach the public endpoint?</h2>
          </div>
          <Reachability />
        </div>
      </section>

      <section className="section" id="plans">
        <div className="container">
          <div className="head">
            <RitualLabel>Plans</RitualLabel>
            <h2>Every universe starts free.</h2>
            <p>
              Most people never need more than the free tier. Premium exists for the ones who run a
              lot.
            </p>
          </div>
          <div className="ledger--wrap">
            <table className="ledger">
              <thead>
                <tr>
                  <th>Plan</th>
                  <th>What you get</th>
                  <th>Limits</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Free</td>
                  <td>
                    A universe: brain, storage, connections, automations, workspaces, and the app on
                    every surface. Runs on your own subscription.
                  </td>
                  <td>
                    Daily limits on outside-world actions, compute minutes and storage, set well above
                    ordinary use.
                  </td>
                </tr>
                <tr>
                  <td>Premium, $20 a month</td>
                  <td>The same universe, nothing held back.</td>
                  <td>Higher daily limits on all three.</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="note">
            Upgrading happens per account from inside the app. If you hit a limit before that control
            ships, write to <a href={`mailto:${SITE.contact.general}`}>{SITE.contact.general}</a>. The
            platform never bills you for a model; your subscription is your own.
          </p>
        </div>
      </section>

      <section className="section" id="not-yet">
        <div className="container split">
          <div>
            <RitualLabel>What does not exist</RitualLabel>
            <h2>Said plainly, so you do not go looking.</h2>
            <ul className="steps" style={{ counterReset: "none" }}>
              <li style={{ gridTemplateColumns: "1fr" }}>
                <div>
                  <h3>No platform model</h3>
                  <p>TinyAssets never supplies an LLM. Without a connected subscription your universe exists but cannot think.</p>
                </div>
              </li>
              <li style={{ gridTemplateColumns: "1fr" }}>
                <div>
                  <h3>No list of integrations</h3>
                  <p>There is one connection primitive. Every integration is built by your universe from what you paste.</p>
                </div>
              </li>
              <li style={{ gridTemplateColumns: "1fr" }}>
                <div>
                  <h3>No signed desktop installer, no Play listing yet</h3>
                  <p>The Android build is a pre-release APK; desktop builds are unsigned and come from the repository.</p>
                </div>
              </li>
              <li style={{ gridTemplateColumns: "1fr" }}>
                <div>
                  <h3>No paid work market</h3>
                  <p>Nothing on this site is an offer to sell anything, and no currency moves. The <Link href="/legal/">legal page</Link> carries the disclosures.</p>
                </div>
              </li>
            </ul>
          </div>
          <div>
            <RitualLabel>Boundaries</RitualLabel>
            <h2 style={{ fontSize: "var(--fs-2xl)" }}>What the platform enforces.</h2>
            <table className="ledger" style={{ marginTop: 12 }}>
              <tbody>
                <tr>
                  <td>Isolation</td>
                  <td>
                    Not affecting other users is the one hard invariant. Inside your own universe you
                    have full authority.
                  </td>
                </tr>
                <tr>
                  <td>Credentials</td>
                  <td>
                    What you deposit goes to your universe&apos;s vault over TLS and is used only by
                    your universe. It never passes through a chat.
                  </td>
                </tr>
                <tr>
                  <td>Execution</td>
                  <td>
                    Nothing runs outside a universe someone controls. Every run has an owner who can
                    see, pause and delete it.
                  </td>
                </tr>
                <tr>
                  <td>Previews of this site</td>
                  <td>
                    Pull-request previews are served from an isolated worker that cannot reach the
                    live endpoint; they render checked-in evidence only.
                  </td>
                </tr>
                <tr>
                  <td>Indexing</td>
                  <td>
                    Public pages welcome search and AI crawlers. <span className="ev">/account</span> and
                    the app&apos;s private paths are excluded.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="section section--tight">
        <div className="container narrow">
          <p className="note">
            Canonical surfaces: the site is <span className="ev">tinyassets.io</span>, the endpoint is{" "}
            <span className="ev">tinyassets.io/mcp</span>, the code is{" "}
            <span className="ev">github.com/Jonnyton/TinyAssets</span>. Anything else is not us.
            Terms, privacy and disclosures: <Link href="/legal/">legal</Link>.
          </p>
        </div>
      </section>
    </>
  );
}
