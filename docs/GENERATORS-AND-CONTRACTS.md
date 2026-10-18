# Generators, schemas and output contracts (Python Tkinter desktop)

## 1. Boundary: recipe vs runtime content

**Planned recipes** live in `.contentmanager/recipes/*.yml`. The current MVP does not parse that DSL: it generates variants directly from Tkinter/CLI inputs and records `.contentmanager/manifests/*.json` output hashes. Recipes are an optional next phase of repeatability. Expanded YAML and JSON must conform to existing plugin schemas and be readable by the respective server plugins **without Content Manager installed**.

Never emit `variants:`, `material_family:`, `template:`, or manager-only metadata under VoxelCore `items:` or `blocks:` unless those keys are explicitly added to VoxelCore itself in a separately versioned contract. This project must not silently implement a parallel inheritance engine.

### Illustrative recipe (proposed, NOT existing VoxelCore YAML)

```yaml
recipe_schema: 1
id: table-wood-family
source: voxel:oak_table
target: mc-26.2
kind: inherited_item_family
axes:
  wood:
    provider: vanilla-wood-planks
    include: [oak, spruce, birch, jungle, acacia, dark_oak, mangrove, cherry, bamboo, crimson, warped, pale_oak]
output:
  id: "{wood}_table"
  display_name: "{wood|title} Table"
  extends: voxel:oak_table
  abstract: false
  model: "voxel:furniture/table/{wood}_table"
  strategy: json-parent-texture-alias
texture_roles:
  wood: "minecraft:block/{wood}_planks"
policy:
  existing_ids: error
  modified_outputs: conflict
  retain_source: true
  manual_review: true
```

This is the manager's **planned recipe DSL**, not a guarantee that `vanilla-wood-planks` includes all those entries on every version. The palette provider uses a version-resolved registry; unsupported variants are filtered and diagnosed. Recipe variables have deterministic escaping/casing rules. A recipe can restrict targets or supply explicit overrides per variant.

## 2. Target core generation algorithm (current MVP implements only a subset)

1. Resolve source ID to a canonical authored item and a VoxelCore-compiled inherited view; identify all linked render and addon references.
2. Resolve exact target's material/color palette. Compute Cartesian product of selected axes; require a user-approved upper bound (proposed default soft warning 64, hard max 4096 outputs per operation, configurable only with explicit advanced override).
3. Expand names and ContentIDs; validate naming, collisions, namespace ownership, duplicate outputs and cross-pack dependency restrictions.
4. Compute the **minimal authored child overrides** using VoxelCore's known inheritance rules. Lists replace, scalar keys override, nested maps deep-merge, `null` clears, and child `abstract: false` must override an inherited abstract parent.
5. Rewrite *only configured role-bound references*. An explicit inherited `furniture.model_item`, `vehicle.model_item`, `vehicle.drop`, `animation.use`, display-part reference or state model may require a variant-specific child override; report unresolved sticky references rather than pretending each child refers to itself.
6. Generate models through selected strategy, validate parent chains and texture slots, and check no accidental overwrite of existing files.
7. Stage a virtual filesystem with a manifest of **each proposed file/path/field**, ownership, original sha256, generated sha256, recipe revision and dependencies.
8. **Future gate:** Run adapter validations and actual VoxelCore content + pack validation for every selected target. The MVP currently performs structural and collision checks only; do not infer authoritative pack compatibility.
9. Show a review matrix and exact YAML/JSON changes with deterministic sort order. Apply transactionally only after explicit confirmation.

## 3. Model strategies (only `alias` and `clone` are implemented in the MVP)

| Strategy | When | Generated output | Hazards |
|---|---|---|---|
| `share-model` | Render identically and use one tintable runtime model | Child `render.model` can reuse source | No material difference without suitable tint rules |
| `json-parent-texture-alias` | Source model has replaceable `#texture` slots | Thin JSON child with `parent` + `textures` overrides | Parent must provide geometry/slot aliases; trace atlas refs |
| `clone-model-json` | Each variant requires explicit geometry/texture rewrite | One JSON model per item, copied element structure | Harder upstream maintenance; patch all nested faces/particle references |
| `palette-recolor-texture` | Authored texture needs new palette with shading preserved | New PNGs with reversible color transform manifest | Human review; alpha, tint, outlines and light values |
| `structured-cmd-tint` | One dyeable model on supported modern target | Shared model with `tintindex`, structured CMD and rules | Version gating; separate IDs may be unnecessary |
| `linked-external-model` | Reuse an approved existing model in another pack | Only item reference and dependency | Requires declared pack dependency and load order |

**Current restrictions:** `alias` writes a child JSON with `parent: <source-model>` and replaces exactly one selected texture slot, which must already reference the source vanilla plank/wool texture; `clone` copies the current model JSON and changes that slot. Both are conservative; they **do not** recursively clone animation or blockstate child models or resolve missing vanilla geometry. The local form warns for sticky inherited `model_item`/`drop` references. **Automatic vs explicit:** The manager may propose `json-parent-texture-alias` if a valid texture alias exists, but never declare it correct from filename similarity alone. Use semantic slot mapping (`wood`, `wool`, `accent`, `particle`, etc.), preview and target validation. If a JSON model inlines a full texture in every face, choose safe reference-aware clone or request explicit role assignment. Do not blindly replace every `oak` substring: oak-colored painted details and oak log ends are different assets.

Minecraft model parent references and `#texture` references are distinct; resolve both. Record the exact texture slot used for each face and any `particle` texture. Preserve `display` transforms and `tintindex`. Avoid overwriting source models, including shader-driven UI portraits or custom vanilla overrides.

## 4. Example: inherited wooden tables

Assume a source item **already exists** and its render model is compatible with `#wood` texture overrides.

**Authored VoxelCore YAML** (valid item-level shape; model files described below):

```yaml
items:
  oak_table:
    material: minecraft:paper
    display_name: "&fOak Table"
    render:
      model: voxel:furniture/table/oak_table
    properties:
      furniture:
        renderer: auto
        hitbox: {width: 1.5, height: 1.0}
        scale: 1.0
        rotation_step: 90

  spruce_table:
    extends: oak_table
    abstract: false
    display_name: "&fSpruce Table"
    render:
      model: voxel:furniture/table/spruce_table

  birch_table:
    extends: oak_table
    abstract: false
    display_name: "&fBirch Table"
    render:
      model: voxel:furniture/table/birch_table
```

Each child inherits the original table's furniture behavior. No duplicate furniture blocks or physics settings are required unless specifically overridden. Child model names are relative to the content namespace in the VoxelCore content pack.

**Model JSONs** (conceptual compatible pattern; geometry must really use `#wood`):

`assets/voxel/models/furniture/table/base_table.json`:

```json
{
  "textures": {"wood": "minecraft:block/oak_planks", "particle": "#wood"},
  "elements": [{
    "from": [0, 0, 0], "to": [16, 2, 16],
    "faces": {
      "up": {"texture": "#wood"},
      "down": {"texture": "#wood"},
      "north": {"texture": "#wood"},
      "south": {"texture": "#wood"},
      "east": {"texture": "#wood"},
      "west": {"texture": "#wood"}
    }
  }]
}
```

`assets/voxel/models/furniture/table/spruce_table.json`:

```json
{
  "parent": "voxel:furniture/table/base_table",
  "textures": {"wood": "minecraft:block/spruce_planks"}
}
```

In a real project, the parent model can contain the complete table geometry and multiple texture roles. The generator does **not** assume a one-element example is a finished table. The source oak model can itself extend `base_table` and use oak texture.

### Abstract/state-driven furniture children

For an open drawer or bench, generate an abstract render-only state item with `abstract: true` and a concrete owner item referring to its state `animation.use`. If a material family is applied, generate both owner and corresponding state items when the source graph demands it. Do not give, trade or expose these abstract visual items as ordinary stock.

For `blockstates`, use the current VoxelFurniture adapter's accepted state keys and selector rules, including orientation/adjacency. Preserve north/east/south/west and corner/edge models and validate every generated state reference. Never treat a showroom snapshot named a variant as a model inheritance child: VoxelFurnitureShop region variants are recorded world layouts with their own persistence lifecycle.

## 5. Example: 16 wool colors

Version catalog color set:
`white, orange, magenta, light_blue, yellow, lime, pink, gray, light_gray, cyan, purple, blue, brown, green, red, black`.

The recipe points `wool` slot at `minecraft:block/<color>_wool`. A `white_wool_chair` source can generate:
`orange_wool_chair`, `magenta_wool_chair`, `light_blue_wool_chair` ... `black_wool_chair` (source remains and all 16 IDs are represented). Human-visible names use `Light Blue` and `Light Gray`; IDs use underscores. The matrix must not create a duplicate white item unless the recipe explicitly asks for a renamed base.

The editor must offer a choice:
1. **16 independent item IDs:** tradeable/creative-visible variants and individual JSON texture children.
2. **One dyeable item:** one ID and tint-backed dynamic appearance if target/model/runtime rules support it.
3. **Hybrid:** one parent with state children, only concrete variants given to players.

**Version caveat:** `minecraft:block/*_wool` is a target-specific vanilla texture reference; validate its availability instead of bundling vanilla PNGs.

## 6. Other family providers

Vanilla families, validated per profile: woods/planks, wool, dyes, stained glass, terracotta, concrete, beds, doors, fences, leaves, logs, decorative stone, metals, colors and optional materials. Advanced custom palette sets can map arbitrary semantic roles, tags and texture files. Presets must not assume e.g. `pale_oak`, `bamboo`, `crimson`, `warped` or any introduced material exists on historical Minecraft clients.

Multi-axis families can create `<wood>_<color>_bench_<state>`. Detect count explosion, ID truncation, accidental composite collisions, and differing references for furniture state/vehicle paint. Keep a consistent deterministic expansion order and allow matrix-based exclusions.

## 7. Ownership manifest (planned schema)

```json
{
  "schema": 1,
  "recipe_id": "table-wood-family",
  "recipe_revision": "sha256:...",
  "input_content_id": "voxel:oak_table",
  "inputs": [{"path": ".../content/furniture.yml", "sha256": "..."}],
  "outputs": [
    {
      "path": ".../content/tables.yml",
      "yaml_path": "items.spruce_table",
      "content_id": "voxel:spruce_table",
      "ownership": "generated-field",
      "last_generated_hash": "sha256:...",
      "base_hash": "sha256:..."
    },
    {
      "path": ".../assets/voxel/models/furniture/table/spruce_table.json",
      "ownership": "generated-file",
      "last_generated_hash": "sha256:..."
    }
  ]
}
```

Paths in committed recipe manifests must be workspace-relative (illustrative `.../` above is *not* an allowed actual path). The implementation schema will use normalized portable path objects, no absolute local paths, no secrets, and explicit entry-level ownership. Manifests are authoritative only for **provenance of generated edits**, never for game item identity.

## 8. Regeneration and conflicting edits (MVP: hash-controlled refusal to overwrite modified generated output; three-way merge is future work)

- If input and output unchanged: no-op, same hashes, zero diff.
- If input changes and output remains unedited: update only recipe-owned keys/files.
- If output edited by a human: future: compute a three-way merge (last generated, current authored, new generated). **Currently:** reject changes to recipe-owned generated files if their hash no longer matches the manifest. No silent overwrite.
- If recipe removes a color: offer retain/detach output; warn inbound references, placed items, and allocation tombstones.
- If an owned model is moved or renamed: update all known graph edges, preserve any opaque external reference as a blocking warning.
- If generated child shadows an existing ContentID from another file/pack: fail before write.
- If source `abstract: true`: child must have `abstract: false` to be giveable; abstract state derivatives remain true.
- If references use a mismatched atlas for a target: rely on actual compiler validate/build, not a model preview assumption.

## 9. Schema adapter policy

**Exact VoxelCore keys today:** `items` contains `extends, type, material, display_name, lore, bound, abstract, render, properties, events`; `render` supports `model, unbreakable, durability, attributes, custom_model_data, oversized_in_gui, rule`. A content file can also contain `blocks` and `ui`. Pack manifests accept `schema, namespace, dependencies`. Unknown top-level/item/render keys are rejected by the current parser.

**Furniture today:** `properties.furniture` includes renderer/model_item/drop/hitbox/scale/view_distance/rotation_step/placement/seat/offset/blocks/blockstates/animation/idle_animation/display_parts/interaction/inventory/value/worth; exact nested grammar must be derived from the current parser, not guessed.

**Vehicles today:** `properties.vehicle` includes type/public/model_item/drop/hitbox/collision/scale/offset/seat/physics/suspension/particles/inventory/view_distance. Custom color/tint can also live in `render.custom_model_data`, `render.rule` and `properties.dyeable`. The item and its vehicle definition share one ContentID.

Do not promise that an edit is runtime-valid until it passes the exact adapter and compiler/version profile. Schemas should be generated/tested from source fixtures wherever feasible, with a separately maintained compatibility matrix for non-public API behavior.
