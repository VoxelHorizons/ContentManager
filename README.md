# Voxel Horizons Content Manager

**Status: architecture and delivery plan only (2026-10-18). No application code has been implemented.**

Content Manager is a **local-first visual content studio** for the Voxel Horizons Minecraft ecosystem. It authors existing VoxelCore content packs, associates item/block/furniture/vehicle definitions with JSON models and PNG textures, generates material and color families, validates content using the actual VoxelCore compilers, and publishes deterministic artifacts through a staged and reversible workflow.

This is a companion authoring tool, **not** a second item registry, a replacement for VoxelCore's resource-pack compiler, or a plugin that owns placed furniture, vehicles, inventories, or shop transactions.

## What it will do

- Discover and import an existing `plugins/VoxelCore/content` workspace without modifying source on import.
- Create/manage items, blocks, furniture, furniture variants, vehicles, UI glyphs, models, textures, item actions, basic shop catalogue associations, and pack dependencies.
- Link every definition to its source YAML, resource model, textures, related ContentIDs, generated derivatives, and runtime consumers.
- Generate **oak_table -> wood-family tables** or **white_wool_chair -> 16 wool-colored chairs**, with configurable naming, display labels, model reuse versus cloning, inherited YAML, state variants, and reviewable changes.
- Offer a visual model/texture editor, 3D previews, hitbox/seat/offset guides, inheritance inspection, validation, relationship graphs, bulk operations, and an undo/diff experience.
- Preview and validate all supported Minecraft target versions, use VoxelCore as the compiler of record, and deploy only via backup + explicit user approval.
- Preserve existing authored content and avoid invalidating persisted render, block, or font allocations.

## Architectural decisions

**Primary stack (planned):** Java 25 local HTTP service and CLI (reuse version-pinned VoxelCore common/pack libraries); React + TypeScript + Vite UI; Three.js preview; a YAML concrete-syntax-tree editor for comment/format preservation. The service serves the bundled UI strictly on loopback with an ephemeral session capability. The same domain operations power GUI and CLI. Packaging: portable runnable distribution first, native installers later.

**Canonical runtime format:** VoxelCore pack YAML, model JSON, textures and actual plugin configurations. The studio's optional `.contentmanager/` recipe/ownership metadata is **authoring metadata only**; it must never become an unsupported key inside VoxelCore YAML.

**Environment:** primary test target Paper 26.2 / Java 25; older VoxelCore pack profiles remain selectable when the source compiler supports them. Folia is out of scope.

## Planning documents

1. [Architecture and internal boundaries](docs/ARCHITECTURE.md)
2. [Product specification and interaction design](docs/FEATURES-AND-UX.md)
3. [Generators, output contracts and examples](docs/GENERATORS-AND-CONTRACTS.md)
4. [Implementation roadmap and gated acceptance criteria](docs/ROADMAP.md)
5. [Security, compatibility, testing and deployment](docs/SAFETY-AND-TESTING.md)
6. [Architectural decisions and unresolved integration checks](docs/DECISIONS.md)

**Development rule:** Do not start application implementation until these specifications, source-of-truth rules, interfaces, safe write guarantees and phase-0 acceptance tests have been reviewed. Do not claim a generator or deployer is complete on the strength of a GUI mockup or isolated unit tests.

## Source repositories examined

- [VoxelCore](https://github.com/VoxelHorizons/VoxelCore): content pack discovery, item inheritance, custom blocks, render/texture atlas handling, UI glyphs and Java pack compiler.
- [VoxelFurniture](https://github.com/VoxelHorizons/VoxelFurniture): `properties.furniture`, model/animation/state/interaction rendering.
- [VoxelVehicles](https://github.com/VoxelHorizons/VoxelVehicles): `properties.vehicle`, physics, seat, collision, storage and dyeable variants.
- [VoxelFurnitureShop](https://github.com/VoxelHorizons/VoxelFurnitureShop): showroom snapshots and derived pricing tooltip integrations.
- [VoxelShop](https://github.com/VoxelHorizons/VoxelShop): user-authored shop catalogues, currencies and transaction-safety boundaries.
- [VoxelWorlds](https://github.com/VoxelHorizons/VoxelWorlds) and [Resourcepack-Expansion](https://github.com/VoxelHorizons/Resourcepack-Expansion): secondary consumers and language/resource-pack compatibility.

**Repository links represent inspected main-branch interfaces as of 2026-10-18, not a frozen API release.** Phase 0 will pin actual commits and record compatibility checks before code is written.
