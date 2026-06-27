# Workflow Moderation Rubric

**Version:** 1.0
**Last updated:** 2026-04-19
**Status:** v1 first-draft. Changes land via PR to `TinyAssets/`; 2 admin-pool members must approve per `SUCCESSION.md` bus-factor rule + `docs/specs/2026-04-18-moderation-mvp.md` §6.
**Canonical home:** this file in `TinyAssets/` repo (platform-code side of the two-repo split).

---

## What this rubric is

This is what **volunteer moderators use to resolve flagged content**. Community-flagged moderation (per host Q10): users flag, volunteer mods review against this rubric, host-admin pool handles appeals + edge cases. Platform does NOT take down legal content proactively; community judgment + this rubric drive action.

**Read this before:**
- Taking on the `volunteer` mod_role (required acceptance).
- Resolving any flag.
- PR-ing changes to this rubric.

**Rubric is versioned.** Each `resolve_flag` call records `rubric_version` so later audits know which version a decision was made under. Changes don't retroactively re-review prior decisions.

---

## Core framing

- **Err toward leaving content up.** Taking down costs more than leaving alone — delete loses commons value, hurts creator trust, invites appeal drama. Hide is reversible; hard-delete is forever.
- **Rationale is the main deliverable.** Every resolution carries a ≥20-char reason visible to the artifact owner. Think of yourself writing a message the owner will actually read.
- **Don't mod own artifacts.** Recusal rule in code; check twice anyway.
- **2-mod concurrence** for hard-delete; soft-hide is 1-mod. Always upgrade-soft-hide when in doubt.
- **Escalate when uncertain.** "I don't know" is a valid resolution via `escalate_to_admin` — not a weakness, a signal.

---

## What to UPHOLD (hide or harder)

Flag upheld if the artifact meets ANY of the 5 criteria below. Use the narrowest applicable criterion when citing.

### U1. Illegal under US federal law

Platform jurisdiction at launch is US federal. Content clearly illegal under US law: CSAM, actual threats of violence against identifiable individuals, doxxing with verified PII, fraudulent financial instruments, content infringing copyright / trademark without fair-use justification.

**Action:** `upheld_hard_delete` if obvious; `upheld_hide` + `escalate_to_admin` if borderline (defer to host-admin for legal calls).

**Who issues:** anyone can flag; mod reviews; hard-delete requires 2-mod concurrence OR admin; escalate goes to admin-pool.

**Positive examples (uphold):**
- A node titled "DDoS toolkit tutorial" that includes actual exploit code targeting a specific organization → hard-delete.
- A node whose concept contains a verified home address of a non-consenting private individual ("here's where so-and-so lives") → hard-delete.
- A node marketing a fraudulent investment scheme with real solicitation language → hard-delete + escalate.

**Negative examples (dismiss):**
- A node titled "how SYN floods work conceptually" without exploit payload → dismiss; educational discussion is legal.
- A node critiquing a public figure's published work with strong language → dismiss; protected speech (see D4).

### U2. Credential leak / private-instance data in public concept

Credentials, API keys, passwords, session tokens, live financial account numbers, home addresses of identifiable private individuals. Any T2-taxonomy item from `docs/catalogs/privacy-principles-and-data-leak-taxonomy.md` that leaked into a public concept.

**Action:** `upheld_hide` (NOT hard-delete — owner needs a chance to redact). Set `status='hidden'`; the owner sees + can redact the private field + flip back to published. Only hard-delete if owner ignores multiple redaction requests for >7 days.

**Who issues:** anyone can flag; mod reviews + hides. Hard-delete after 7-day-ignored redaction requires 2-mod concurrence.

**Positive examples (uphold):**
- A node's concept includes `{"example_api_key": "sk-abc123..."}` → hide; message owner: "this looks like a real OpenAI key. Redact it (move to instance data) and I'll un-hide."
- A concept field contains a `postgresql://user:password@host/db` connection string → hide + redaction request.
- A node's example includes a verified live bank account number → hide + urgent-redaction request.

**Negative examples (dismiss):**
- A concept shows `{"example_api_key": "sk-YOUR_KEY_HERE"}` (obvious placeholder pattern) → dismiss; this is the correct way to document a key-shaped field.
- A tutorial node's concept quotes what a compromised key would look like without containing one → dismiss; pedagogy needs pattern examples.

### U3. Spam

Identical or near-identical text posted en masse across many artifacts. Off-topic commercial advertisement unrelated to the workflow. Linkjacking (masquerading as a node but containing only redirect-bait).

**Action:** `upheld_hide` for individual artifacts. Hard-delete reserved for accounts posting 10+ spam artifacts in a short window (clear bulk-spam pattern). Rate-limit + account-age gate from §14.7 / crypto spec §7.1 should have caught most; this is the human-caught residue.

**Who issues:** anyone can flag; mod reviews + hides individuals. Account-level bulk-spam ban escalates to admin-pool.

**Positive examples (uphold):**
- Five nodes all titled "Best crypto signals 2026" with affiliate links + no actual workflow content → all hide + escalate account to admin for bulk-spam ban.
- A node whose concept is just "visit my-site.com for more" with no workflow pattern → hide (linkjacking).
- A node duplicated verbatim across 8 domains with only the title changing → hide all except the original + note duplication on the surviving one.

**Negative examples (dismiss):**
- A user who intentionally creates similar nodes per-domain (e.g. "invoice OCR for retail" / "invoice OCR for healthcare") with genuine domain-specific variations → dismiss; legitimate cross-domain adaptation.
- A node that links to external documentation (arXiv paper, GitHub repo) relevant to the workflow → dismiss; outbound links aren't linkjacking when the content is substantively relevant.

### U4. Harassment or targeted abuse

Content directed at an identifiable individual with clear intent to harm, not debate. Includes: revenge-spite posts, defamatory claims presented as fact, coordinated brigading targeting one user's output.

**Action:** `upheld_hide` for single incidents. `upheld_hard_delete` if content contains PII (doxxing). Always include a rationale line referencing what specifically rose to harassment — e.g. "names the target + states intent to harm career" vs "criticizes the target's public argument."

**Who issues:** anyone can flag; mod reviews + hides. Doxxing-PII hard-delete requires 2-mod concurrence + admin notification.

**Positive examples (uphold):**
- A node that lists a real person's employer, home city, and dog's name in a "fun facts about them" concept → hide + escalate for doxxing-PII review → hard-delete by admin-pool if confirmed.
- A node whose concept describes a coordinated-reporting scheme targeting a specific user's artifacts → hide + flag organizing account.
- A node with defamatory claim-of-fact ("X committed Y crime") without substantiation → hide + route to admin-pool.

**Negative examples (dismiss):**
- A node titled "Why [public-figure]'s work is trash" that's substantive critique of their published arguments → dismiss; protected speech about a public figure.
- A node disagreeing with another user's workflow design in the remix rationale → dismiss; that's what remix rationales are for.

### U5. License violation

Artifact claims a license incompatible with the repo's CC0-1.0. Or: artifact imports clearly-copyrighted third-party work without fair-use justification (e.g. reproduces a full article text verbatim from a paywalled source).

**Action:** `upheld_hide`. The artifact's owner gets a chance to either (a) change license compatibility, (b) rewrite the content as fair-use summary/citation, or (c) remove the problematic portion. Hard-delete is reserved for owners who ignore the notice.

**Who issues:** anyone can flag (especially the rights-holder); mod reviews + hides. Hard-delete-after-ignored-notice requires 2-mod concurrence.

**Positive examples (uphold):**
- A node's concept includes a 500-word verbatim quote from a paywalled New York Times article without fair-use justification → hide; owner can rewrite as paraphrase + citation.
- A node's example-library contains full song lyrics of a copyrighted song → hide + redaction request.
- A node's YAML frontmatter declares `license: MIT` while the repo's standard is CC0 → hide + owner can change license or the content.

**Negative examples (dismiss):**
- A node's concept cites a short quotation (<50 words) with attribution + analytical framing → dismiss; textbook fair use.
- A node implements a technique described in a public-domain paper with proper citation → dismiss; concepts aren't copyrightable; citation satisfies attribution.

---

## What to DISMISS

Flag dismissed if the artifact meets ANY of the 4 criteria below. Dismissal is as valid as any uphold action — saying "this flag is wrong" is good moderation.

### D1. Disagreement about quality, style, or usefulness

The flagger doesn't like the approach, thinks the node is bad, prefers a different style. Not a mod concern. The community corrects via forks, remixes, upvotes, and discovery ranking — not mod action.

**Action:** `dismissed`. Rationale: "quality disagreement; use fork or remix to propose a better approach."

**Who issues:** anyone can flag; any mod dismisses. Flagger's flag-accuracy-score is not penalized the first time someone does this; a pattern (5+ quality-disagreement flags in a month) surfaces to admin.

**Positive examples (dismiss):**
- Flagger: "this is poorly written" — dismiss; critique belongs in remix rationale not in the flag system.
- Flagger: "the author used Python but should have used Go" — dismiss; fork + do-it-in-Go.
- Flagger: "this recipe is not to my taste" — dismiss; subjective preference.

**When NOT to dismiss under D1:**
- If the "quality" complaint describes an actual U5 license violation or U2 credential leak — those are the real reason, treat under that category.

### D2. Flag on stale state — artifact was revised since the flag landed

The flagger raised a concern that the current version has already addressed. Revisions are the wiki-open model's primary healing mechanism.

**Action:** `dismissed`. Rationale: "current revision resolves the concern; re-flag if it reappears." Do NOT penalize the flagger's accuracy score for this category — they flagged in good faith at the time.

**Who issues:** anyone can flag; any mod dismisses. Flag-accuracy exempt per above.

**Positive examples (dismiss):**
- Flag filed at v3 said "contains a credential"; at v5 the owner had redacted → dismiss; the flagger was right at the time.
- Flag about an out-of-date link pointed at a paper that was since moved to the current canonical URL → dismiss; corrected.

**When to escalate instead of dismiss under D2:**
- If the revision *reintroduced* the flagged pattern later and the flagger just re-flagged → escalate to admin (the owner may be gaming the revision cycle).

### D3. Dispute-motivated flag

Flagger has an unrelated dispute with the artifact owner and is using the flag system as a proxy. Look at flag-accuracy score + recent pattern (did they flag 5 of this user's artifacts in 24h?).

**Action:** `dismissed`. If pattern is egregious, `escalate_to_admin` so admin-pool can review the flagger's account for false-flag-brigading demote.

**Who issues:** anyone can flag; mod dismisses. Egregious-pattern escalation routes to admin-pool; demote of flagger's mod_role happens at admin level.

**Positive examples (dismiss + note pattern):**
- Flagger has filed 5 flags against one owner's artifacts in 24 hours while ignoring similar content from other owners → dismiss the individual flag + escalate for brigading review.
- Flagger's account was created yesterday + filed 10 flags against artifacts related to a topic the flagger publicly criticized elsewhere → dismiss + escalate.

**Negative examples (don't jump to dispute-motivated):**
- A single user legitimately flagging a pattern across multiple artifacts they genuinely care about (e.g. someone who fights credential-leak exposure aggressively across many nodes) → not dispute-motivated; evaluate each flag on merits.

### D4. Legally protected speech, even if unpleasant

Criticism, satire, dissenting opinion, political disagreement, unpopular aesthetic choices. If it's legal in the US AND doesn't meet U1-U5, it stays up. This is where community moderation differs from opinionated platform moderation — we're the former.

**Action:** `dismissed`. Rationale: "protected speech; platform policy is community-flagged moderation, not ideological takedown."

**Who issues:** anyone can flag; any mod dismisses. Consistent pattern of dismissed-under-D4 flags from the same flagger contributes to their flag-accuracy score dropping.

**Positive examples (dismiss):**
- Political satire of a public figure's published positions → dismiss; protected.
- Harsh but substantive critique of a specific methodology → dismiss; the remedy is counter-speech (fork + remix), not takedown.
- Content the flagger finds ideologically objectionable but which isn't U1/U2/U3/U4/U5 → dismiss; the commons holds content the community as a whole may not love.

**When to escalate instead of dismiss under D4:**
- If the "protected speech" content actually crosses into U4 harassment (named target, clear harm intent) → treat under U4 not D4.
- If the flagger argues a specific US-federal illegality → escalate to admin to evaluate under U1; D4 applies only AFTER U1-U5 are ruled out.

---

## Hard-delete threshold

Hard-delete requires **2 concurring mods** per `docs/specs/2026-04-18-moderation-mvp.md` §3. The first mod's `upheld_hard_delete` marks the artifact `hidden`; it stays `hidden` until a second mod concurs. The second mod's concurrence executes the DELETE; audit row in `node_activity` preserves what happened.

Hard-delete only for:

- **H1. Illegal content** (CSAM, credible threats, doxxing with verified PII, content infringing copyrighted material that clearly has no fair-use defense).
- **H2. Persistent bulk spam** — account has been hidden 3+ times for spam and keeps posting.
- **H3. Credential leaks where the owner has been told + ignored** for >7 days.

**Default everything else to hide, not hard-delete.** Hide is reversible. Hard-delete is the only moderation action with no undo path (the audit row stays but the concept content is gone).

---

## Appeal handling (for admin-pool members only)

Artifact owners can appeal any decision via `appeal_decision`. Appeals route to admin-pool (not back to the deciding mod).

**Admin-pool member reviewing an appeal:**

- Read the owner's message + the original rationale + the flagger's report text.
- Apply the same rubric + the same "err toward leaving content up" framing.
- If you'd have dismissed the original flag → overturn the decision. `nodes.status` flips back to `published`. Tell the owner + the original mod.
- If you'd have made the same call → uphold the decision. Tell the owner why with full rationale (they earned the appeal; they deserve a thoughtful answer).
- If you're uncertain → DON'T RESOLVE ALONE. Ask another admin-pool member for a second opinion. Convergence on appeal = durable precedent for the rubric.

Recusal rules (per spec #36 §4.5):

- Admin cannot resolve appeal on own artifact.
- Admin cannot resolve appeal on decision where they were the original mod.

---

## Rubric changes

Changes via PR to this file. **2 admin-pool members must approve** per `SUCCESSION.md` §1.7 bus-factor rule.

Version bump on:
- New uphold / dismiss category.
- Default-action flip on an existing category (e.g. hide → hard-delete as default).
- Fundamental re-framing of the "err toward leaving content up" posture.

No version bump for:
- Wording polish that doesn't change meaning.
- Example addition / replacement.
- Typo fix.

---

## On being a moderator

Four things that matter more than the rubric letter:

1. **Rationale ≥20 chars.** The owner reads this. Make it a message, not a verdict.
2. **Precedent > consistency.** If your call conflicts with a prior decision on similar content, surface it — consistency across mods is the commons' trust signal. File an escalation if you think prior precedent was wrong; don't just quietly deviate.
3. **Your flag-accuracy score is public-visible to other mods.** Don't dismiss everything reflexively (low accuracy demotes you). Don't uphold everything reflexively (same demote). Follow the rubric; the score follows.
4. **Time matters.** Flags get stale. Artifacts get revised. Try to resolve within 48h; escalate if you can't.

Mod work is quiet, unglamorous, and the commons depends on it. Thank you for doing it.

---

## References

- **Spec:** `docs/specs/2026-04-18-moderation-mvp.md` — the full platform moderation surface.
- **Spec:** `docs/specs/2026-04-18-full-platform-schema-sketch.md` §2 RLS — where this rubric's decisions land at the row level.
- **Catalog:** `docs/catalogs/privacy-principles-and-data-leak-taxonomy.md` — referenced by U2 for credential-leak detection.
- **Runbook:** `SUCCESSION.md` — admin-pool bus-factor rule that this rubric's 2-mod concurrence matches.
- **Memory:** `project_q10_q11_q12_resolutions.md` — Q10 community-flagged framing source.
- **Memory:** `project_host_independent_succession.md` — why admin pool is ≥2.
