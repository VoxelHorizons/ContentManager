# Staged Java validation integration — 21 October 2026

- Added opt-in `validate-java` command staging authored pack trees and optional allocation manifest in a disposable temporary root. Calls VoxelCore's real Java `JavaPackCompiler.validate` via a source-mode launcher, using a supplied Java dependency classpath.
- CLI emits text or schema-versioned JSON, checks exact compiler success marker and target, enforces timeout/file-size/symlink guards, and does not build ZIPs or publish to Minecraft worlds. Synthetic golden input fixtures and Python bridge tests were added.
- **Not certified:** this milestone still requires running actual VoxelCore Maven/JDK 25 fixtures; classpath SHA provenance is not attested and Paper/Furniture/Vehicles runtime acceptance tests remain open. New Java bridge tests submitted to CI, not yet reported as passing here.
- See [Java validation instructions](JAVA-VALIDATION.md) and [development ledger](DEVELOPMENT-LOG.md).

# Offline lint / 26.3 authoring increment — 21 October 2026

- New shared read-only structural linter for CLI (`lint [root] [--json] [--strict]`) and Tkinter Diagnostics. Deterministic JSON reports use schema 1 and distinguish error/warning/info. Offline lint does **not** certify Java pack compilation, shader loading or Paper runtime support.
- `mc-26.3` is now an **authoring palette label only**, available alongside `mc-26.2`. GUI/CLI/recipe defaults select 26.3. No authoritative VoxelCore 26.3 target integration was executed.
- Added tests for clean scans, invalid references, external vanilla asset parents, JSON parse errors, warning strictness, addon-property conflicts and 26.3 palettes. **Initial CI:** 81 passed, 1 skipped, 4 failed on Linux/Python 3.10 due solely to a missing JSON import; fix committed, full rerun pending.
- Next: P0 Java 25 VoxelCore compiler golden fixtures and 26.3 target verification; improve source-path precision and schema-aware diagnostics before publication tooling.

# Development continuity milestone — 21 October 2026

- Added a durable [development ledger](DEVELOPMENT-LOG.md) reconstructing earlier PR #10 commits, recording decisions/limitations/next action and requiring per-commit updates for future code changes.
- A pull-request guard checks **each individual code-changing commit** for an in-commit ledger update, with small unit tests; branch protection is required to prevent bypass by direct pushes.
- **CI status for this branch:** pending at the time of authoring. This milestone changes project process, not Minecraft runtime compatibility.

# Implementation status — 18 October 2026

## Foundation hardening milestone

- `transactions.py`: OS-backed exclusive writer locks (POSIX flock / Windows byte-range lock), portable output path checks, protected allocation filenames, durable before/after snapshots and journals.
- Apply preconditions cover every scanned pack manifest/content definition plus explicitly tracked model inputs. Newly added definitions and stale in-memory workspaces invalidate previews.
- Rollback verifies every target and backup before the first mutation. Interrupted writes block further apply until explicit `recover`; `redo` restores recorded after-bytes. User edits cause conflicts, never forced recovery.
- CLI adds `snapshots`, `recover`, and `redo`. Directory fsync is performed on POSIX; Windows directory durability cannot be guaranteed by Python's portable APIs. This is offline authoring, not certified live publication.
- Corrected source-reviewed inheritance null/empty-event semantics and `.yaml` discovery. See [source pins](SOURCE-CONTRACTS.md).
- Validation at this milestone: **36 pytest tests passed on Linux/Python 3.12**, plus compileall. Includes separate-process lock exclusion, injected write failure, interrupted apply recovery, backup corruption, stale ancestors, Windows filename checks and redo. Windows execution and real power-loss testing remain unverified.

## Model/reference milestone

- `assets.py`: bounded local JSON parent resolution, inherited texture aliases, cycle/missing resource diagnostics, preserved geometry/UV/display transforms, typed incoming/outgoing item/model/texture graph, duplicate models and unused candidates. Vanilla parents remain explicitly external/unverified without client assets. The graph is not exhaustive for blocks, glyphs, rules or third-party plugins.
- `generators.py`: inherited texture slots work with alias/clone strategies. Opt-in related-item expansion follows source-verified furniture animation/state/display-part and vehicle chest/preview references. Generated state items preserve abstract status; explicit self model/drop links point at each new variant. Lists preserve selector data and maps emit minimal overrides. Unrelated shared references remain unchanged with warnings.
- Generated outputs cannot silently adopt identical unowned files. Recipes remain schema 1 with an optional dependency policy; changing strategy/policy requires explicit migration. Three-way merge and multi-axis recipes remain unimplemented.
- Tkinter adds References and History/recovery tabs, resolved geometry preview, background workspace indexing/generation/application and progress, and preview invalidation when options change. This is still a basic desktop UI, not the full visual studio.
- CLI adds `references` and `generate --include-dependencies`.
- Local validation: **56 passed, 1 display-dependent test skipped**, Python 3.12/Linux; compileall passes. Windows CI runs the new GUI smoke. Previous foundation commit passed all four Python 3.10/3.13 Linux/Windows CI jobs.

## Existing-item editor and packaging milestone

- `editing.py` adds comment/quote-preserving ruamel.yaml item edits with no-op byte identity, complete file diffs, semantic preservation checks, inheritance/reference validation and the existing transaction snapshots. Basic item fields and advanced YAML are available in Tkinter. Unsupported anchored/aliased documents remain read-only rather than risking shared-node changes. Full addon schema forms remain unimplemented.
- YAML discovery now accepts standard merge aliases while continuing to reject explicit duplicate keys and bounded excessive nesting/aliases.
- Unsaved editor changes require explicit discard when switching/opening/closing; edits and preview options invalidate stale plans.
- A Windows PyInstaller workflow runs tests, packages a native standalone directory, launches the packaged Tk smoke test and uploads a ZIP artifact with dependencies/checksums. This is a development build workflow, not production certification or a signed installer.
- Local validation: **67 passed, 1 skipped** (no local display), compileall passed. The preceding model milestone passed all four Linux/Windows CI jobs including the Windows GUI smoke. Current editor/package CI results must be checked separately.

## Multi-axis recipe milestone

- Added versioned, bounded material/color Cartesian recipes in Tkinter and CLI, with explicit source-item/texture-slot mappings, minimal inherited overrides, abstract states, typed reference rewriting, revision manifests and repeatability. See [recipe format](RECIPES.md).
- Custom family textures can represent wood, wool, concrete, stone or user-defined groups. This is explicit texture binding, not verified vanilla catalogs for every family; size/timing/tint axes remain future work.
- Additional fault tests cover interrupted rollback and corrupt late backups. Pale oak now appears in the 1.21.4 palette. Windows reparse-point outputs are rejected.
- Local test baseline: **76 passed, 1 display-dependent skipped**, Python 3.12/Linux; compileall passes. Windows/editor packaging at commit `8fa5073` passed CI and packaged EXE smoke. The multi-axis head requires its own CI result.

## Stack correction

The application **must be Python/Tkinter**, not Java/React/TypeScript. The Java VoxelCore plugin remains the canonical **external runtime/content compiler**, and only a later optional Python subprocess bridge will invoke it.

## Implemented in PR #10 (0.1.0 source MVP)

| Feature | Status | Evidence |
|---|---|---|
| Python package, launcher and CLI | Implemented | `pyproject.toml`, `content_manager/__main__.py`, `cli.py` |
| Native dark-themed Tkinter/ttk application | Implemented | `content_manager/app.py` |
| Open VoxelCore pack or content root | Implemented | read-only `Workspace`; no file modifications on open |
| Searchable item/furniture/vehicle/block/UI explorer | Implemented | Tk `Treeview` + ID-based search |
| Authored versus inherited inspector | Implemented (approximate) | Python merge mirrors common VoxelCore semantics; Java compiler not invoked |
| Create a basic item/furniture/vehicle YAML linked to existing JSON model | Implemented | `plan_new_item`; generated file isolated from handwritten YAML |
| Model asset association and simple geometry preview | Partial | Local parent chains resolved; Canvas cuboids remain untextured and approximate |
| Wood/planks variants, target palette filtering | Implemented (restricted) | `plan_family(..., "wood")`; a base such as `oak_table` is required |
| 16 wool colors, compound source prefixes | Implemented (restricted) | `plan_family(..., "wool")` supports `white_wool_chair` |
| Child item inheritance, model JSON alias or clone | Implemented (restricted) | exact one-texture-slot substitution, `extends`, new files |
| Dry-run preview, YAML/JSON diff and explicit apply | Implemented | changeset preview in GUI; CLI only applies with `--apply` |
| Ownership hashes, stale source protection, backup/rollback | Partial | refuse changes to manually edited output; snapshot restore; durable transaction service added; platform certification remains |
| Tests | 15 synthetic pytest tests pass locally | `tests/test_content_manager.py` |
| Resource pack compilation or real plugin semantic validation | **Not implemented** | requires VoxelCore Java CLI bridge |
| Furniture blockstates/animation model fanout | Partial | opt-in typed material-prefixed related-item expansion; see milestone above |
| Vehicle chest model/physics editing | **Not implemented** | only basic starter config form |
| Robust texture editing, import, UV / shader preview | **Not implemented** | needs model asset pipeline |
| Existing YAML editing | Partial | basic fields + advanced item YAML, round-trip file diff and backup; full addon forms and anchors remain incomplete |
| Safe live server publish/reload | **Not implemented** | offline source authoring only |

## MVP restrictions and risk notes

- Existing YAML is left alone. The generator writes **new individual YAML files** under `content/generated/contentmanager/<recipe>/` and new JSON models under the source's model directory. This avoids damaging comments in the original source.
- Source IDs must start with a material prefix: `oak_table`, `white_wool_chair`. Existing model must use a slot whose value exactly matches the appropriate `minecraft:block/<material>_planks` or `minecraft:block/<color>_wool`.
- The `alias` strategy creates a child model inheriting the source geometry and overriding one texture alias; `clone` deep-copies the original model JSON and overrides that slot. No semantic whole-model recolor or nested state model generation.
- Current generator warns when inherited `properties.furniture.model_item`, `vehicle.model_item`, `drop`, `animation`, `blockstates` or vehicle storage could cause unexpected variant relationships.
- Minecraft 1.12.2 is excluded from automatic palette generation due to different vanilla texture ID conventions. More recent version choices constrain wood families, but **this is curated Python catalog filtering rather than authoritative Minecraft content verification**.
- Run against a *copy* of your server's content first. Before deployment, verify with your actual compatible VoxelCore Java compiler and Paper test server.

## Remaining acceptance gates (current, not a list of missing MVP features)

1. **P0 / #1 — In progress:** Source contract pins exist. Must add real
   Furniture/Vehicle parser fixtures, Java 25 compiler harness, pack-target
   smoke tests and a current 26.3 support matrix.
2. **P1 / #2 — Implemented in part:** Offline locks, journals, backups,
   optimistic preconditions, redo and Windows filename safeguards exist.
   Still needs real Windows/reparse-point and power-loss durability
   certification, watcher/reopen policies and permission hardening.
3. **P2 / #3 — Implemented in part:** Item inheritance, source-bound editing,
   model/texture reference graph, JSON parent-chain resolution and CLI lint
   exist. Still needs plugin-wide graph, semantic field provenance,
   three-way merge and authorable rename impact review.
4. **P3 / #4 — Implemented in part:** Approximate Tkinter model geometry
   preview exists. Still needs texture/UV pixel studio and accurate animation,
   display, seat and hitbox overlays.
5. **P4 / #5 — Implemented in part:** Wood/wool generator, related item
   references and bounded multi-axis recipes exist. Still needs
   three-way merge, arbitrary dependent asset transformations, and
   authoritative runtime/target verification.
6. **P5 / #6 — Open:** Full source-pinned Furniture, Vehicles and Blocks
   schema editors, advanced forms and parser-confirmed output.
7. **P6 / #7 — Open:** Java compiler subprocess bridge, glyph/localization
   studio, atlas checks, true target validation and shop catalogue editing.
8. **P7 / #8 — Open:** Staged validated publishing and deployment
   certification; current local backups are **not** safe live publication.
9. **P8 / #9 — Open:** Integration testing against supported Paper/Java
   versions, large-workspace performance, packaging certification and release.

The synthetic Python tests establish only offline behavior and do not prove
Minecraft/Paper correctness or 26.3 compiler compatibility. Keep production
certification status **open** until the acceptance criteria actually pass.
