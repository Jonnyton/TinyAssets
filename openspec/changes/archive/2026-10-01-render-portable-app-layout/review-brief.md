# Focused Fable shape review: real portable layout consumer

Read proposal.md, design.md, specs/portable-app-layout/spec.md and tasks.md in
this directory. The parent owns the release; review only this shape now.

Check current code: tinyassets/custom_agents.py normalization/create/update,
tinyassets/api/custom_agents.py ACL; universe_server.py agent graph routes;
onboarding/app.html conversation/request/model/status nodes and MCP.callTool;
onboarding/serving.py platform binding selection. OpenRouter draft3853 model_setup
considers any existing binding recovery; this proposal avoids empty-universe
layout installation. Read original September13 architecture review dispositions
if available in primary0a7f docs/audits/2026-09-13-harness-experience-review-handoff.md.

Questions: Is the exact declarative schema safe without executable content? Can
a dedicated non-serving binding preserve serving/data and existing authority?
Are recovery, ambiguous installation, home-change and uncertain-write rules
sufficient for this usable MVP? Name concrete blockers only; record later
hardening separately. A consumed layout is the goal, not just metadata tests.
This does not claim arbitrary UI/harness or whole-setup replacement.

HARD CONSTRAINTS: no subagents, peer calls, new worktrees, implementation, live
account actions or full suite. Read-only shape review, at most one targeted
test file if needed. Return AGREE / DISAGREE_EVIDENCE with citation /
DISAGREE_CONCERN, concrete required corrections, and end with exactly
VERDICT: APPROVE|ADAPT|REJECT. Budget5minutes.
