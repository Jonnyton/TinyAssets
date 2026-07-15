# Operating Notes — Constraints & Long-Roadmap (2026-07-09)

Adopted at the end of the design sprint's holistic review. These bind transport work and long-range planning alongside SUCCESSION and USER-PATH.

## 1. Non-custodial constraint (BINDING on Wave 2)
The platform must NEVER custody user funds. Escrow lives in smart contracts on Base; the platform computes settlements (ledger.py adapters) but never controls keys. Rationale: custodying buyer/seller funds at scale is money-transmitter territory across most jurisdictions — the architecture, not a license, is the mitigation. The ledger core is custody-agnostic by design; Wave 2 MUST wire it non-custodially. Any design that puts user funds in a platform-controlled account is wrong-shaped; stop and escalate.

## 2. North-star metrics (pre-revenue)
Revenue is 1% of near-zero for the first year — do not steer by it. The two curves that matter and that the seed round is raised on:
- Demand side: **weekly gate claims** (universes genuinely achieving outcomes)
- Supply side: **dollars earned by sellers/makers**
Instrument both from day one. Leading indicator ahead of both: standing goals per active universe (demand-side design note §1).

## 3. Prohibited-use & moderation (pre-launch gate)
A permissionless fabrication market WILL receive firearm-component requests in week one; datasets have PII risk; models and workflows have abuse surfaces. "We're neutral" is not an answer payment partners or regulators accept. Before launch: a written prohibited-use policy + a review path for fabrication jobs and dataset registration. This does not need to be clever; it needs to exist. (Scope for founder + counsel with the Track H/token engagement. Includes the Track I §I7 garage-fab safety gate: fab-chemistry capability listings without safety documentation fail closed.)

## 4. Payments & card strategy (long roadmap, sequenced)
- **Now → launch:** no card. Incentives are platform-credit bonuses on the existing ledger (already buildable).
- **Seller-scale milestone (~thousands of earning sellers):** **earnings debit card** via issuing-as-a-service — sellers spend their capacity earnings anywhere. The marketing sentence is the product: "my gaming PC bought my coffee." Months-scale project; inherits KYC/compliance program; do not start before real seller earnings exist.
- **Customer-scale milestone (six-figure customers, proven spend):** **co-brand credit card**, rewards at a competitive rate **paid in platform credits** (credits cost below face value and recycle into GMV — the rewards program feeds the flywheel instead of bleeding interchange). Requires issuing-bank partner + program manager; 12–18 months from start; year-3-class item.
- Discipline: cards are acquisition/retention spend wearing payments costumes — judge them as marketing, gate them on the milestones above, and never let a card program precede the flow it's meant to amplify.

## 5. Standing discipline (from the holistic review)
- Focus test: if month nine has a thriving commons and zero live markets, that is SUCCESS.
- Channel independence: assume closed chatbot directories are late or hostile; OpenClaw-class open ecosystems are the first door.
- Founder runway (financial and psychological) is a budgeted line item, not an afterthought.
