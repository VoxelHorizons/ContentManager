# Architecture decisions and verification register

These are **proposed decisions for the planning PR**, not evidence that the software is implemented.

## Accepted-design candidates

**ADR-001 — Keep plugin files canonical.** VoxelCore content packs and runtime config remain source of truth. Studio recipes and indexes are optional sidecars; no new server plugin is needed to read generated content. Rationale: existing VoxelCore has mature inheritance/identity/build semantics; reimplementing would cause divergence.

**ADR-002 — Java 25 backend plus TypeScript frontend.** Java integrates with source-pinned VoxelCore common/pack classes, offers headless CLI and loopback local service. React/TS provides advanced UI and syntax-aware YAML editing; Three.js provides approximate geometry preview. An Electron runtime is not initially required. The frontend must not secretly become a separate compiler.

**ADR-003 — Use the exact compiler as authority.** `ContentLoader` and `JavaPackCompiler.validate/compile` produce definitive diagnostics and resource pack ZIP. No model fix or allocation algorithm is forked into this repository.

**ADR-004 — Generation is an explicit, reversible transaction.** Recipe + manifest own only declared changes. Three-way merge preserves human edits; all writes stage, review and snapshot first.

**ADR-005 — Versioned adapters and target-aware palettes.** Wood/material/colors/feature availability derive from a target version catalog; the current plugin parsers define accepted item/furniture/vehicle schemas. A schema mismatch is a diagnostic and unsupported mode, not a best-effort destructive rewrite.

**ADR-006 — Local-first/no mandatory network.** All core editing, generation and pack building work offline. GitHub integration, updates, AI and remote deployment are opt-in.

**ADR-007 — World snapshots are not item variants.** VoxelFurnitureShop `snapshots/variants` are captured world layouts, distinct from per-item wood/color/animation/model variants. Editor can inspect/link them in later phases but cannot pretend to generate a world layout by swapping model textures.

## Interfaces requiring source-level verification in P0

- Exact source commit SHAs, Maven artifact availability, relocation/shading boundaries and stable calling convention of `voxelcore-common` and `voxelcore-pack`.
- Whether `JavaPackCompiler.validate` ever changes temporary allocations or examines runtime global asset files; enforce sandbox wrapper in either case.
- Current grammar and default semantics of `FurnitureDefinitionParser`: `blockstates`, neighbor selectors, local transforms, `display_parts`, animation and worth.
- Current `VehicleInventoryDefinition` chest/rows/model preview storage fields, and possible behavioral drift from its README.
- Actual asset paths, source model indirections, item IDs and custom texture roles in user's furniture and vehicle packs; the design examples are schematic and do not assert those exact assets exist.
- Licensing and permissible provenance of Minecraft vanilla textures/models, optional externally imported resources and ShopGUIPlus authored YAML.
- Renderer parity in GUI transforms, fallback armor stand and modern ItemDisplay, especially hand-coded shader portraits.
- Whether plugin-specific `reload` hooks safely refresh each type in the same content revision, and which files require a full Paper restart.
- Exact structure and write ownership of each allocation manifest; maintain tombstones and existing IDs.
- Scope of live VoxelShop integration; no GUI authoring for transaction-critical state until the current staging safety gates pass.

## Rules for design changes

A new feature should identify: user story, runtime owner, changed canonical files, graph edges, exact output keys, target version capability, schema adapter, read/write hazards, safe diff example, generator or editor provenance and acceptance tests. Update these documents first when changing a previously approved architecture contract.

## First vertical slice contract

Given a valid example pack with `voxel:oak_table` and a shared alias-based table model:

1. Workspace loads with **zero file changes**.
2. Graph finds `oak_table`, its model, inherited furniture properties and textures.
3. Wood generator plans `spruce_table`, `birch_table` and one selected additional compatible variant; live files unchanged.
4. Review lists exact new YAML keys and child JSON models, with no unintended source diff.
5. VoxelCore validator approves the staged content on `mc-26.2`; any failure blocks Apply.
6. Applied output can be built into a deterministic ZIP.
7. Re-running the same generator reports **zero changes**.
8. Editing one generated child manually and changing source behavior produces a correct disjoint merge or an explicit conflict.
9. Undo restores previous source and allocations exactly.
10. A real staged server loads and renders the material variants, and loads placed furniture without state errors.

This ten-point scenario is the first implementation checkpoint; it should be the center of the initial CI suite and UI demo.
