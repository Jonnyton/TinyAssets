# Cowork session-start bootstrap

When a Cowork session opens this Workflow project, before any other tool
call, run:

    bash "$(pwd)/scripts/cowork-bootstrap.sh"
    source "$HOME/.cowork-env"

This wires GitHub PAT credentials from `.cowork-bootstrap/github.token`
(gitignored, host-managed) into `~/.git-credentials` so `git push` and
`gh` work from the Cowork sandbox. After sourcing, `$GH_TOKEN` is set.

Cowork should write a memory entry pointing at this file the first time
it sees it, so future sessions auto-execute the bootstrap.
