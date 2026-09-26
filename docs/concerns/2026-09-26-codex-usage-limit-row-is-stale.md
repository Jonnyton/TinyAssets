# Two durable claims about Codex are stale, and both suppress cross-family review

**Filed:** 2026-09-26
**Verified:** 2026-09-26, Windows dev box, repo venv Python 3.14.3
**Severity:** P2

## Source (verbatim)

`docs/host-actions.md`:

> ## Codex is usage-limited, so a cross-family pass is OWED on what lands meanwhile (2026-09-25)
>
> `codex exec` answers only:
>
> > ERROR: You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage
> > to purchase more credits or try again at Sep 27th, 2026 5:15 PM.
>
> `codex login status` still reports "Logged in using ChatGPT", so this is a
> credit balance, not an auth failure, and no agent can fix it.
>
> **The standing arrangement while it lasts** (founder directive): the
> cross-family pass is POSTPONED, not skipped.

`.agents/skills/peer-agents/SKILL.md` (mirrored to `.claude/skills/`):

> codex runs with no `-m`, so it uses the model from the host's
> `~/.codex/config.toml` (currently `gpt-5.6-sol`)

> Useful flags: `--timeout SEC` (default 1800), `--effort minimal|low|medium|high|xhigh`

## Re-verification (2026-09-26)

Both claims are contradicted by live runs today, during the PR #4011 lane:

1. **Codex is not usage-limited.** A full cross-family review dispatched with
   `python scripts/peer_agent.py codex --effort high` returned a complete
   structured verdict (four reproduced P0s). A second cheap probe minutes later:

   ```
   echo "Reply with exactly: CODEX_ALIVE" | python scripts/peer_agent.py codex --effort low
   [peer_agent] codex done in 9s -> stdout
   CODEX_ALIVE
   ```

2. **The model is `gpt-6-astra`, not `gpt-5.6-sol`**, and that model **rejects
   `--effort minimal`**, which the skill still lists as a valid value:

   ```
   "message": "Unsupported value: 'minimal' is not supported with the 'gpt-6-astra'
    model. Supported values are: 'low', 'medium', 'high', 'xhigh', and 'max'.",
   "status": 400
   ```

## Why this matters

The host-actions row authorizes landing an authority-path PR on a same-family
review "in place" of the cross-family pass. That is a real weakening of the
AGENTS.md verification rule, and it is now weakening it for no reason — the peer
it routes around is answering in nine seconds. A stale suppression is worse than
no row, because it reads as a founder directive.

The skill's `--effort minimal` is a 400 on the first call, which a session is
likely to read as "Codex is broken" and fall back to same-family review — the same
failure with a different cause.

## Suggested resolution

- Delete the `docs/host-actions.md` usage-limit row (git holds it), or replace it
  with the date the credits came back and a note that the OWED passes are owed.
- Update `.agents/skills/peer-agents/SKILL.md` to `gpt-6-astra` and
  `--effort low|medium|high|xhigh|max`, then re-run
  `powershell -ExecutionPolicy Bypass -File scripts/sync-skills.ps1`.

Filed rather than fixed because both files are outside this lane's write set
(`docs/host-actions.md` is founder-owned and the skill is mirrored), and an
unrelated lane may be holding them. Whoever picks this up: re-run the two probes
above first — a credit balance can lapse again.
