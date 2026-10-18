# Product specification and UX flows

## Interaction principles

**Guided by default, expert when needed.** Every feature offers simple controls and an advanced raw YAML/JSON view of exactly the same files. No two sources of truth. Every bulk operation starts as a dry-run. Suggestions never commit themselves. Model previews must distinguish **estimated studio rendering** from **verified Minecraft runtime output**.

**Fast everyday actions:** keyboard command palette, global search, breadcrumbs, bulk multi-select, drag-and-drop texture/model assignment, pin/recent assets, tags, presets, undo/redo, quick duplicate, duplicate with inheritance, compare siblings, and a one-click jump to defining parent.

## Navigation and screen inventory

| Screen | Main interactions |
|---|---|
| Workspace home | Open/import pack or server, sample content, target profile, last build health |
| Explorer | Search/filter pack, item, block, furniture, vehicle, glyph, shop, file and generated derivative |
| Content editor | Name/ID, material, lore, flags, actions, addon-specific conditional panels, property provenance |
| Model library | Thumbnail grid, JSON parent/texture slots, model associations, inherited texture previews |
| Texture studio | Pixel-grid editor, palette swap, alpha handling, recolor preview, 16x/32x/other dimensions |
| Generator wizard | Pick source/template, parameter families, naming, inherited overrides, output matrix and diff |
| 3D preview | Rotate/pan/zoom, show hitbox/seat/collision blocks/display parts, switching item/world/GUI transforms |
| Relationship graph | Dependencies, dead assets, duplicate IDs, orphan models, incoming references, rename-impact view |
| UI/glyph studio | PNG glyph, scale/ascent, offsets, palette and multilingual text/title preview |
| Shop workspace | View prices, shop items, item worth, UI references and unsupported purchase variants |
| Build center | Per-target diagnostics, validate, deterministic ZIP build, manifests, preview artifact differences |
| Publish center | Diff, backups, release notes, approval, safe deploy, rollback, audit |
| Settings/diagnostics | Schema version, compiler commit, cache, workspace permissions, snapshots, plugin handshake |

### Example: new Oak Table

1. **New → Furniture**; choose `Table` preset, name `oak_table`, select pack `voxel`.
2. Associate existing geometry model and set material/texture slots (or import a JSON model).
3. Inspect the VoxelFurniture panel: hitbox, rotation step, local offsets, collision blocks and optional interactions/storage.
4. In 3D, visualize the model at four orientations, interaction box and collision footprint.
5. Validate; create staged YAML + model refs. Apply after reviewing which files/keys change.
6. Optionally continue into **Create Family → Wood types**.

### Example: Wood Family wizard

1. Select `voxel:oak_table`; choose `wood-planks` palette for the chosen Minecraft version.
2. Select included types (oak, spruce, birch, etc.), one base model and either texture-alias children or full model materialization.
3. Map semantic texture roles to `minecraft:block/<wood>_planks` or explicit authored textures; set `display_name = <Wood> Table`, `ContentID = <wood>_table`.
4. Preview a grid showing the source, inherited fields and the resolved textures for every variant. Red highlight = unresolved texture or non-portable target.
5. Exclude individual variants or edit their overrides; select `keep inherited gameplay behavior`.
6. See a file/key diff and impact summary before Apply. Later edits to the base can be propagated to unmodified derivatives without overwriting edited children.

### Example: Wool Color Family wizard

Pick an existing wool-covered seat or table; select the **vanilla wool** palette; create 16 variants with canonical color labels and texture paths. The wizard offers a true color/texture family, **or** one tintable model when render rules and content behavior allow. Separate ContentIDs versus one dyeable item is an explicit product choice, not a hidden optimization.

## Detail editor: sections and conditional behavior

**Universal:** identity, pack, tags/notes (studio metadata), type, material, abstract, bound, lore, model, textures, actions, inheritance and provenance.

**Blocks:** cube/cube_column/custom model, face textures, carrier method, hardness, blast resistance, drops, silk touch, tool tiers, stackability and compatibility.

**Furniture:** renderer AUTO/display/legacy compatibility, preview model ID, `scale` scalar/vector, hitbox dimensions/offsets, placement TOP/WALL, seat yaw/position, local offset + rotation, 45/90° steps, block collision data, neighbor-state model selector, use animation, draw/display parts, inventory/close delay, idle bob/spin and value/worth; expose limitations of horizontal interaction width.

**Vehicles:** LAND/PLANE, model/drop ID, public/private, independent collision vs click hitboxes, local assembly offsets, driver seat, suspension pitch/roll, physics ranges, storage slots + chest attach model, preview icon, tints/custom model data. Do not imply a static preview simulates suspension/physics accurately; server test is required.

**UI and economy-facing references:** font glyph path/ascent and negative offsets, named aliases, tooltip text, currencies and item values, abstract GUI icon vs tradeable stock rules.

## Visual/editor constraints

- Preview editable model `display.gui`, `display.fixed`, `display.thirdperson` and ItemDisplay context where JSON specifies transforms. Texture UV and rotation are preserved.
- Load the full Minecraft-style parent chain and resolve `#texture` indirections; detect cycles and missing parents. Vanilla asset bundles are loaded from a user-selected legally obtained client/version jar or an explicit approved reference source; never embed proprietary assets without license.
- Show a **preview capability label** when shader-driven portraits, emissive effects, dye tint, client fonts or runtime display interactions cannot match without a running client.
- Pixel editor: nearest-neighbor zoom by default, optional alpha checker, hard pixel grid, no unwanted antialiasing, reversible palette operations; retain original PNG unless user explicitly saves an edited derivative.
- Schema-driven forms expose tooltips, legal ranges, field-level errors, parent values and supported-version badges. Unknown extension fields remain editable in expert mode without the editor dropping them.
- In-context help links to the actual VoxelCore/Furniture/Vehicles docs and examples, not hard-coded stale placeholders.

## Bulk tasks and advanced conveniences

- Rename/refactor ContentIDs with reference graph preview and compatibility warnings; never assume world-instance migration.
- Find/replace item names, model paths, texture IDs and placeholder aliases using typed operations.
- Copy component presets (hitbox/seat/physics) without forcing unrelated fields.
- Multi-axis generation: material × color × size × state × handedness/rotation. Show count and cost estimate; hard limit/cancellable work; deterministic ordering.
- Orphan detection, duplicate/ambiguous asset names, unused font glyphs, atlas target differences and circular references.
- Side-by-side YAML source and **resolved** inherited view; granular three-way merge on external file changes.
- Content test kits: representative items/furniture/vehicles, resource-pack build, Paper integration checklist and scripted staging commands.

## Optional future intelligence

AI-assisted naming, suggested mapping of texture roles, generating semantic descriptions and interpreting compiler errors may be added behind explicit opt-in. AI output is always an untrusted proposal and must pass the same deterministic compiler validation. No cloud account or external inference should be necessary for core use.
