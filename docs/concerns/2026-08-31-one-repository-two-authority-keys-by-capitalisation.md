# A workspace consent is refused when the repository is capitalised differently

**Found** 2026-08-31 against **production**, on the founder's universe whose
owner had granted both workspace consents through the request rail:

```
jonnyton/tinyassets -> checkout:http_79315...:github.com/jonnyton/tinyassets   active: True
Jonnyton/TinyAssets -> checkout:http_79315...:github.com/Jonnyton/TinyAssets   active: False
```

Same repository, same connection, same grant. `git_read` / `git_write` scopes
split the same way (`format_git_scope`).

The refused spelling is **the one GitHub displays**, so an agent that reads the
repository page and asks for `Jonnyton/TinyAssets` is told it has no consent
while the owner's grant sits in the store. It fails **closed**, so this denies
access rather than widening it — but a permission that depends on
capitalisation is not a permission.

This is the third time this key family has had two spellings: the host used to
default to `github.com` while the sink passed the connection's own host, and
`sink` / `channel_type` had to be closed in #2742.

## The obvious fix is wrong — do not casefold `normalize_repo`

Attempted, reviewed by Codex, **REJECTED on three independent grounds**, all of
which check out against the tree. The attempt is preserved on branch
`claude/repo-key-case` at `746a3a76` so nobody has to redo it to see why.

**1. `normalize_repo` reaches the FILESYSTEM, not just keys.** Traced and
confirmed:

```
effectors/workspace.py:174  _split_repo -> normalize_repo
effectors/workspace.py:755  repo_key = repo_key_for(host, owner, name)
workspace_pool.py:336       universe_paths(...) -> workspaces/<repo_key>/<generation>
```

Folding changes the on-disk directory name of a **permanent** workspace, so
every existing generation stored under a mixed-case key is silently stranded.
The claim that it fed "only authority keys and comparisons" was wrong.

**2. It WIDENS authority on case-sensitive forges.** This module deliberately
supports any forge a connection declares — GitHub, GitLab, Gitea, self-hosted
(`git_host_for_endpoints`). On a case-sensitive host, `Owner/Name` and
`owner/name` can be two different repositories, and folding makes a grant for
one authorize work on the other. The "GitHub and GitLab don't allow it"
argument is true and irrelevant, because the platform never names one forge.

**3. It orphans stored keys beyond the ones that were checked.** A production
scan covering **consent rows** and **git scopes** found none mixed-case (16
consent rows, of which the only two mixed are `twitter_post` / `@TinyAssets`,
which do not go through `normalize_repo`; 12 git-scope mentions, all lower).
But that scan did not cover the other stores keyed the same way:

* lease / generation keys — `workspace_pool.py:450-460`, `:919-935`
* request-rail decision dedupe and suppression —
  `api/pending_requests.py:265`, `:421-426` vs
  `storage/pending_requests.py:157-160`

Mixed-case git scopes survive a fold because reads re-normalize them; the
lease and rail keys are matched EXACTLY, so they would not.

## The shape a real fix probably has

Not decided — this needs the design thought the rejected attempt skipped.

* **Resolve at the input boundary, once.** When a packet names a repository,
  canonicalise it to the spelling the *connection's* scope declares, and carry
  that one spelling everywhere. One repository then has one identity because it
  was resolved, not because every consumer folded independently — and a
  case-sensitive forge keeps its distinctness.
* Or **fold only in the consent/scope comparison, and only when the forge is
  known case-insensitive** (`github.com`, `gitlab.com`), leaving `repo_key` and
  every filesystem path exactly as they are. Narrower, uglier, and it does not
  touch stored identity.

Either way: enumerate **every** store keyed on a repository first. The rejected
attempt failed because it changed one function and reasoned about two of its
consumers.

## Impact today

**P2.** It denies authorized access rather than granting unauthorized access,
and the universe the live proof runs on already holds lowercase consents and
lowercase scopes — its own scope list is where an agent reads the spelling, so
the likely path avoids the bug. Raise the priority the first time a run is
refused for this reason, which is also the evidence that would justify the
larger change.
