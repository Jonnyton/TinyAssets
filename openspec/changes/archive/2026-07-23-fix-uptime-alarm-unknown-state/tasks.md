## 1. Regression Coverage

- [x] 1.1 Add focused workflow tests that execute the extracted alarm script with mocked GitHub/core APIs and prove empty or unknown results make zero REST calls and do not fail.
- [x] 1.2 Add coverage that literal green never creates a label and only recovers an already discovered incident, while literal red retains label creation, threshold lookup, and paging outputs.

## 2. Alarm-Sink Implementation

- [x] 2.1 Initialize no-page outputs and classify current output before REST calls; return successfully with warning and summary for unknown input.
- [x] 2.2 Restrict label creation and red incident lifecycle to literal red; restrict incident lookup, recovery comment, and closure to literal green.

## 3. Verification

- [x] 3.1 Run the focused workflow tests, actionlint when available, and strict OpenSpec validation; inspect the owned-file diff.
