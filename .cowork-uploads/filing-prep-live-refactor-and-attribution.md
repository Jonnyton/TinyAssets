# Workflow proposal — live wiki refactoring + multi-generation attribution

A user observation and design proposal about how the platform should handle scale and credit. Filed as a reference document; please decide whether this lands as a wiki design entry, a bug, multiple smaller filings, or something else, and file it accordingly.

## The problem this is trying to solve

The Workflow community patch loop is approaching a future where dozens (eventually hundreds) of users are submitting patch requests through their own chatbots. Today the loop has a few users at a time, and so far that's been manageable. As volume grows, two related failure modes become severe.

**Failure mode 1: fragmented work.** Five users describe what is essentially the same underlying issue, in five different vocabularies. The platform's current dedup catches identical text (file_bug rejects exact duplicates; wiki rejects identical slugs), but that's pre-filing dedup. The harder case is post-filing: a request comes in, looks distinct on the surface, but is actually about the same underlying thing as three open requests already. Today the loop investigates each one independently. That wastes investigation cycles, produces five competing patches that contradict each other, and confuses contributors who can't tell which investigation to engage with. At ten or fifty concurrent users, this fragmentation becomes the dominant failure mode.

**Failure mode 2: missing credit.** When a patch eventually ships, the contribution model today is essentially "whoever filed the initial bug." But the actual contribution graph is much wider. Other users may have filed similar issues that helped frame the problem. Other users may have requested the feature in different vocabulary, or pushed for it months ago, or designed a branch that got remixed into the eventual solution — and that branch may itself have been remixed from an earlier branch that someone else designed, and so on through several generations of community evolution. Daemons run nodes during investigation and implementation, contributing structured work. Some of these contributors are users via chatbot; some are devs via PRs; many are the same person across both surfaces. None of them get credit today beyond the initial filer.

Both failure modes share a root: the loop doesn't track the full participation graph as work moves from request to ship. Fix that graph and both fix.

## What's there today that already helps

Branch lineage is partly tracked — `lineage_parent_id` exists on daemon souls and presumably on branch versions; remix history is preserved. file_bug dedup-at-filing is in place per the host directive captured in PLAN.md. The wiki has structured categories. Daemons are addressable identities (souls + memory + brains in the existing `workflow/daemon_brain.py` + `daemon_memory.py` + `docs/souls/`). GitHub PRs are tracked. Cross-provider user identity is the load-bearing primitive that probably isn't built yet (chatbots may show up to the MCP as anonymous clients) — that's a related substrate gap I'm filing separately because it's a prerequisite for several scale-related capabilities, but it specifically blocks attribution to a stable user identity here.

## Proposal — two pieces, bundled

### Piece 1: Live wiki refactoring

When a new wiki entry or file_bug arrives, the platform should examine it against currently open entries and either cluster it into an existing investigation or start a new one. Specifics:

- Similarity check at filing time, beyond exact-match dedup. Probably embedding-based or LLM-judged, not pure text overlap. Threshold-tuned per wiki category (more lenient for bugs that often share root cause; stricter for distinct feature requests).
- When a new entry clusters into an existing investigation, the wiki entry doesn't disappear — it becomes a member of the cluster, and the investigation gains the new entry's framing. The original filer is still tracked. The cluster's investigation becomes a multi-source view rather than a single-source one.
- The loop should be able to refactor the cluster as understanding deepens. Two requests that initially looked the same may turn out to be distinct after investigation; the cluster splits. Two investigations that initially looked distinct may turn out to share root cause; the clusters merge. This is iterative and the loop drives it through whatever evidence accumulates.
- Cluster membership is visible to users in the wiki. When a user files something that clusters into an existing investigation, they see "your filing was added to investigation X — see the existing thread, others are working on it too." This is also a UX win — users feel heard rather than dropped into a void.
- Threshold for "distinct enough to be its own investigation" is probably wiki-evolved itself. Different wiki categories may want different thresholds. The platform ships a default; community refines.

### Piece 2: Multi-generation attribution

When a patch ships, every contributor should be credited. The contribution graph the platform tracks should include:

- Every user who filed an entry that ended up clustered with the original (cluster contribution).
- The user who designed the branch that got remixed into the solution (direct branch lineage).
- The user who designed the parent branch that THAT branch was remixed from, and so on, several generations back through the remix chain (transitive branch lineage).
- The daemons whose nodes ran during investigation and implementation (per-node daemon contribution). The daemon's owner is the user who summoned/configured it (or the platform itself for core team daemons); attribution propagates upward through the daemon registry.
- The dev who reviewed and merged any PR that's part of the patch (review contribution).

Each contributor's identity is one of: a known user account (cross-provider — same user on ChatGPT and Claude.ai is one identity; chatbot login is the bridge), a known GitHub account, or a daemon identity (which itself resolves to a user-or-platform owner). When a contribution is anonymous (e.g., chatbot session without verified login), it's tagged as such; when it later becomes claimable (the user logs in or links accounts), the credit retroactively attaches.

The credit isn't necessarily monetary today. It might just be "your name appears on the patch's evidence record" or "you appear in the patch's contributor list in the wiki." But the substrate has to be in place before any monetization or reputation system can layer on top.

## Why bundle these two

Clustering and attribution are tightly coupled. Without clustering, attribution is shallow (only the initial filer gets credit). With clustering but without attribution, the clustered users don't get credit even though their filings shaped the investigation. With both, each filing matters: filing a similar bug to one already open isn't wasted effort — it's a vote, framing input, and credit-share. That changes user incentives for the better — they stop hesitating to file because "someone probably already filed this," because filing IS contribution even when it clusters.

## How this would land

I'd file this as a wiki design proposal first, then let the loop produce its own investigation. Likely substrate work the loop will identify:

- A similarity index over open wiki entries (embedding or LLM-judged)
- A clustering primitive (with refactor-merge-split operations)
- A contribution graph data structure (extends existing branch_versions + lineage tracking)
- An attribution surface in the wiki (contributor lists on patches, on cluster pages, on user profiles)
- Cross-provider user identity through MCP handshake (load-bearing prerequisite — separate filing)
- Reputation / weighted-credit primitives (probably v0.5, after the basic attribution is in)

If you'd rather break this into smaller filings (e.g., clustering as one, attribution as another, identity as a separate prerequisite), feel free. My instinct is to keep them bundled because the bundling is the point — each motivates the other. But you may know the loop's existing patterns better than me.

## Context for whoever picks this up

This filing exists partly to prep the loop for an oncoming barrage of related-but-distinct user observations and feature requests I'm planning to file in close succession over the next several hours. Those filings will themselves test the clustering capability proposed here. If clustering doesn't work yet, the failure mode will be visible — investigations will fragment across the barrage. That's intentional: the failure is data about what to fix.

The connection to existing platform discipline: this proposal is consistent with the commons-first scoping rule (cluster identity is platform-stored / public; contributor identity respects existing privacy boundaries — host-resident accounts stay host-resident, public commits get GitHub credit). Consistent with minimal-primitives — the actual new primitives proposed are small (similarity + cluster + contribution graph); a lot of the surface (wiki rendering, attribution display) is composition over them. Consistent with community-build — once the primitives ship, the threshold tuning and contribution-display patterns are exactly the kind of thing the community can iterate on.
