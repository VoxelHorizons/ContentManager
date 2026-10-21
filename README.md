# Voxel Horizons Content Manager

**Status (2026-10-21): Python/Tkinter authoring studio in active development; core offline features implemented, but Java/Paper validation and production deployment remain incomplete. See [implementation status](docs/IMPLEMENTATION-STATUS.md) and [development ledger](docs/DEVELOPMENT-LOG.md).**

Content Manager is a **local-first visual content studio** for the Voxel Horizons Minecraft ecosystem. It authors existing VoxelCore content packs, associates item/block/furniture/vehicle definitions with JSON models and PNG textures, generates material and color families, validates content using the actual VoxelCore compilers, and publishes deterministic artifacts through a staged and reversible workflow.

This is a companion authoring tool, **not** a second item registry, a replacement for VoxelCore's resource-pack compiler, or a plugin that owns placed furniture, vehicles, inventories, or shop transactions.

## Planned product capabilities

- Discover and import an existing `plugins/VoxelCore/content` workspace without modifying source on import.
- Create/manage items, blocks, furniture, furniture variants, vehicles, UI glyphs, models, textures, item actions, basic shop catalogue associations, and pack dependencies.
- Link every definition to its source YAML, resource model, textures, related ContentIDs, generated derivatives, and runtime consumers.
- Generate **oak_table -> wood-family tables** or **white_wool_chair -> 16 wool-colored chairs**, with configurable naming, display labels, model reuse versus cloning, inherited YAML, state variants, and reviewable changes.
- Offer a visual model/texture editor, 3D previews, hitbox/seat/offset guides, inheritance inspection, validation, relationship graphs, bulk operations, and an undo/diff experience.
- Preview and validate all supported Minecraft target versions, use VoxelCore as the compiler of record, and deploy only via backup + explicit user approval.
- Preserve existing authored content and avoid invalidating persisted render, block, or font allocations.

## Run the current Python MVP

Install Python 3.10+ (with Tkinter) and run from this repository:

```powershell
py -m pip install -e .
py -m content_manager gui
# On Windows, you can also double-click Launch-ContentManager.bat after setup.
```

Or browse packs and generate variants from the CLI:

```powershell
py -m content_manager scan "C:\\Minecraft\\plugins\\VoxelCore\\content"
py -m content_manager generate "C:\\Minecraft\\plugins\\VoxelCore\\content" voxel:oak_table --family wood --strategy alias
# Only after reviewing the dry-run output:
py -m content_manager generate "C:\\Minecraft\\plugins\\VoxelCore\\content" voxel:oak_table --family wood --strategy alias --apply
```

The GUI can also open a single content pack directly. The current implementation creates new item/furniture/vehicle YAML linked to **existing** model JSON files, previews source/resolved inherited items, renders a simplified cuboid outline, and supports wood/wool family generation using `alias` and `clone` strategies. Generated files are isolated under `content/generated/contentmanager/`; provenance and rollback backups live in each pack's `.contentmanager/` sidecar.

**Limitations:** This MVP does **not** execute the authoritative VoxelCore Java pack compiler, hot-deploy to a server, render textures or shaders accurately, generate associated Furniture blockstate/animation child models, or offer full property-form editing. Review generated model associations (particularly sticky `model_item`/`drop` references), run VoxelCore pack validation and test on a copied staging server before deploying. See [implementation status](docs/IMPLEMENTATION-STATUS.md).

## Complete roadmap

## Architectural decisions

**Required stack:** **Python 3.10+ and native Tkinter/ttk**, with PyYAML. No React, TypeScript, Java backend, Vite, Electron or required local HTTP server. The Python engine drives both Tkinter and the CLI; optional Pillow and a future Python subprocess bridge to VoxelCore's authoritative Java compiler may be added. A standard-library Tkinter canvas provides the current *approximate* cuboid preview.

**Canonical runtime format:** VoxelCore pack YAML, model JSON, textures and actual plugin configurations. The studio's optional `.contentmanager/` recipe/ownership metadata is **authoring metadata only**; it must never become an unsupported key inside VoxelCore YAML.

**Environment:** primary test target Paper 26.2 / Java 25; older VoxelCore pack profiles remain selectable when the source compiler supports them. Folia is out of scope.

## Planning documents

1. [Implementation status (completed versus planned)](docs/IMPLEMENTATION-STATUS.md)
2. [Architecture and internal boundaries](docs/ARCHITECTURE.md)
3. [Product specification and interaction design](docs/FEATURES-AND-UX.md)
4. [Generators, output contracts and examples](docs/GENERATORS-AND-CONTRACTS.md)
5. [Implementation roadmap and gated acceptance criteria](docs/ROADMAP.md)
6. [Security, compatibility, testing and deployment](docs/SAFETY-AND-TESTING.md)
7. [Architectural decisions and unresolved integration checks](docs/DECISIONS.md)

**Development rule:** Iterate through gated vertical slices. The MVP exists, but formal P0 cross-plugin Java compiler fixtures and production safety gates are **not** complete; do not treat the current generator as runtime-verified. Do not claim a generator or deployer is complete on the strength of a GUI mockup or isolated unit tests.

## Source repositories examined

- [VoxelCore](https://github.com/VoxelHorizons/VoxelCore): content pack discovery, item inheritance, custom blocks, render/texture atlas handling, UI glyphs and Java pack compiler.
- [VoxelFurniture](https://github.com/VoxelHorizons/VoxelFurniture): `properties.furniture`, model/animation/state/interaction rendering.
- [VoxelVehicles](https://github.com/VoxelHorizons/VoxelVehicles): `properties.vehicle`, physics, seat, collision, storage and dyeable variants.
- [VoxelFurnitureShop](https://github.com/VoxelHorizons/VoxelFurnitureShop): showroom snapshots and derived pricing tooltip integrations.
- [VoxelShop](https://github.com/VoxelHorizons/VoxelShop): user-authored shop catalogues, currencies and transaction-safety boundaries.
- [VoxelWorlds](https://github.com/VoxelHorizons/VoxelWorlds) and [Resourcepack-Expansion](https://github.com/VoxelHorizons/Resourcepack-Expansion): secondary consumers and language/resource-pack compatibility.

**Repository links represent inspected main-branch interfaces as of 2026-10-18, not a frozen API release.** Phase 0 will pin actual commits and record compatibility checks before code is written.

## Development update: recovery and related variants

```bash
python -m content_manager references /path/to/content --node item:voxel:oak_table
python -m content_manager generate /path/to/content voxel:oak_table --family wood --include-dependencies
python -m content_manager snapshots /path/to/pack
python -m content_manager recover /path/to/pack /path/to/pack/.contentmanager/backups/SNAPSHOT
python -m content_manager redo /path/to/pack /path/to/pack/.contentmanager/backups/SNAPSHOT
```

Related generation follows known furniture animation/blockstate/display-part and vehicle chest/preview IDs **only when they share the source material prefix and pack**. It preserves abstract state items and selector data. Review every diff; unrelated shared dependencies remain unchanged. Local parent/texture resolution does not certify vanilla geometry, atlas behavior or server compatibility.

Apply/rollback/redo coordinate through an OS writer lock. An interrupted operation leaves a journal and blocks further writes until explicit recovery. Recovery refuses externally edited targets. Keep backups: automatic force recovery and live server publication are intentionally unavailable. See [current implementation status](docs/IMPLEMENTATION-STATUS.md) and [source contracts](docs/SOURCE-CONTRACTS.md).

## Editing and standalone Windows builds

Select an item and open **Edit item**. Update the basic fields into the YAML buffer or edit its authored YAML directly, preview the full file diff, then apply. The editor preserves existing comments/quotes where possible and refuses semantic changes to unrelated definitions. Anchored YAML remains read-only. History supports undo/redo with external-edit conflict checks.

The **Windows desktop package** Actions workflow builds a PyInstaller directory and tests the packaged launch. Download its artifact, extract everything, and run `VoxelHorizons-ContentManager.exe` beside `_internal`. No Python installation is needed for that build. Artifacts are unsigned development builds; successful launch is not evidence of full Minecraft compatibility.

## Continuing development safely

Read the [development ledger](docs/DEVELOPMENT-LOG.md) first. It links the latest
source-truth documents, prior merged PR, remaining issue gates, and precise
next task. Every code-changing commit must add its own progress entry (what
changed, verification, limitations and next action); the PR CI guard checks
individual commits, not merely the PR diff. Do not treat a roadmap checkbox
as runtime verification without the source-pinned Java/Paper acceptance tests.

## Offline diagnostics (development)

```bash
python -m content_manager lint /path/to/plugins/VoxelCore/content
python -m content_manager lint /path/to/plugins/VoxelCore/content --json
python -m content_manager lint /path/to/plugins/VoxelCore/content --strict
```

The Tkinter **Diagnostics** tab uses the same read-only checks. CLI exits 1
when an error is found, or when `--strict` detects a warning; otherwise exits
0. A missing external workspace pack produces a warning, not a failure.
JSON output is schema-versioned and never certifies pack validity. The
`mc-26.3` target is now the default for material/texture variant authoring,
but the offline palette list is **not** proof that VoxelCore can compile the
pack or that a plugin will load its definitions on Paper 26.3.

## Optional VoxelCore Java pack validation

The opt-in `validate-java` CLI now stages selected content into a disposable
snapshot and invokes an externally supplied VoxelCore Java compiler classpath
without touching authored packs or live allocations. Unlike the Python
`lint` command, it calls `JavaPackCompiler.validate`. See
[Java bridge setup, guarantees and limitations](docs/JAVA-VALIDATION.md).

```bash
python -m content_manager validate-java /path/to/content --classpath-file /path/to/voxelcore-classpath.txt --target mc-26.3 --json
```

Successful validation **does not** certify Paper runtime behavior or full
VoxelFurniture/VoxelVehicles plugin integration.

## Tkinter: optional Java pack validation

In **Diagnostics**, choose the VoxelCore Java classpath text file (and,
optionally, an existing render-allocations manifest), then select
**Validate saved content with VoxelCore Java**. This runs on a background
worker against a temporary copy and displays compiler output in the same
panel. It validates **saved** files; unsaved YAML editor changes are not
included. Build/classpath setup and limits are in
[Java validation](docs/JAVA-VALIDATION.md).
