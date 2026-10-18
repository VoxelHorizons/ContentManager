# Implementation status — 18 October 2026

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
| Model asset association and simple geometry preview | Partial | Existing JSON file picker + `Canvas` cuboids; no full parent/UV/texture/shader interpretation |
| Wood/planks variants, target palette filtering | Implemented (restricted) | `plan_family(..., "wood")`; a base such as `oak_table` is required |
| 16 wool colors, compound source prefixes | Implemented (restricted) | `plan_family(..., "wool")` supports `white_wool_chair` |
| Child item inheritance, model JSON alias or clone | Implemented (restricted) | exact one-texture-slot substitution, `extends`, new files |
| Dry-run preview, YAML/JSON diff and explicit apply | Implemented | changeset preview in GUI; CLI only applies with `--apply` |
| Ownership hashes, stale source protection, backup/rollback | Partial | refuse changes to manually edited output; snapshot restore; no crash-recovery journal or cross-process lock |
| Tests | 15 synthetic pytest tests pass locally | `tests/test_content_manager.py` |
| Resource pack compilation or real plugin semantic validation | **Not implemented** | requires VoxelCore Java CLI bridge |
| Furniture blockstates/animation model fanout | **Not implemented** | warning only |
| Vehicle chest model/physics editing | **Not implemented** | only basic starter config form |
| Robust texture editing, import, UV / shader preview | **Not implemented** | needs model asset pipeline |
| Full form-based existing YAML editing | **Not implemented** | source configurations currently read-only |
| Safe live server publish/reload | **Not implemented** | offline source authoring only |

## MVP restrictions and risk notes

- Existing YAML is left alone. The generator writes **new individual YAML files** under `content/generated/contentmanager/<recipe>/` and new JSON models under the source's model directory. This avoids damaging comments in the original source.
- Source IDs must start with a material prefix: `oak_table`, `white_wool_chair`. Existing model must use a slot whose value exactly matches the appropriate `minecraft:block/<material>_planks` or `minecraft:block/<color>_wool`.
- The `alias` strategy creates a child model inheriting the source geometry and overriding one texture alias; `clone` deep-copies the original model JSON and overrides that slot. No semantic whole-model recolor or nested state model generation.
- Current generator warns when inherited `properties.furniture.model_item`, `vehicle.model_item`, `drop`, `animation`, `blockstates` or vehicle storage could cause unexpected variant relationships.
- Minecraft 1.12.2 is excluded from automatic palette generation due to different vanilla texture ID conventions. More recent version choices constrain wood families, but **this is curated Python catalog filtering rather than authoritative Minecraft content verification**.
- Run against a *copy* of your server's content first. Before deployment, verify with your actual compatible VoxelCore Java compiler and Paper test server.

## Work remaining in order

1. P0 source-verified fixtures for full Furniture/Vehicle parser grammars; integration against true resource pack compiler.
2. P1 durable filesystem write lock, crash recovery and Windows path safety, tests across systems.
3. P2 model reference graph, real full parent/texture resolution and safe YAML editor.
4. P3 Tkinter asset/pixel studio and richer 3D preview (optional Pillow, CPU scene rasterizer).
5. P4 recipe DSL with dependent animation/blockstate fanout, multiple axes and three-way merge.
6. P5 full schema-driven Furniture/Vehicle/Block forms and source configuration editing.
7. P6 VoxelCore compiler bridge, UI glyph/atlas, target compatibility and shop references.
8. P7 staged offline publish, rollback certification, safe optional live bridge.
9. P8 packaging, Windows runtime smoke, Paper 26.2 integration and release.

Current tests establish the core Python file operations, **not** full Minecraft/Paper correctness. Do not mark production-ready until all gates are met.
