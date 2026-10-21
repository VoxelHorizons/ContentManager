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

### 2026-10-21 — feat: offline structural lint and 26.3 authoring profile

**Change:** Added `content_manager/lint.py`, a read-only diagnostics service
shared by Tkinter's Diagnostics tab and the new `lint` CLI command. Reports
missing models/textures/item references, dependency-not-loaded warnings,
unverified vanilla parents and potential duplicate model bytes. Text and JSON
output are deterministic, with exit code 1 on structural errors (and optional
warnings under `--strict`). Added a `mc-26.3` curated wood/wool authoring
profile and made it the GUI, CLI and recipe default; retained 26.2.

**Verification:** Unit tests added for clean read-only scans, missing texture
JSON/nonzero exit, vanilla-parent information, strict dependencies, both addon
sections, parse failures and the 26.3 palette. Cross-platform CI results must
be checked on the new PR before merging.

**Limitations:** This is static, incomplete graph linting; it is **not**
authoritative VoxelCore Java compilation or proof of Paper 26.3 addon support.
Missing workspace dependencies are only warnings because a pack may have been
opened in isolation. True version compatibility and P0 compiler fixtures remain
open.

**Next:** Establish pinned Java validation fixtures and add detailed source
locations to diagnostics, then expand safe plugin-aware reference coverage.
Do not advance P0/P6 acceptance gates on Python-only results.

### 2026-10-21 — fix: import JSON serializer for lint CLI

**Change:** CI identified a missing `json` import in `content_manager/cli.py`.
Added the import so `lint --json` and malformed-workspace JSON error
handling execute as designed. No behavior change to authored files.

**Verification:** Initial Linux/Python 3.10 CI on `2bafc58`:
81 passed, one skipped, four lint CLI tests failed with the same
`NameError: name 'json' is not defined`. Retest on this fix required;
do not mark the PR green until all jobs finish.

**Next:** Confirm Python 3.10/3.13 on Linux and Windows and Windows
packaging workflow; then review the linter's limitations before merging.

### 2026-10-21 — docs: reconcile active roadmap and decision status

**Change:** Removed out-of-date claims that cross-process locks, journals,
round-trip editing, and multi-axis recipes are still absent. Reconciled
the P0–P8 remaining acceptance gates with the code already merged in PR #10,
and distinguished implemented Python features from unverified runtime behavior.

**Verification:** Documentation-only commit; no application behavior changed.
Review the current PR's full CI results and do not imply Java/Paper tests
passed when they have not been executed.

**Next:** Build version-pinned Java compiler golden fixtures and improve
plugin-specific graph/schema references. Keep each new coding commit logged.

### 2026-10-21 — feat: staged authoritative Java pack-validation bridge

**Change:** Added the opt-in \`validate-java\` command and isolated Python-to-Java
source launcher for the source-reviewed \`JavaPackCompiler.validate\` interface.
The Java compiler only sees temporary copied packs/allocations. Added bounded,
source-drift/symlink-aware input staging, explicit classpath validation, timeout,
stable JSON output, failure marker checks, tiny synthetic valid/invalid fixtures
and tests. \`docs/JAVA-VALIDATION.md\` describes the pinned source interface and
building the operator-supplied dependency classpath.

**Source proof:** VoxelCore \`1b6489c5d396c119f9f6e0326eabb1b2aeaf5b39\`
declares exact 26.3 format 97.1 and 26.2 format 88.0 targets, and a
non-publishing \`JavaPackCompiler.validate\` method.

**Verification:** Python tests for staging/CLI are submitted in this commit.
The external Java classpath, actual Maven build and addon runtime tests are
NOT yet verified; PR CI must be inspected. No production content mutated.

**Limitations:** Compiler classpath provenance is user-managed, not attested.
Success proves only staged VoxelCore pack validation, not Paper/Furniture/
Vehicles compatibility. This is opt-in (not automatically required for Apply).

**Next:** Automate a pinned Java 25 build/test of these fixtures and add
source-location diagnostics and supported Furniture/Vehicle parser fixtures.
Do not claim the P0 or P6 acceptance gate complete on Python unit tests.

### 2026-10-21 — test: fix symlink regression and add real Java contract workflow

**Change:** Fixed the symlink regression test's expected error text:
the existing Workspace scanner correctly rejects an external symlink before
the new bridge can stage it. Added a source-pinned Maven/JDK 25 GitHub Actions
workflow compiling VoxelCore at `1b6489c` and checking valid/invalid
golden fixtures using the actual Java process and format-97.1 target.

**Verification:** Initial Python 3.10/Linux test run: 91 passed, 1 skipped,
1 failed solely because the existing scanner reports `Path escapes content
pack root` instead of the test's `Linked/special` text. Re-run all Python
and Java CI before declaring this slice ready.

**Risks:** External Maven repository availability, JDK25 dependency classes,
fixture compatibility and classpath provenance. The workflow uses a pinned
source checkout but does not yet produce attested distributable JAR checksums.

**Next:** Inspect pinned Java CI and address genuine source/API/fixture errors.
Keep the parser/compiler acceptance gates open until actual runs pass.

### 2026-10-21 — fix: Windows CRLF and real Java negative fixture

**Change:** Made Java success-marker parsing accept CRLF on Windows, added a
regression test, and changed the pinned Java negative fixture to an unknown
`render` field. Unlike the duplicate-YAML fixture, this field passes
Content Manager scanning and is rejected by VoxelCore's Java parser. CLI
`validate-java --json` errors now remain structured even on setup failure.

**Verification:** Actual pinned JDK25/Maven CI successfully compiled VoxelCore
and passed a real Java 26.3 **positive fixture**, returning one rendered
item. The previous negative job failed because duplicate YAML was caught
by Python first and no JSON was emitted. Windows/Python 3.13 found a CRLF
success marker mismatch. New tests and Java CI must pass before merging.

**Next:** Verify positive/negative Java and Windows CI on this commit, then
add more representative abstract/state/multi-pack fixtures.

### 2026-10-21 — verified P0 integration checkpoint

**Change:** Documentation-only verification record after the Java contract
workflow completed. The pinned JDK 25 source build at VoxelCore commit
`1b6489c` compiled successfully and invoked `JavaPackCompiler.validate`
on a staged `mc-26.3` fixture. A real valid fixture passed (1 rendered
item, 0 blocks, 1 asset); a Python-scannable invalid render field was
rejected by the **Java** parser with `Unsupported key
'unsupported_java_parser_key'`. No source files or live server allocations
were changed.

**CI evidence at `f3d2cf0`:** Python 3.10/3.13 on Windows/Linux: all four
jobs passed (representative Linux result: **95 passed, 1 skipped**).
Pinned JDK25/Maven Java contract workflow: **passed**. Windows PyInstaller
desktop/package smoke: **passed**. Per-commit development ledger guard:
**passed**. These are verifiable in GitHub Actions for PR #12.

**Remaining P0:** compiler classpath integrity attestation, target 26.2
regression on the new bridge, parser fixtures for Furniture/Vehicles,
representative asset/atlas/shader diagnostics and actual Paper runtime tests.
This is not a P0/P6 completion claim.

**Next:** Expand Java fixtures across more targets and real plugin contracts,
then expose optional Java validation in the native Tkinter workflow. Keep
all validation opt-in and staged until full safety acceptance.

### 2026-10-21 — feat: native Tkinter Java validation action and 26.2 smoke

**Change:** Added a native **Diagnostics → Validate saved content with VoxelCore
Java** action, classpath picker, optional allocation manifest picker/clear,
background execution and explicit saved-file/unsaved-editor warning. The GUI
reuses `validation.validate_java`, displays success/failure counts and
diagnostics, and cannot publish the pack. Added a display-dependent GUI smoke
for worker dispatch plus a real `mc-26.2` golden fixture to the pinned
JDK 25 CI alongside `mc-26.3`.

**Verification:** Code, GUI smoke and new target fixture submitted to CI.
The earlier PR #12 pinned Java pack fixture tests passed on 26.3; this
new GUI and 26.2 integration must be confirmed on PR #13 before merging.

**Limitations:** The user still provides Java classpath and optional
allocation file. No automatic plugin version discovery, classpath integrity
attestation, GUI pack ZIP building or Paper/Furniture/Vehicle certification.

**Next:** Add real furniture/vehicle source-parser fixtures and structured
pack diagnostic paths, then consider optional pre-apply Java validation gate.

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

**Current development baseline:** `main` merge commit `07a8795` (PR #11).
Current branch: `feat/gui-java-validation-20261021` (PR #13). Updated per-commit
hints in this document supersede older historical handoff branch references.
Never publish to the live Minecraft server as part of a Content Manager test.
