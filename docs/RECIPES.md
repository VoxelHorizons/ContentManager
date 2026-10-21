# Multi-axis recipes (schema 1)

Recipes are explicit editor metadata. They never become new VoxelCore runtime keys.
Use the **Multi-axis recipes** tab or:

```bash
python -m content_manager recipe /path/to/content /path/to/recipe.yml
python -m content_manager recipe /path/to/content /path/to/recipe.yml --apply
```

The first command is read-only. Apply writes reviewed item/model derivatives and a
manifest containing the full recipe, revision digest and output ownership hashes.
Replay that manifest with the same command or Load recipe / manifest in the GUI.

```yaml
recipe_schema: 1
id: upholstered-table
source: voxel:oak_table
target: mc-26.3
strategy: alias
axes:
  wood:
    oak: minecraft:block/oak_planks
    spruce: minecraft:block/spruce_planks
  color:
    white: minecraft:block/white_wool
    red: minecraft:block/red_wool
texture_slots:
  wood: wood
  cloth: color
items:
  voxel:oak_table: '{wood}_{color}_table'
  voxel:oak_open: '{wood}_{color}_open'
```

Both source items must already exist in the same pack and their resolved models
must expose `wood` and `cloth` texture slots. The explicit item list lets the
planner remap known animation/blockstate/display-part/chest references. The
owner is concrete; related source items retain their abstract status. Missing
items or slots fail before writes. Other shared references are retained and
reported. Map overrides are minimal; state lists preserve selector fields.

One to four axes are accepted, with at most 4096 planned files and 64 MiB of
serialized output. Axis names/values are lowercase identifiers. Only literal
`{axis}` substitutions are supported: no Python expressions, attribute access,
commands or scripts. Include every axis in output names to avoid collisions.
Original source IDs cannot be reused as output names. Target selection is a
label/profile gate, **not verification that custom texture choices exist in a
particular Minecraft version**.

Alias and clone model strategies are supported. This recipe version binds axes
to textures, not arbitrary geometry scale, physical dimensions, tint rules or
animation timing. These require later recipe extensions. Geometry, UVs and
transforms are preserved. Vanilla model geometry remains unverified when client
assets are absent.

Regeneration updates only unchanged recipe-owned output. Human edits produce a
conflict; no automatic three-way merge is implemented. Narrowing a recipe retains
previous output and reports that retention. There is no implicit deletion or ID
migration. All edits participate in the ordinary snapshot undo/redo/recovery flow.

Minecraft `mc-26.2` remains selectable. The `mc-26.3` profile currently
selects a curated palette only; authoritative version-aware Java pack
validation has not yet been integrated.
