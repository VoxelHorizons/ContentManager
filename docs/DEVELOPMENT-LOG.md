# Development ledger — authoritative handoff record

This file is the durable handoff between coding sessions. **Every commit that
changes application code, tests, build configuration or CI must update this
file in the same commit.** The pull-request progress guard checks each commit
individually. A direct push to an unprotected branch can bypass this guard;
require the CI check through GitHub branch protection when available.

For the current state, read this ledger, then
[implementation status](IMPLEMENTATION-STATUS.md),
[roadmap](ROADMAP.md), [source contracts](SOURCE-CONTRACTS.md),
open [issues](https://github.com/VoxelHorizons/ContentManager/issues) and
[PRs](https://github.com/VoxelHorizons/ContentManager/pulls) **before editing**.
The roadmap is aspirational; only test-backed items in the status document may
be marked implemented.

## Completed history recovered from Git

### 2026-10-18 — initial product foundation (merged as PR #10 on 2026-10-21)

- `9240759`: original architecture, generator contracts, gated roadmap.
- `c20130c`: first offline Python/Tkinter studio, scanner and variant planner.
- `aa81d34`: Python/Tkinter decision and cross-platform CI.
- `6f31c13`: Windows launcher and offline setup guidance.
- `cea4ef0`: recoverable write journals, lock and stale-input checks.
- `4f76819`: asset parent/texture resolution, graph and related variants.
- `8fa5073`: round-trip existing-item editor and Windows package workflow.
- `3807503`: bounded multi-axis recipes and additional fault tests.
- Merge: `e75afc2`, [PR #10](https://github.com/VoxelHorizons/ContentManager/pull/10), 21 October.

Previous authors reported 76 tests passing and one display-dependent skip on
Python 3.12/Linux for `3807503`. This is **historical**, not an independently
reproduced current CI result. The existing README's early-MVP limitations are
in places older than subsequent commits; favor source/tests and this ledger.

### 2026-10-21 — chore: establish per-commit progress checkpoints

**Change:** Added this handoff ledger, `scripts/check_progress.py`, regression
tests and a PR Actions guard requiring the ledger in every code-changing commit.
Updated documentation to explain the continuation procedure.

**Verification:** The new guard logic has unit tests and runs in GitHub Actions
for pull requests; verification of this branch's full CI is pending.

**Limitations:** A CI job alone cannot protect direct main pushes. Repo branch
protection/rulesets must make the guard required. Reconstructed old commits do
not have individual ledger entries; their history above was recovered from Git.

**Next:** Implement an offline read-only diagnostic command and a curated
Minecraft 26.3 palette target, with CLI tests. Do not claim VoxelCore Java
compiler verification or Paper runtime certification.

## Current project decisions and next work

1. **P0 (#1):** Source pins exist in SOURCE-CONTRACTS, but authoritative Java
   parser/pack-compiler fixtures and 26.3 profile verification are outstanding.
2. **P1 (#2):** Lock, journal, undo/redo and Windows path checks are implemented
   but need real power-loss and Windows file-system certification.
3. **P2/P3 (#3/#4):** Partial item/reference/model and Tkinter editor/preview;
   missing plugin-wide references, texture/UV studio and renderer parity.
4. **P4 (#5):** Wood/wool/dependency fanout and multi-axis recipes work offline;
   three-way merges and full plugin compile checks are not complete.
5. **P5–P8 (#6–#9):** Schema forms, resource-pack Java builder, staged deploy,
   Paper integration and production packaging remain unverified/incomplete.

**Working baseline:** `main` merge commit `e75afc2` before this development
branch. Development branch: `feat/lint-26-3-progress-ledger-20261021`.
Never publish to the live Minecraft server as part of a Content Manager test.
