> **Current checkpoint (21 October 2026):** The offline linter and curated
> `mc-26.3` material palette are implemented on a development branch, but
> VoxelCore Java compiler/parser validation for 26.3 remains a **P0 gate**.
> Consult [the development ledger](DEVELOPMENT-LOG.md) and
> [implementation status](IMPLEMENTATION-STATUS.md) before trusting a milestone.
> Every code-changing PR commit must update the ledger.

# Complete implementation roadmap

**Baseline:** 2026-10-18, repository `VoxelHorizons/ContentManager`. A **Python 3.10+ Tkinter MVP** is committed, with a shared CLI, structural import, YAML inspection, basic model viewing, conservative generator and 15 passing pytest tests. Most roadmap gates remain open. See [implementation status](IMPLEMENTATION-STATUS.md).

## Current session progress

P1 offline transactions, P2 reference resolution/basic YAML edits, P4 linked and
multi-axis material recipes, and P8 Windows development packaging have progressed.
See IMPLEMENTATION-STATUS.md for executed tests and remaining limitations. **No
phase is closed:** authoritative Java compiler/Paper tests, full schema editors,
textured/interactive asset tools, exhaustive references and safe publishing remain.

## Delivery strategy

Follow vertical slices, not hundreds of empty UI controls. The target first fully certified scenario is **open existing VoxelCore pack → inspect Oak Table → generate Spruce/Birch variants → diff → validate via VoxelCore → publish safely → reopen and regenerate idempotently**. Expand to other content kinds only after this path is dependable.

| Phase | Core deliverable | Exit gate |
|---|---|---|
| **P0 Contracts and fixtures** | Pin source SHAs, extract fixture YAML/model trees, schema matrix, version capabilities, accepted sample outputs | Maintainer approves format contracts; fixtures compile with VoxelCore |
| **P1 Workspace/CLI foundation** | Python service functions + argparse CLI, Tkinter bootstrap, project import, source indexing, read safety, revision tracking and OS file lock | Import real sample untouched; second open has zero diff; symlink escape rejected; cross-process lock added |
| **P2 Canonical graph + editors** | Typed identities/edges, CST-preserving YAML/JSON patches, source/resolved views, undo, diagnostics | Parent and cross-file references correct; YAML comments/order retained; unknown keys survive |
| **P3 Asset and model studio** | Tk Canvas previews with optional Pillow, model/PNG catalog, parent/texture alias resolution, transform + hitbox overlays | Representative table, bench and tractor previews match defined transforms within documented tolerances |
| **P4 Variant recipe engine** | Wood + wool versioned palettes, material axes, share/parent/clone strategies, deterministic diff, provenance, regeneration and conflict merge | 12-type wood and 16-color wool suites, zero unexpected changes on second run; human edits protected |
| **P5 Addon-specific editors** | Furniture form, vehicle form, animations/states/display-parts, storage, vehicle tint/chest, block editor | Real authored fixtures survive parse/write/reload; errors match plugin parser; legacy behavior gated |
| **P6 UI, economy-facing and pack build** | Glyph/font editor, shop/worth references, localization lint, pack target matrix, compiler validation/build, reproducible ZIP | All selected target profiles pass expected validation; unsupported features reported; no allocation churn |
| **P7 Deployment/recovery** | Local deploy, snapshots, explicit review, backup, atomic publish, rollback, optional test server workflow | Fault injection mid-write leaves live tree intact or recovers automatically; no silent reload |
| **P8 Advanced integrations/release** | Optional authenticated Paper bridge, FurnitureShop layout introspection, shop/DM adapters, Git integration, installers, plugin compatibility dashboard | Staging Paper 26.2/Java 25 tests, docs, migrations, security audit and performance budgets pass |

**Parallelizable work:** UX prototypes, model fixtures, schema inventory and CLI read-only API design can proceed during P0/P1; live write paths cannot bypass P1/P2 gates. Advanced AI helpers are an explicitly optional post-MVP stream.

## P0: source truth and test corpus (must precede implementation)

- Record exact commits of VoxelCore, VoxelFurniture, VoxelVehicles, VoxelFurnitureShop, VoxelShop and relevant resource-pack components and test versions.
- Confirm source-of-truth paths and accepted plugin-specific YAML fields, especially furniture blockstates/display_parts and vehicle inventory/chest settings.
- Capture self-contained tests: basic item, inherited abstract item, block, furniture with seat, bench drawer open state, neighbor/corner state, dyeable curtains, LAND tractor with chest, PLANE, UI glyph/font, invalid atlas model and shop menu.
- Compile each sample using a **version-pinned** `ContentLoader` and `JavaPackCompiler` test harness, then compare output against expected diagnostic and ZIP manifest.
- Freeze spec `recipe_schema: 1`, path normalization, ownership rules, typed graph edge map, migration rules and API error envelope.
- Write risk register and golden master fixtures using only assets legally shareable in this repository (synthetic fixtures preferred).
- Document output compatibility for `mc-1.12.2`, `mc-1.13.2`, `mc-1.14.4`, `mc-1.19.4`, `mc-1.20.5`, `mc-1.21.4`, `mc-26.2`.

**Gate:** a representative parent/child table family and an abstract animated state model can already be validated by VoxelCore external fixture tests without running the studio. Do not implement generators against hypothetical schemas.

## P1: Python workspace, CLI and Tkinter application

Create a standard Python package with `pyproject.toml`, portable Tkinter/ttk application and argparse CLI sharing core services. The MVP already implements `gui`, `scan`, `generate`, and `rollback`. Further editor/build CLI commands are gated until validated.

Read-only import profiles: choose standalone content root or server installation. Detect packs, namespaces, dependencies, current plugin versions (if present), shader/model assets, existing render/block/glyph allocations and source file permissions. No modification on discovery, no automatic file upgrade.

File hashes, best-effort atomic sibling writes and restore snapshots exist. Add debounce/file watchers, cross-process writer locks, staged journals, complete crash recovery, and file permission policies before P1 can be closed. No local HTTP service is needed; Tkinter calls Python domain services directly. Extend pure service read APIs for explorer and scriptable diagnostics.

**Acceptance:** dry-run never modifies a byte, path-traversal/symlink attacks fail, and restart/reopen preserves indices. Watcher notifications never invalidate unsaved edits silently.

## P2: graph, content AST and basic forms

Create single id/location resolver and schema/adapters. Show raw and resolved YAML values side-by-side, field-level provenance, inheritance cycles, duplicate IDs, missing pack dependencies and runtime limitations. Semantic patcher writes only approved nodes and retains comments. Implement safe undo/redo.

**Acceptance:** edit one child's display name without touching unrelated content; report exact file and YAML path; generated YAML still passes authoritative compilation. Refactor preview enumerates incoming typed references; no arbitrary search/replace.

## P3: assets and preview

Texture/model explorer, drag/drop association, 2D pixel grid, parent/texture slot resolver, edit JSON with syntax/semantic diff. Render Minecraft-style `elements` cuboids, UV, rotations, `display` transforms, tint and animation-state switching as supported. Provide separate object transforms for furniture visual model, interaction hitbox, collision blocks and vehicle seat/physics overlays.

**Acceptance:** missing texture and parent-cycles visibly flagged, source PNG unchanged unless saved, nearest-neighbor render verified by pixel fixtures. Studio preview limitations clearly labeled.

## P4: generators MVP

Ship family provider API and two built-in recipes: wood planks and wool colors. Include branch selection, version filtering, output names, source/child inheritance, model strategy, associated abstract state expansion, ownership manifest, regenerate/detach and three-way merge. Add virtual filesystem, exact diff and apply.

**Acceptance tests:**
- Repeated same recipe and inputs -> zero changes and identical output digests.
- Change source furniture rotation -> descendants inherit unless child overrides.
- Manually edit one variant texture -> regeneration preserves or visibly conflicts.
- Source abstract true, child concrete -> `abstract: false` correctly authored.
- Invalid texture/cross-pack dependency -> validation fails before any output.
- Attempt delete a generated asset referenced elsewhere -> blocked pending explicit impact review.
- Unbounded color × wood × state expansion -> protected by hard count limit.

## P5: richer plugin integrations

Forms cover Furniture accepted nested sections (with source parser), Vehicle properties including storage/chest model/preview ID and color, custom blocks, item actions, model state/inventory metadata and per-addon presets. Plugin-specific integration must be optional; unknown or removed addon versions report read-only/unsupported rather than deleting keys.

**Acceptance:** each resulting item can be loaded by its plugin on a staged Paper instance, not only VoxelCore's pack compiler. Include WorldGuard/Lands compatibility notes but do not attempt to change server permissions in a content authoring tool.

## P6: pack, UI and shop references

Use VoxelCore's existing bitmap UI definitions, font allocation manifest, authored vanilla language overrides and atlas compiler. Preview offset glyph aliases and apply target version restrictions. Add read-only VoxelShop catalogue import and edit only version-confirmed authored config keys. Abstract inventory GUI icons are allowed where supported, whereas trade stock must use concrete item definitions. Currency values are *metadata previews*, never wallet writes.

**Acceptance:** resource pack ZIP equals VoxelCore compiler result for given fixture inputs; duplicate/legacy atlas problems are reported from compiler, not masked by studio. No render/block/glyph manifest deletion, renumbering or reuse.

## P7: publication

Local publish requires explicit folder mapping and supports: snapshot -> stage -> validate -> diff -> commit files -> optional server command to reload; never live-write while generator previewing. Optional server live bridge introduced only after local safe paths. Provide manual zip export for offline plane/travel use without external services.

**Acceptance:** exception at any injected stage allows recovery to previous valid content, including correct allocation files; refusal to deploy when a VoxelCore validation is red, disk space is low, target paths unsafe or a running server has stale revision.

## P8: hardening and release

- Real Paper 26.2 Java 25 tests of model variants, furniture placing/breaking, shop showroom snapshots, vehicles with/without chest, storage and restarts.
- Regression suites for Minecraft 1.12 through 26.2 pack targets. Older addons may not support a target; distinguish their runtime support from pack build support.
- CI matrix: Python 3.10–3.13 on Windows/Linux with pytest/compileall, optional Tkinter smoke on a display-enabled runner, Java 25 toolchain only for the future VoxelCore compiler bridge, golden fixtures, dependency scanning, package signatures and checksums.
- Performance/load: 10k item nodes, 50k asset references, 1k-generation dry-run, cold/warm search/preview, bounded memory, cancellation tests.
- Release formats: portable Python source and zip first; Windows standalone packaging via PyInstaller (optional) after security review, with macOS/Linux wrappers later. Headless Python CLI supports offline automation.

## Definition of done for 1.0

A first-time user can import an actual VoxelCore pack, create a furniture item, link a model, generate both wood and wool families, inspect every resulting model and inherited definition, modify one variant safely, validate/build `mc-26.2`, deploy with backup and undo, and reopen the project with **no drift**. Real VoxelFurniture/VoxelVehicles examples pass staged in-server loading and restarts. Every failure shows actionable source paths; no silent data loss is accepted.

Features not satisfying this path remain flagged `planned` or `experimental` in product/docs, not marketed as fully supported.

## Post-1.0 backlog

Rich Bedrock/Geyser preview and conversion, collaborative multi-user sessions, controlled cloud sync, procedural 3D modeling, AI-assisted asset generation, live in-world editing of FurnitureShop snapshots, full DeluxeMenus designer, video fly-through previews and content marketplace. Each must respect source ownership and target runtime licensing/compatibility.
