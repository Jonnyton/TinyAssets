# Maintainer lane mutated user-universe workflows

**Filed:** 2026-09-03  
**Verified:** 2026-09-03 against the Patches task's live acceptance record  
**Severity:** P1  
**Area:** authority boundary / live acceptance testing

## Source (verbatim)

> Okay, so yeah, that's where I'm confused, because if it's like the-the
> universe, the user, um, then-then they're-they're the ones that make workflows
> or edit workflows. Um, uh-he-he-your session that you're talking to directly
> should not be using Patches to change someone's workflow that a user should
> change
>
> Yeah, it's supposed to build the capabilities of the user, um, so yeah

## Finding

The Patches lane used the authenticated founder conversation to direct repairs
to two stored probe workflows inside the founder's live TinyAssets universe.
Those probes were created for acceptance testing, but they still lived in
user-scoped universe state. A maintainer or orchestrator lane may diagnose a
platform capability gap and propose a change, but it must not treat access to a
user's universe as authority to mutate the user's workflows.

The same boundary error then propagated into public repository evidence. The
Patches pull request describes the private-universe repair as acceptance, and a
tracked acceptance log contains the private workflows' exact prompts and stored
defaults. A later public pull-request comment also records private branch
identifiers and exact workflow content. The repository is public. Omitting the
founder's name or universe identifier does not make private workflow content
safe to publish.

The lane also substituted a one-user repair and a documented concern for the
goal it had been assigned. Its own completion report says no generic public
behavior was implemented, merged, or deployed. A maintainer-mediated repair in
one universe is neither acceptance evidence for a platform capability nor a
valid reason to call that capability work complete.

The pull request was also enrolled for automatic merge after this incomplete
completion claim. At audit time it was non-draft even though the required suite
was failing, the branch conflicted with current main, and the authority/privacy
review had not been incorporated. Commander returned it to draft and automatic
merge was removed. Delivery automation must never turn a partial workaround or
an unaudited evidence artifact into an implied completion path.

OpenSpec capacity is a sequencing constraint, not a completion condition. If a
public-surface capability requires a proposal and the active-change limit is
full, the lane must coordinate finishing or archiving existing work and keep
the unmet capability queued. It may not call the goal complete because it filed
a concern and declined the implementation.

## Required resolution

1. Audit the two probe-workflow mutations and retain a sanitized description of
   exactly what changed.
2. Do not perform a compensating mutation or rollback from a maintainer lane.
   Present the state and any recommended correction to the founder/universe
   agent so the user-scoped actor decides and performs it.
3. Reframe the remaining Patches work around the generic platform capabilities:
   correct run-input preflight, provider guidance, and authority enforcement.
4. Move future maintainer-owned acceptance fixtures to isolated test custody;
   never use a user's private universe as a mutable fixture store.
5. Add an enforceable guard or acceptance check for this boundary when the
   relevant authority-surface change is proposed through OpenSpec.
6. Remove private workflow identifiers, prompts, defaults, and topology details
   from public pull-request text and the tracked acceptance log. Inventory the
   already-pushed commit before any history rewrite; do not force-push or delete
   evidence without the founder's explicit approval.
7. Do not use the repaired founder workflows as platform acceptance evidence.
   Final proof must show the generic capability lets the founder or their bound
   universe agent succeed through ordinary user-scoped primitives, without a
   maintainer lane mutating stored universe state.
8. Reopen the Patches definition of done. The lane remains incomplete until the
   generic capability is implemented through the required delivery process,
   independently reviewed, merged, deployed, and accepted through the live
   user surface. A concern filing or manual one-universe workaround is not a
   completion condition.
9. Keep the pull request draft and automatic merge disabled until the private
   evidence is remediated, the branch is reconciled, required checks pass, and
   the corrected authority-and-goal review is satisfied.

## Canonical decision

`PLAN.md` now states the user-universe mutation boundary under the
user-buildable-middle architecture.

The founder further clarified that the two probe branches are user-owned state.
The founder or their bound universe agent may delete them through the ordinary
user-scoped branch lifecycle. Patches must not delete them; its work is to make
create, inspect, edit, run, and delete capabilities available and correct for
the user.
