## 1. Workflow Truth

- [x] 1.1 Persist exactly one validated runtime-image assignment in the fresh drill template before Compose startup.
- [x] 1.2 Make a red MCP probe produce a red terminal workflow conclusion after failure evidence is recorded.
- [x] 1.3 Add a validated cleanup-only dispatch job that deletes one retained Droplet without provisioning.

## 2. Operator Contract

- [x] 2.1 Update the DR runbook for digest persistence, red-run truth, and cleanup-only dispatch.

## 3. Verification And Landing

- [x] 3.1 Run the existing focused DR workflow tests, actionlint, strict OpenSpec validation, and diff hygiene.
- [ ] 3.2 Obtain independent exact-SHA review and land through CI.
- [ ] 3.3 Delete retained Droplet `587161699`, rerun the exact landed SHA, and record green MCP plus deletion evidence.
