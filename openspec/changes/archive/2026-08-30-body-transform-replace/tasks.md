## 1. Change

- [x] 1.1 `$ta.replace` in the transform vocabulary, applied before the wire;
      refusals for empty/absent/ambiguous `old`, bad `count`, wrong shape.
- [x] 1.2 write_graph docs show the change-a-line shape; `body_hint` names it.
- [x] 1.3 Test: the live README line replaced with exact bytes around it.
- [x] 1.4 Codex round 1 (ADAPT) folded: closed key set (P1), UTF-8 byte
      charging (P1), served example shows a literal `\\n` (P1), design.md for
      the public vocabulary (P1), `count` resolved as an operand (P2).

## 2. Proof and close

- [x] 2.1 Live 2026-08-30 09:30:56Z (prod `81b1fe19`): run `ecabc10d41294d7f`
      (branch `f95b244ad8db`) fetched, replaced the exact two-line suffix,
      opened #2720 non-draft and merged it - `-2/+1`, exactly the fix - in
      one write run, uncoached; the universe reached it by retrying itself
      twice inside one turn after the nearest-match refusal (#2717) showed the
      leading space it had guessed wrong.
- [x] 2.2 Synced into `openspec/specs/external-effect-adapters/spec.md`
      (replace clause, closed key set, byte charging, nearest-match refusal,
      the vocabulary freeze from `sandboxed-code-node`); archived.
